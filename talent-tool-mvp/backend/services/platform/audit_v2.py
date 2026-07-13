"""T2603 — Enterprise Audit Log v2 Service.

Adds GDPR Art. 30 / PIPL / CCPA-compliant audit primitives on top of
``services.observability.audit``:

- ``audit(actor, action, resource, pii_fields, lawful_basis, ...)``
  Writes one row to ``audit_log_v2`` (preferred) or falls back to
  ``audit_log`` if v2 table is missing.

- ``@audit_pii(action, resource_type, lawful_basis, pii_fields=None)``
  Decorator that wraps any FastAPI route / service function and emits
  one audit row per invocation.

- ``audit_pii_module(module, action_map)`` — AST-driven scanner: walks
  a module, finds every function whose signature contains one of the
  canonical PII parameter names (``email``, ``phone``, ``ssn``,
  ``id_number``, ``resume``, ``interview_video``, ``salary``,
  ``address``, ``dob``) and returns a decorator map so the caller can
  blanket-apply audit to the entire module.

- Built-in detection of the request context (IP / UA / actor) from a
  FastAPI ``Request``-shaped argument; falls back to thread-local.

The whole module is import-safe: it never raises at import time even
if Supabase is unavailable.
"""
from __future__ import annotations

import ast
import functools
import inspect
import logging
import os
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional

logger = logging.getLogger("waibao.audit_v2")

# ---------------------------------------------------------------------------
# Canonical PII fields (cross-region, cross-purpose)
# ---------------------------------------------------------------------------
PII_FIELDS: set[str] = {
    # contact
    "email", "phone", "address", "location", "postcode", "zipcode",
    # identity
    "name", "full_name", "first_name", "last_name", "ssn",
    "id_number", "passport", "id_card", "dob", "date_of_birth",
    "gender", "ethnicity", "nationality", "marital_status",
    # career
    "resume", "cv", "work_history", "education", "skills",
    "salary", "compensation", "bank_account",
    # behavioural / sensitive
    "interview_video", "interview_audio", "voice_print",
    "facial_expression", "health", "criminal_record",
    "credit_score", "religion", "political_affiliation",
    "sexual_orientation",
}

# Maps region -> default lawful_basis code (region comes from the request)
DEFAULT_LAWFUL_BASIS: dict[str, str] = {
    "EU": "gdpr_consent",
    "CN": "pipl_consent",
    "CA": "ccpa_business_purpose",
    "US": "ccpa_business_purpose",
    "GLOBAL": "gdpr_consent",
}

# Maps action -> data_classification
ACTION_DATA_CLASS: dict[str, str] = {
    "read": "pii",
    "list": "pii",
    "export": "sensitive",
    "create": "pii",
    "update": "pii",
    "delete": "pii",
    "forget": "sensitive",
    "rectify": "sensitive",
    "consent_grant": "public",
    "consent_withdraw": "public",
    "login": "public",
    "logout": "public",
    "share": "sensitive",
}


# ---------------------------------------------------------------------------
# Thread-local request context (filled by middleware / dependency)
# ---------------------------------------------------------------------------
_tls = threading.local()


@dataclass(slots=True)
class AuditContext:
    actor_id: str | None = None
    actor_role: str | None = None
    tenant_id: str | None = None
    actor_ip: str | None = None
    actor_ua: str | None = None
    request_id: str | None = None
    session_id: str | None = None
    region: str = "GLOBAL"


def set_audit_context(ctx: AuditContext) -> None:
    _tls.ctx = ctx


def get_audit_context() -> AuditContext:
    return getattr(_tls, "ctx", AuditContext())


def clear_audit_context() -> None:
    if hasattr(_tls, "ctx"):
        delattr(_tls, "ctx")


def update_audit_context(**kwargs: Any) -> None:
    ctx = get_audit_context()
    for k, v in kwargs.items():
        if v is not None:
            setattr(ctx, k, v)
    set_audit_context(ctx)


