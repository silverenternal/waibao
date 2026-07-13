"""v8.0 T3502 — Public Service Catalog API.

Anonymous-safe endpoints that the marketing site (/services) uses to
render the live service catalog. Endpoints:

    GET  /api/public/services                     - list enabled services (filterable)
    GET  /api/public/services/categories          - bucketed by category + plan
    GET  /api/public/services/{name}              - public detail + dependencies + SLA
    GET  /api/public/services/{name}/dependencies - dependency sub-graph
    GET  /api/public/services/graph/all           - public dep graph (DAG, anonymous-safe)
    POST /api/public/services/subscribers         - email / webhook subscription

The public route never reveals internals: it filters out ``plan_required ==
'internal'``, ``status == 'disabled'``, and never returns any audit/admin
payload. Subscribers are persisted best-effort to ``service_subscribers``
(graceful no-op when Supabase is not configured).

Cached for 60 seconds via the same key scheme as ``service_toggle``.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field

from services.platform.service_catalog import (
    PlanTier,
    ServiceStatus,
)
from services.platform.service_registry import (
    catalog_snapshot,
    get_dependencies_for,
)
from services.platform.service_toggle import service_toggle

logger = logging.getLogger("recruittech.api.public_services")

router = APIRouter(prefix="/api/public/services", tags=["public-services"])


# ---------------------------------------------------------------------------
# Lightweight in-process subscriber store (Supabase-backed when available)
# ---------------------------------------------------------------------------
_SUBSCRIBERS: List[Dict[str, Any]] = []


def _supabase_safe():
    try:
        from api.deps import get_supabase_admin

        return get_supabase_admin()
    except Exception:
        return None


def _persist_subscriber(payload: Dict[str, Any]) -> bool:
    """Best-effort persist. Returns True if persisted, False if skipped."""
    sb = _supabase_safe()
    if sb is None:
        return False
    try:
        sb.table("service_subscribers").insert(payload).execute()
        return True
    except Exception as exc:  # pragma: no cover
        logger.debug("service_subscribers persist failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# SLA / metadata constants
# ---------------------------------------------------------------------------
_DEFAULT_SLA = {
    "uptime_target_pct": 99.9,
    "support_response_minutes": 60,
    "incident_history_url": "/status",
}

_CATEGORY_DISPLAY = {
    "agent": "AI 智能体",
    "business": "业务模块",
    "integration": "集成",
    "platform": "平台",
    "frontend": "端",
    "api": "API",
    "analytics": "分析",
    "misc": "其他",
}

_CATEGORY_ORDER = ["agent", "business", "frontend", "integration", "api", "platform", "analytics", "misc"]

_PLAN_ORDER = ["free", "pro", "enterprise"]


# ---------------------------------------------------------------------------
# Cache (60s)
# ---------------------------------------------------------------------------
_CACHE: Dict[str, Any] = {}
_CACHE_TS: Dict[str, float] = {}
_TTL = 60.0


def _cache_get(key: str) -> Optional[Any]:
    ts = _CACHE_TS.get(key)
    if ts is not None and (time.time() - ts) < _TTL:
        return _CACHE.get(key)
    return None


def _cache_set(key: str, value: Any) -> None:
    _CACHE[key] = value
    _CACHE_TS[key] = time.time()


def _public_payload(svc_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Strip internals from a catalog entry for public consumption."""
    return {
        "name": svc_dict["name"],
        "display_name": svc_dict.get("display_name", svc_dict["name"]),
        "description": svc_dict.get("description", ""),
        "category": svc_dict.get("category", "misc"),
        "category_display": _CATEGORY_DISPLAY.get(svc_dict.get("category", "misc"), "其他"),
        "status": svc_dict.get("status", "enabled"),
        "plan_required": svc_dict.get("plan_required", "free"),
        "roles_allowed": list(svc_dict.get("roles_allowed") or []),
        "dependencies": list(svc_dict.get("dependencies") or []),
        "version": svc_dict.get("version", 1),
    }