# ---------------------------------------------------------------------------
# Internal Supabase accessor (graceful when unavailable)
# ---------------------------------------------------------------------------
def _sb():
    try:
        from api.deps import get_supabase_admin  # type: ignore

        return get_supabase_admin()
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# In-memory fallback buffer (test + dev environments)
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class AuditRecord:
    id: str
    actor_id: str | None
    actor_role: str | None
    tenant_id: str | None
    action: str
    resource_type: str
    resource_id: str | None
    data_classification: str
    pii_accessed: list[str]
    lawful_basis: str
    request_id: str | None
    session_id: str | None
    metadata: dict[str, Any]
    created_at: datetime
    retention_until: datetime


class _InMemoryStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._records: list[AuditRecord] = []
        self._max = int(os.environ.get("AUDIT_V2_MEM_MAX", "10000"))

    def append(self, rec: AuditRecord) -> None:
        with self._lock:
            self._records.append(rec)
            if len(self._records) > self._max:
                self._records = self._records[-self._max :]

    def query(
        self,
        *,
        actor_id: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        action: str | None = None,
        tenant_id: str | None = None,
        limit: int = 100,
    ) -> list[AuditRecord]:
        with self._lock:
            results = self._records
            if actor_id:
                results = [r for r in results if r.actor_id == actor_id]
            if tenant_id:
                results = [r for r in results if r.tenant_id == tenant_id]
            if resource_type:
                results = [r for r in results if r.resource_type == resource_type]
            if resource_id:
                results = [r for r in results if r.resource_id == resource_id]
            if action:
                results = [r for r in results if r.action == action]
            return results[-limit:]

    def clear(self) -> None:
        with self._lock:
            self._records.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)


_store = _InMemoryStore()


def get_audit_store() -> _InMemoryStore:
    return _store


def reset_audit_store() -> None:
    _store.clear()


# ---------------------------------------------------------------------------
# Retention computation
# ---------------------------------------------------------------------------
def compute_retention_until(
    action: str,
    *,
    region: str = "GLOBAL",
    explicit_days: int | None = None,
) -> datetime:
    """Compute the timestamp when this audit row may be purged.

    PIPL Art. 52: minimum 3 years for personal information processing
    records. GDPR has no fixed ceiling; we use 3 years for EU too, so
    global deployments share a single retention clock. Special actions
    (export / forget / breach) get 5 years to satisfy Art. 33.
    """
    if explicit_days is not None:
        return datetime.now(timezone.utc) + timedelta(days=explicit_days)
    base_days = 365 * 3
    if action in {"export", "forget", "breach", "rectify"}:
        base_days = 365 * 5
    if action in {"login", "logout", "consent_grant", "consent_withdraw"}:
        base_days = 365 * 2
    return datetime.now(timezone.utc) + timedelta(days=base_days)


# ---------------------------------------------------------------------------
# Core API
# ---------------------------------------------------------------------------
def audit(
    *,
    actor: str | None = None,
    actor_role: str | None = None,
    tenant_id: str | None = None,
    action: str,
    resource: str,
    resource_id: str | None = None,
    pii_fields: Iterable[str] | None = None,
    lawful_basis: str | None = None,
    data_classification: str | None = None,
    metadata: dict[str, Any] | None = None,
    region: str | None = None,
    ip: str | None = None,
    ua: str | None = None,
    request_id: str | None = None,
    session_id: str | None = None,
    retention_days: int | None = None,
) -> str:
    """Emit one audit row. Returns the row id.

    Never raises: audit must never break the calling request.
    """
    try:
        ctx = get_audit_context()
        actor_id = actor or ctx.actor_id
        effective_tenant = tenant_id or ctx.tenant_id
        effective_region = region or ctx.region or "GLOBAL"
        effective_ip = ip or ctx.actor_ip
        effective_ua = ua or ctx.actor_ua
        effective_request_id = request_id or ctx.request_id
        effective_session_id = session_id or ctx.session_id

        # canonicalise pii fields
        pii_list = sorted(set(f for f in (pii_fields or []) if f))
        # auto-detect PII from resource_id and metadata if obvious
        if resource_id and resource_id in PII_FIELDS and resource_id not in pii_list:
            pii_list.append(resource_id)
            pii_list.sort()

        classification = (
            data_classification
            or ("sensitive" if pii_list and any(p in {
                "ssn", "id_number", "passport", "health", "religion",
                "credit_score", "voice_print", "interview_video",
            } for p in pii_list) else ACTION_DATA_CLASS.get(action, "pii"))
        )

        effective_basis = lawful_basis or DEFAULT_LAWFUL_BASIS.get(
            effective_region, "gdpr_consent"
        )
        rec_id = f"audv2_{uuid.uuid4().hex[:20]}"
        created_at = datetime.now(timezone.utc)
        retention = compute_retention_until(
            action, region=effective_region, explicit_days=retention_days
        )

        # 1) Always write to the in-memory store (so tests + dev work)
        rec = AuditRecord(
            id=rec_id,
            actor_id=actor_id,
            actor_role=actor_role or ctx.actor_role,
            tenant_id=effective_tenant,
            action=action,
            resource_type=resource,
            resource_id=resource_id,
            data_classification=classification,
            pii_accessed=pii_list,
            lawful_basis=effective_basis,
            request_id=effective_request_id,
            session_id=effective_session_id,
            metadata=metadata or {},
            created_at=created_at,
            retention_until=retention,
        )
        _store.append(rec)

        # 2) Best-effort persist to Supabase
        sb = _sb()
        if sb is not None:
            payload = {
                "actor_id": actor_id,
                "actor_role": actor_role or ctx.actor_role,
                "tenant_id": effective_tenant,
                "actor_ip": effective_ip,
                "actor_ua": (effective_ua or "")[:512],
                "action": action,
                "resource_type": resource,
                "resource_id": resource_id,
                "data_classification": classification,
                "pii_accessed": pii_list,
                "lawful_basis": effective_basis,
                "request_id": effective_request_id,
                "session_id": effective_session_id,
                "metadata": metadata or {},
            }
            payload = {k: v for k, v in payload.items() if v not in (None, "", [])}
            try:
                # try v2 first; fallback to legacy
                try:
                    sb.table("audit_log_v2").insert(payload).execute()
                except Exception:  # noqa: BLE001
                    sb.table("audit_log").insert({
                        "actor_user_id": payload.get("actor_id"),
                        "action": payload["action"],
                        "resource_type": payload["resource_type"],
                        "resource_id": payload.get("resource_id"),
                        "user_id": payload.get("actor_id"),
                        "ip_address": payload.get("actor_ip"),
                        "user_agent": payload.get("actor_ua"),
                        "metadata": {
                            **payload.get("metadata", {}),
                            "data_classification": payload.get("data_classification"),
                            "pii_accessed": payload.get("pii_accessed"),
                            "lawful_basis": payload.get("lawful_basis"),
                            "audit_v2": True,
                        },
                    }).execute()
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "audit_v2.persist_failed action=%s err=%s",
                    action, exc,
                )
        return rec_id
    except Exception as exc:  # noqa: BLE001
        logger.warning("audit_v2.emit_failed action=%s err=%s", action, exc)
        return ""


# ---------------------------------------------------------------------------
# Decorator: @audit_pii
# ---------------------------------------------------------------------------
def _extract_pii_from_args(args: tuple, kwargs: dict) -> list[str]:
    found: set[str] = set()
    # Inspect kwarg names — these are the strongest signal that a
    # function is operating on a PII field (e.g. ``email="x@y"``).
    for k in kwargs.keys():
        if isinstance(k, str) and k.lower() in PII_FIELDS:
            found.add(k.lower())
    # Inspect positional arg values — if a literal string happens to
    # be a PII field name, count it too.
    for v in list(args) + list(kwargs.values()):
        if isinstance(v, str) and v.lower() in PII_FIELDS:
            found.add(v.lower())
        elif isinstance(v, dict):
            for k in v.keys():
                if isinstance(k, str) and k.lower() in PII_FIELDS:
                    found.add(k.lower())
        elif isinstance(v, (list, tuple)):
            for item in v:
                if isinstance(item, str) and item.lower() in PII_FIELDS:
                    found.add(item.lower())
    return sorted(found)