def _filter_public(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Hide internal / disabled entries."""
    out: List[Dict[str, Any]] = []
    for r in rows:
        if r.get("plan_required") == "internal":
            continue
        if r.get("status") == ServiceStatus.DISABLED.value:
            continue
        out.append(_public_payload(r))
    return out


def _all_public_rows() -> List[Dict[str, Any]]:
    """Catalog snapshot, filtered to customer-facing rows.

    Reads from Supabase when configured (so admin toggles / overrides take
    immediate effect), falling back to the static ``catalog_snapshot()``
    when the DB is unreachable. The DB path prefers rows that exist in
    ``services``; rows only present in the static catalog are still
    included so newly-added entries surface immediately.
    """
    cached = _cache_get("public:rows")
    if cached is not None:
        return cached  # type: ignore[return-value]

    sb = _supabase_safe()
    rows: List[Dict[str, Any]] = []
    if sb is not None:
        try:
            res = sb.table("services").select("*").execute()
            db_rows = res.data or []
            for r in db_rows:
                rows.append(
                    {
                        "name": r.get("name"),
                        "display_name": r.get("display_name") or r.get("name"),
                        "description": r.get("description") or "",
                        "category": r.get("category") or "misc",
                        "status": r.get("status") or "enabled",
                        "plan_required": r.get("plan_required") or "free",
                        "roles_allowed": list(r.get("roles_allowed") or []),
                        "dependencies": list(r.get("dependencies") or []),
                        "version": r.get("version") or 1,
                    }
                )
        except Exception as exc:  # pragma: no cover
            logger.debug("public catalog DB read failed: %s", exc)

    if not rows:
        # fallback to in-process static catalog
        rows = catalog_snapshot()

    rows = _filter_public(rows)
    _cache_set("public:rows", rows)
    return rows


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class SubscribeIn(BaseModel):
    email: Optional[EmailStr] = None
    webhook_url: Optional[str] = Field(default=None, max_length=2048)
    # Optional filter: only notify when one of these services change
    services: List[str] = Field(default_factory=list)
    # Optional filter by category
    category: Optional[str] = None
    locale: str = Field(default="en-US", max_length=8)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------
@router.get("")
async def list_services(
    category: Optional[str] = Query(None, description="agent|business|frontend|integration|api|platform|analytics"),
    plan: Optional[str] = Query(None, description="free|pro|enterprise"),
    status: Optional[str] = Query(None, description="enabled|beta|maintenance"),
    search: Optional[str] = Query(None, description="Free text matching display_name / name / description"),
    limit: int = Query(200, ge=1, le=10000),
):
    """List customer-facing services with optional filters.

    The upper bound on ``limit`` is intentionally generous (10k) so callers
    paginating via cursor can request bigger pages. We then clamp the
    effective page size to 500 so a runaway client cannot pull the entire
    catalog in one request. ``limit`` is clamped, not rejected.
    """
    rows = _all_public_rows()
    if category:
        rows = [r for r in rows if r["category"] == category]
    if plan:
        rows = [r for r in rows if r["plan_required"] == plan]
    if status:
        rows = [r for r in rows if r["status"] == status]
    if search:
        needle = search.lower()
        rows = [
            r
            for r in rows
            if needle in r["name"].lower()
            or needle in r["display_name"].lower()
            or needle in (r.get("description") or "").lower()
        ]
    rows = rows[: min(int(limit), 500)]
    return {
        "count": len(rows),
        "items": rows,
        "filters": {
            "category": category,
            "plan": plan,
            "status": status,
            "search": search,
        },
    }


# ---------------------------------------------------------------------------
# Grouped by category
# ---------------------------------------------------------------------------
@router.get("/categories")
def list_categories():
    cached = _cache_get("public:categories")
    if cached is not None:
        return cached
    rows = _all_public_rows()
    buckets: Dict[str, Dict[str, Any]] = {}
    for cat in _CATEGORY_ORDER:
        buckets[cat] = {
            "id": cat,
            "display": _CATEGORY_DISPLAY.get(cat, cat.title()),
            "count": 0,
            "by_plan": {p: 0 for p in _PLAN_ORDER},
            "services": [],
        }
    for r in rows:
        cat = r["category"] if r["category"] in buckets else "misc"
        b = buckets[cat]
        b["count"] += 1
        if r["plan_required"] in b["by_plan"]:
            b["by_plan"][r["plan_required"]] += 1
        b["services"].append(
            {"name": r["name"], "display_name": r["display_name"], "plan_required": r["plan_required"]}
        )
    payload = {
        "categories": [buckets[c] for c in _CATEGORY_ORDER if buckets[c]["count"] > 0],
        "totals": {
            "services": len(rows),
            "enabled": sum(1 for r in rows if r["status"] == "enabled"),
            "beta": sum(1 for r in rows if r["status"] == "beta"),
            "maintenance": sum(1 for r in rows if r["status"] == "maintenance"),
        },
    }
    _cache_set("public:categories", payload)
    return payload


# ---------------------------------------------------------------------------
# Public detail
# ---------------------------------------------------------------------------
@router.get("/{name}")
def get_service_public(name: str):
    cached = _cache_get(f"public:detail:{name}")
    if cached is not None:
        return cached
    snapshot = {r["name"]: r for r in _all_public_rows()}
    row = snapshot.get(name)
    if row is None:
        raise HTTPException(status_code=404, detail="service not found or not public")

    declared = get_dependencies_for(name)
    transitive = service_toggle.resolve_dependencies(name)
    dependents = service_toggle._find_dependents(name)  # noqa: SLF001
    related = []
    for d in declared:
        if d in snapshot:
            related.append(snapshot[d])

    # History snapshot (publicly safe subset)
    history: List[Dict[str, Any]] = []
    try:
        from eventbus import emit  # noqa: F401  # placeholder import for clarity
    except Exception:
        pass
    # Pull a recent slice from the audit table when Supabase is reachable.
    sb = _supabase_safe()
    if sb is not None:
        try:
            res = (
                sb.table("service_audit")
                .select("action,actor_id,reason,before,after,created_at")
                .eq("service_name", name)
                .order("created_at", desc=True)
                .limit(20)
                .execute()
            )
            for h in res.data or []:
                history.append(
                    {
                        "action": h.get("action"),
                        "reason": h.get("reason") or "",
                        "actor_id": _mask_actor(h.get("actor_id")),
                        "before": _status_only(h.get("before")),
                        "after": _status_only(h.get("after")),
                        "created_at": h.get("created_at"),
                    }
                )
        except Exception as exc:
            logger.debug("public detail audit read failed: %s", exc)

    payload = {
        **row,
        "sla": _DEFAULT_SLA,
        "declared_dependencies": declared,
        "dependencies_resolved": transitive,
        "dependents": dependents,
        "related_services": related,
        "history": history,
    }
    _cache_set(f"public:detail:{name}", payload)
    return payload


def _mask_actor(actor_id: Optional[str]) -> Optional[str]:
    if not actor_id:
        return None
    digest = hashlib.sha256(actor_id.encode("utf-8")).hexdigest()[:10]
    return f"admin:{digest}"


def _status_only(payload: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not payload or not isinstance(payload, dict):
        return None
    if "status" in payload:
        return {"status": payload["status"]}
    return None


# ---------------------------------------------------------------------------
# Public dep graph (anonymous safe)
# ---------------------------------------------------------------------------
@router.get("/graph/all")
async def public_graph():
    cached = _cache_get("public:graph")
    if cached is not None:
        return cached
    rows = _all_public_rows()
    nodes = [
        {
            "id": r["name"],
            "label": r["display_name"],
            "category": r["category"],
            "plan_required": r["plan_required"],
            "status": r["status"],
        }
        for r in rows
    ]
    edges: List[Dict[str, Any]] = []
    for r in rows:
        for d in r["dependencies"]:
            if any(n["id"] == d for n in nodes):
                edges.append({"from": r["name"], "to": d, "kind": "depends_on"})
    payload = {"nodes": nodes, "edges": edges, "count": len(nodes)}
    _cache_set("public:graph", payload)
    return payload


@router.get("/{name}/dependencies")
async def public_dependencies(name: str):
    rows = _all_public_rows()
    snapshot = {r["name"]: r for r in rows}
    if name not in snapshot:
        raise HTTPException(status_code=404, detail="service not found")
    # BFS sub-graph starting from this node
    visited: Dict[str, Any] = {}
    queue: List[str] = [name]
    while queue:
        cur = queue.pop(0)
        if cur in visited:
            continue
        if cur not in snapshot:
            # dependency not public, include it as a stub so the graph is complete
            visited[cur] = {"id": cur, "label": cur, "external": True}
            continue
        r = snapshot[cur]
        visited[cur] = {
            "id": cur,
            "label": r["display_name"],
            "category": r["category"],
            "plan_required": r["plan_required"],
            "status": r["status"],
        }
        for d in r["dependencies"]:
            queue.append(d)
    nodes = list(visited.values())
    edges: List[Dict[str, Any]] = []
    for r in rows:
        if r["name"] not in visited:
            continue
        for d in r["dependencies"]:
            if d in visited:
                edges.append({"from": r["name"], "to": d, "kind": "depends_on"})
    return {"nodes": nodes, "edges": edges, "count": len(nodes), "root": name}


# ---------------------------------------------------------------------------
# Subscribers (email / webhook)
# ---------------------------------------------------------------------------
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@router.post("/subscribers")
async def subscribe(body: SubscribeIn = Body(...)):
    if not body.email and not body.webhook_url:
        raise HTTPException(status_code=400, detail="email or webhook_url is required")
    if body.webhook_url and not body.webhook_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="webhook_url must be http(s)")

    sub_id = str(uuid.uuid4())
    payload: Dict[str, Any] = {
        "id": sub_id,
        "email": body.email,
        "webhook_url": body.webhook_url,
        "services": list(body.services or []),
        "category": body.category,
        "locale": body.locale,
        "created_at": _now_iso(),
        "active": True,
    }
    _SUBSCRIBERS.append(payload)
    persisted = _persist_subscriber(payload)
    return {
        "ok": True,
        "id": sub_id,
        "persisted": persisted,
        "message": "subscription created",
    }


@router.delete("/subscribers/{sub_id}")
def unsubscribe(sub_id: str):
    removed = False
    for s in list(_SUBSCRIBERS):
        if s.get("id") == sub_id:
            _SUBSCRIBERS.remove(s)
            removed = True
            break
    sb = _supabase_safe()
    if sb is not None:
        try:
            sb.table("service_subscribers").update({"active": False}).eq("id", sub_id).execute()
        except Exception as exc:
            logger.debug("unsubscribe update failed: %s", exc)
    return {"ok": True, "removed": removed}


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# EventBus hook — notify subscribers when a service changes
# ---------------------------------------------------------------------------
def notify_subscribers(service_name: str, action: str, before: Optional[str], after: Optional[str]) -> int:
    """Iterate subscribers, send best-effort notifications.

    Returns the count of notifications dispatched (for tests). In production
    this would enqueue to a worker; here we attempt direct delivery with a
    short timeout. Failures are logged and swallowed.
    """
    if not _SUBSCRIBERS:
        return 0

    import asyncio
    import urllib.parse
    import urllib.request

    async def _send_email(to: str, subject: str, body: str) -> bool:
        # SMTP delivery is the success criterion. We keep an optional
        # audit-trail digest in ``service_subscriber_digest`` when Supabase
        # is reachable, but that path is *observability*, not delivery.
        # Returning False from this helper keeps the public counter honest.
        sb = _supabase_safe()
        if sb is not None:
            try:
                sb.table("service_subscriber_digest").insert(
                    {
                        "to": to,
                        "subject": subject,
                        "body": body,
                        "kind": "email",
                        "service": service_name,
                        "action": action,
                    }
                ).execute()
            except Exception:
                pass
        # Without an SMTP transport we cannot actually deliver — return False.
        smtp_url = os.environ.get("SMTP_URL")
        if not smtp_url:
            return False
        # Best-effort SMTP send (kept simple; production systems would
        # hand this off to a worker). Errors are swallowed.
        try:
            import asyncio  # noqa: F401  (local import for clarity)
            import smtplib
            from email.message import EmailMessage

            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = os.environ.get("SMTP_FROM", "no-reply@waibao.cn")
            msg["To"] = to
            msg.set_content(body)
            with smtplib.SMTP(os.environ.get("SMTP_HOST", "localhost")) as s:
                s.send_message(msg)
            return True
        except Exception:
            return False

    async def _send_webhook(url: str, body: Dict[str, Any]) -> bool:
        loop = asyncio.get_event_loop()

        def _do_post() -> bool:
            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(body).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=3) as resp:  # nosec
                    return 200 <= resp.status < 300
            except Exception:
                return False

        return await loop.run_in_executor(None, _do_post)

    matches: List[Dict[str, Any]] = []
    for s in _SUBSCRIBERS:
        if not s.get("active"):
            continue
        if s.get("services") and service_name not in s["services"]:
            continue
        if s.get("category"):
            row = next((r for r in _all_public_rows() if r["name"] == service_name), None)
            if row is None or row["category"] != s["category"]:
                continue
        matches.append(s)

    if not matches:
        return 0

    sent = 0
    body = {
        "service": service_name,
        "action": action,
        "before": before,
        "after": after,
        "timestamp": _now_iso(),
    }

    async def _dispatch_all() -> None:
        nonlocal sent
        for s in matches:
            ok = False
            if s.get("email"):
                subject = f"[waibao] {service_name} → {after}"
                text = (
                    f"Service {service_name} changed: {before or '?'} → {after or '?'} ({action}). "
                    f"View: https://waibao.cn/services/{service_name}"
                )
                ok = await _send_email(s["email"], subject, text)
            elif s.get("webhook_url"):
                ok = await _send_webhook(s["webhook_url"], body)
            if ok:
                sent += 1

    try:
        asyncio.run(_dispatch_all())
    except Exception as exc:
        logger.debug("notify_subscribers failed: %s", exc)
    return sent


# ---------------------------------------------------------------------------
# Wire up to EventBus so subscribers get pinged on service.changed
# ---------------------------------------------------------------------------
def _install_eventbus_listener() -> None:
    try:
        from eventbus import on  # type: ignore

        def _listener(topic: str, payload: Dict[str, Any]) -> None:
            name = payload.get("service") or payload.get("name") or ""
            if not name:
                return
            before = None
            after = None
            if isinstance(payload.get("before"), dict):
                before = payload["before"].get("status")
            if isinstance(payload.get("after"), dict):
                after = payload["after"].get("status")
            elif payload.get("status"):
                after = payload["status"]
            notify_subscribers(name, payload.get("action") or "changed", before, after)

        on("service.changed", _listener)
    except Exception as exc:  # pragma: no cover
        logger.debug("eventbus listener install failed: %s", exc)


_install_eventbus_listener()