def audit_pii(
    action: str,
    resource_type: str,
    lawful_basis: str | None = None,
    pii_fields: Iterable[str] | None = None,
    *,
    data_classification: str | None = None,
    actor_arg: str = "user",
    resource_id_arg: str | None = None,
    resource_id_attr: str | None = None,
    metadata_fn: Optional[Callable[..., dict]] = None,
):
    """Decorator: emit one audit row per call.

    - ``action``: e.g. ``"read"``, ``"update"``
    - ``resource_type``: e.g. ``"candidate"``, ``"journal"``
    - ``lawful_basis``: optional; defaults to region's choice
    - ``pii_fields``: explicit field list; auto-detected when omitted
    - ``actor_arg``: kwarg name holding the actor (default: ``user``)
    - ``resource_id_arg``: kwarg name holding the resource id
    - ``resource_id_attr``: attribute on the result whose value becomes resource_id
    - ``metadata_fn``: callable(args, kwargs, result) -> dict
    """

    def decorator(fn: Callable) -> Callable:
        sig = inspect.signature(fn)
        is_coro = inspect.iscoroutinefunction(fn)
        declared_pii = list(pii_fields) if pii_fields else None

        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs):
            try:
                result = await fn(*args, **kwargs)
            except Exception:
                audit(
                    action=action,
                    resource=resource_type,
                    resource_id=_resolve_resource_id(args, kwargs, None, resource_id_arg, resource_id_attr),
                    pii_fields=declared_pii or _extract_pii_from_args(args, kwargs),
                    lawful_basis=lawful_basis,
                    data_classification=data_classification,
                    actor=_resolve_actor(kwargs, actor_arg),
                    actor_role=_resolve_actor_role(kwargs, actor_arg),
                    tenant_id=_resolve_tenant(kwargs),
                    metadata={
                        "error": True,
                        "decorator": "audit_pii",
                        "fn": fn.__qualname__,
                    },
                )
                raise
            audit(
                action=action,
                resource=resource_type,
                resource_id=_resolve_resource_id(args, kwargs, result, resource_id_arg, resource_id_attr),
                pii_fields=declared_pii or _extract_pii_from_args(args, kwargs),
                lawful_basis=lawful_basis,
                data_classification=data_classification,
                actor=_resolve_actor(kwargs, actor_arg),
                actor_role=_resolve_actor_role(kwargs, actor_arg),
                tenant_id=_resolve_tenant(kwargs),
                metadata=_build_metadata(metadata_fn, args, kwargs, result, fn.__qualname__),
            )
            return result

        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs):
            try:
                result = fn(*args, **kwargs)
            except Exception:
                audit(
                    action=action,
                    resource=resource_type,
                    resource_id=_resolve_resource_id(args, kwargs, None, resource_id_arg, resource_id_attr),
                    pii_fields=declared_pii or _extract_pii_from_args(args, kwargs),
                    lawful_basis=lawful_basis,
                    data_classification=data_classification,
                    actor=_resolve_actor(kwargs, actor_arg),
                    actor_role=_resolve_actor_role(kwargs, actor_arg),
                    tenant_id=_resolve_tenant(kwargs),
                    metadata={
                        "error": True,
                        "decorator": "audit_pii",
                        "fn": fn.__qualname__,
                    },
                )
                raise
            audit(
                action=action,
                resource=resource_type,
                resource_id=_resolve_resource_id(args, kwargs, result, resource_id_arg, resource_id_attr),
                pii_fields=declared_pii or _extract_pii_from_args(args, kwargs),
                lawful_basis=lawful_basis,
                data_classification=data_classification,
                actor=_resolve_actor(kwargs, actor_arg),
                actor_role=_resolve_actor_role(kwargs, actor_arg),
                tenant_id=_resolve_tenant(kwargs),
                metadata=_build_metadata(metadata_fn, args, kwargs, result, fn.__qualname__),
            )
            return result

        wrapper = async_wrapper if is_coro else sync_wrapper
        wrapper.__wrapped__ = fn  # type: ignore[attr-defined]
        wrapper.__signature__ = sig  # type: ignore[attr-defined]
        wrapper.__audit_meta__ = {  # type: ignore[attr-defined]
            "action": action,
            "resource_type": resource_type,
            "lawful_basis": lawful_basis,
            "pii_fields": declared_pii,
        }
        return wrapper

    return decorator


def _resolve_actor(kwargs: dict, actor_arg: str) -> str | None:
    if actor_arg in kwargs:
        u = kwargs[actor_arg]
        if hasattr(u, "id"):
            return str(u.id)
        if isinstance(u, str):
            return u
    # FastAPI dependency injection may put it as positional arg
    for v in kwargs.values():
        if hasattr(v, "id") and hasattr(v, "role"):
            return str(v.id)
    ctx = get_audit_context()
    return ctx.actor_id


def _resolve_actor_role(kwargs: dict, actor_arg: str) -> str | None:
    if actor_arg in kwargs:
        u = kwargs[actor_arg]
        if hasattr(u, "role"):
            return getattr(u, "role", None)
    for v in kwargs.values():
        if hasattr(v, "id") and hasattr(v, "role"):
            return getattr(v, "role", None)
    return get_audit_context().actor_role


def _resolve_tenant(kwargs: dict) -> str | None:
    for v in kwargs.values():
        if hasattr(v, "tenant_id"):
            tid = getattr(v, "tenant_id", None)
            if tid:
                return str(tid)
    ctx = get_audit_context()
    return ctx.tenant_id


def _resolve_resource_id(
    args: tuple,
    kwargs: dict,
    result: Any,
    resource_id_arg: str | None,
    resource_id_attr: str | None,
) -> str | None:
    if resource_id_arg and resource_id_arg in kwargs:
        v = kwargs[resource_id_arg]
        return str(v) if v is not None else None
    if resource_id_attr and result is not None:
        attr = getattr(result, resource_id_attr, None)
        if attr is not None:
            return str(attr)
    # FastAPI path param fallback
    request = kwargs.get("request")
    if request is not None and hasattr(request, "path_params"):
        for v in request.path_params.values():
            return str(v)
    # Heuristic: any kwarg whose name looks like "*_id" / "id" / "uuid"
    for name in ("resource_id", "id", "user_id", "candidate_id",
                 "ticket_id", "dsr_id", "target_user_id"):
        if name in kwargs and kwargs[name] is not None:
            return str(kwargs[name])
    # First positional str arg
    for a in args:
        if isinstance(a, str) and a:
            return a
    return None


def _build_metadata(
    fn: Optional[Callable[..., dict]],
    args: tuple,
    kwargs: dict,
    result: Any,
    qualname: str,
) -> dict:
    base = {"decorator": "audit_pii", "fn": qualname}
    if fn is not None:
        try:
            base.update(fn(args, kwargs, result) or {})
        except Exception:  # noqa: BLE001
            base["metadata_fn_error"] = True
    return base


# ---------------------------------------------------------------------------
# AST-driven scanner
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class ScannedFunction:
    qualname: str
    module: str
    lineno: int
    pii_params: list[str]
    args: list[str]


def scan_module_for_pii(module: Any) -> list[ScannedFunction]:
    """Walk a module's AST and return every function whose signature
    contains at least one canonical PII parameter name.

    Use this to decide which functions in the codebase *should* be
    decorated with ``@audit_pii``. The return value is a pure-data
    inventory; it does not import or run the module.
    """
    try:
        source = inspect.getsource(module)
    except (OSError, TypeError):
        source = ""

    return scan_source_for_pii(source, module_name=getattr(module, "__name__", "?"))


def scan_source_for_pii(source: str, *, module_name: str = "<source>") -> list[ScannedFunction]:
    """Same as ``scan_module_for_pii`` but takes source code directly.

    Useful for tests / synthetic modules where ``inspect.getsource``
    fails because the module is not on disk.
    """
    if not source:
        return []
    tree = ast.parse(source)
    results: list[ScannedFunction] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = [a.arg for a in node.args.args] + [
                a.arg for a in node.args.kwonlyargs
            ]
            pii_hits = sorted({a.lower() for a in args if a.lower() in PII_FIELDS})
            if pii_hits:
                results.append(
                    ScannedFunction(
                        qualname=node.name,
                        module=module_name,
                        lineno=node.lineno,
                        pii_params=pii_hits,
                        args=args,
                    )
                )
    return results


def build_audit_decorators(
    scanned: list[ScannedFunction],
    *,
    action: str = "read",
    resource_attr: str | None = None,
) -> dict[str, Callable]:
    """Given a list of ``ScannedFunction`` (e.g. from ``scan_module_for_pii``),
    return a ``{qualname: decorator_factory}`` map so a caller can
    blanket-attach audit to every detected function:

        decos = build_audit_decorators(scanned)
        for qualname, deco in decos.items():
            target = getattr(mod, qualname)
            setattr(mod, qualname, deco(action="read")(target))
    """
    factories: dict[str, Callable] = {}
    for sf in scanned:
        resource = (resource_attr or sf.module.rsplit(".", 1)[-1])
        pii = sf.pii_params

        def make_factory(p=pii, r=resource):
            def factory(*, action: str = action, resource_type: str = r,
                        lawful_basis: str | None = None):
                return audit_pii(
                    action=action,
                    resource_type=resource_type,
                    lawful_basis=lawful_basis,
                    pii_fields=p,
                )
            return factory

        factories[sf.qualname] = make_factory()
    return factories


# ---------------------------------------------------------------------------
# Coverage verifier
# ---------------------------------------------------------------------------
def coverage_report(
    *,
    api_dir: str = "backend/api",
) -> dict[str, Any]:
    """Scan ``api_dir`` and report which route functions touch PII
    (per the canonical PII field set) and which do not yet carry the
    ``__audit_meta__`` attribute set by ``@audit_pii``.

    The intent is to make "100% coverage" a verifiable claim rather
    than a hopeful one.
    """
    audited: list[str] = []
    untracked_pii: list[dict[str, Any]] = []

    for root, _dirs, files in os.walk(api_dir):
        for fn in files:
            if not fn.endswith(".py") or fn.startswith("__"):
                continue
            full = os.path.join(root, fn)
            try:
                with open(full, "r", encoding="utf-8") as fp:
                    src = fp.read()
            except OSError:
                continue
            tree = ast.parse(src, filename=full)
            for node in tree.body:  # top-level only — skip nested helpers
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                arg_names = (
                    [a.arg for a in node.args.args]
                    + [a.arg for a in node.args.kwonlyargs]
                )
                pii_hits = sorted({a.lower() for a in arg_names if a.lower() in PII_FIILDS_safe()})
                if not pii_hits:
                    continue
                # Only consider functions exposed via a router decorator
                # (i.e. something like @router.get / @app.get / @app.post).
                # Private helpers and tests don't need audit decorators.
                is_route = False
                for d in node.decorator_list:
                    fn = d.func if isinstance(d, ast.Call) else d
                    if isinstance(fn, ast.Attribute) and fn.attr in {
                        "get", "post", "put", "delete", "patch", "route", "api_route",
                    }:
                        is_route = True
                        break
                    if isinstance(fn, ast.Name) and fn.id in {
                        "router", "app",
                    }:
                        # bare @router or @app — needs sub-decorator; skip
                        pass
                if not is_route:
                    continue
                has_audit = any(
                    (isinstance(d, ast.Attribute) and d.attr == "audit_pii")
                    or (isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "audit_pii")
                    or (isinstance(d, ast.Name) and d.id == "audit_pii")
                    or (isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "audit_pii")
                    for d in node.decorator_list
                )
                if has_audit:
                    audited.append(f"{full}:{node.lineno} {node.name}")
                else:
                    untracked_pii.append({
                        "file": full,
                        "lineno": node.lineno,
                        "function": node.name,
                        "pii_params": pii_hits,
                    })
    total = len(audited) + len(untracked_pii)
    coverage_pct = (len(audited) / total * 100) if total else 100.0
    return {
        "total_pii_touching": total,
        "audited": len(audited),
        "untracked": len(untracked_pii),
        "coverage_pct": round(coverage_pct, 2),
        "untracked_detail": untracked_pii,
    }


def PII_FIILDS_safe() -> set[str]:
    return PII_FIELDS
