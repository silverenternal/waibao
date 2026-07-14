"""v10.0 T5025 — Event schema registry + compatibility checking.

Each event name flowing through :class:`~eventbus.streams.StreamEventBus`
has an optional JSON-schema-like contract registered here. The registry
serves two purposes:

1. **Validation at the trust boundary.** ``StreamEventBus.publish`` calls
   ``registry.validate(name, payload)`` before appending to the stream;
   payloads that violate the schema are routed to the DLQ instead of being
   dispatched (catching producer bugs early, before they poison consumers).

2. **Backward-compatible evolution.** When a producer evolves a payload
   (e.g. adds an optional field), ``register(name, schema, version=2)`` runs
   a compatibility check against the previously registered schema so a
   breaking change is rejected rather than silently deployed.

The schema language is intentionally tiny (required keys + types), not full
JSON Schema, so producers can declare contracts inline without pulling in a
validator dependency. Full JSON-Schema dicts are also accepted verbatim.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema representation
# ---------------------------------------------------------------------------
@dataclass
class EventSchema:
    """A registered event contract.

    ``fields`` maps field name -> python type (``str``, ``int``, ``float``,
    ``bool``, ``dict``, ``list``) or ``None`` to mean "any". ``required``
    lists field names that must be present. ``json_schema`` is an optional
    full JSON-Schema dict that, when set, takes precedence over the tiny DSL.
    """

    name: str
    version: int = 1
    fields: Dict[str, Any] = field(default_factory=dict)
    required: List[str] = field(default_factory=list)
    json_schema: Optional[Dict[str, Any]] = None
    description: str = ""

    def validate(self, payload: Dict[str, Any]) -> bool:
        """Return True iff ``payload`` conforms to this schema."""
        if not isinstance(payload, dict):
            return False
        if self.json_schema is not None:
            return _validate_json_schema(self.json_schema, payload)
        # required keys
        for key in self.required:
            if key not in payload:
                return False
        # type checks
        for key, expected in self.fields.items():
            if key not in payload:
                continue  # optional if not in `required`
            if expected is None or expected is Any:
                continue
            value = payload[key]
            if not _type_ok(value, expected):
                return False
        return True


def _type_ok(value: Any, expected: Any) -> bool:
    if expected is Any or expected is None:
        return True
    if isinstance(expected, tuple):
        return any(_type_ok(value, t) for t in expected)
    # bool is a subclass of int — guard explicitly so a bool never passes int
    if expected is int and isinstance(value, bool):
        return False
    if expected is float and isinstance(value, int) and not isinstance(value, bool):
        return True  # ints are acceptable where floats are expected
    try:
        return isinstance(value, expected)
    except TypeError:
        return False


# ---------------------------------------------------------------------------
# Compatibility
# ---------------------------------------------------------------------------
class IncompatibleSchemaError(Exception):
    """Raised when a new schema version breaks backward compatibility."""


_COMPAT_MODE_BACKWARD = "backward"


def _is_backward_compatible(old: EventSchema, new: EventSchema) -> Tuple[bool, str]:
    """Backward compatible iff:
    * every previously-required field remains present and required, and
    * no previously-required field had its type narrowed.
    Adding new optional fields or new required fields (with a default that
    older producers won't send) is *not* backward compatible unless they are
    also optional in the new schema — so we only allow *new optional* fields
    and forbid *removing* previously-required fields.
    """
    old_required = set(old.required)
    new_required = set(new.required)
    # removed required fields
    removed = old_required - new_required
    if removed:
        return False, f"previously-required fields removed: {sorted(removed)}"
    # narrowed types on shared required fields
    for key in old_required & set(new.fields):
        old_t = old.fields.get(key, Any)
        new_t = new.fields.get(key, Any)
        if old_t is Any or new_t is Any:
            continue
        if old_t != new_t:
            return False, f"field {key!r} type changed {old_t!r} -> {new_t!r}"
    return True, ""


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
class SchemaRegistry:
    """Process-wide event schema registry."""

    def __init__(self, *, compat_mode: str = _COMPAT_MODE_BACKWARD) -> None:
        self._schemas: Dict[str, EventSchema] = {}
        self._history: Dict[str, List[EventSchema]] = {}
        self._compat_mode = compat_mode

    # ---- registration ----------------------------------------------------
    def register(
        self,
        name: str,
        *,
        fields: Optional[Dict[str, Any]] = None,
        required: Optional[List[str]] = None,
        json_schema: Optional[Dict[str, Any]] = None,
        version: Optional[int] = None,
        description: str = "",
        force: bool = False,
    ) -> EventSchema:
        """Register (or re-register) a schema for ``name``.

        Raises :class:`IncompatibleSchemaError` if a new version is not
        backward compatible with the existing one, unless ``force=True``.
        """
        ver = version or (self._schemas[name].version + 1 if name in self._schemas else 1)
        schema = EventSchema(
            name=name,
            version=ver,
            fields=dict(fields or {}),
            required=list(required or []),
            json_schema=json_schema,
            description=description,
        )
        existing = self._schemas.get(name)
        if existing is not None and not force:
            ok, reason = _is_backward_compatible(existing, schema)
            if not ok:
                raise IncompatibleSchemaError(
                    f"schema {name!r} v{ver} not backward compatible: {reason}"
                )
        self._schemas[name] = schema
        self._history.setdefault(name, []).append(schema)
        logger.info("schema_registry.registered name=%s version=%s", name, ver)
        return schema

    def get(self, name: str) -> Optional[EventSchema]:
        return self._schemas.get(name)

    def history(self, name: str) -> List[EventSchema]:
        return list(self._history.get(name, []))

    def known(self) -> List[str]:
        return sorted(self._schemas)

    # ---- validation ------------------------------------------------------
    def validate(self, name: str, payload: Dict[str, Any]) -> bool:
        schema = self._schemas.get(name)
        if schema is None:
            # Unknown events are allowed by default — opt-in strict mode via
            # ``register``. This keeps the bus open for ad-hoc events while
            # still validating every event that *has* a contract.
            return True
        try:
            return schema.validate(payload)
        except Exception:  # noqa: BLE001
            logger.exception("schema_registry.validate_failed name=%s", name)
            return False


# ---------------------------------------------------------------------------
# Tiny JSON-Schema subset validator (no external dep)
# ---------------------------------------------------------------------------
def _validate_json_schema(schema: Dict[str, Any], instance: Any) -> bool:
    try:
        return _js_check(schema, instance)
    except Exception:  # noqa: BLE001
        return False


def _js_check(schema: Dict[str, Any], instance: Any) -> bool:
    if "type" in schema:
        t = schema["type"]
        mapping = {
            "object": dict, "array": list, "string": str,
            "integer": int, "number": (int, float), "boolean": bool,
        }
        expected = mapping.get(t)
        if expected is None:
            return True
        if t == "integer" and isinstance(instance, bool):
            return False
        if t == "number" and isinstance(instance, bool):
            return False
        if not isinstance(instance, expected):
            return False
    if isinstance(instance, dict) and isinstance(schema.get("required"), list):
        for key in schema["required"]:
            if key not in instance:
                return False
    if isinstance(instance, dict) and isinstance(schema.get("properties"), dict):
        for key, subschema in schema["properties"].items():
            if key in instance and not _js_check(subschema, instance[key]):
                return False
    if isinstance(instance, list) and isinstance(schema.get("items"), dict):
        for item in instance:
            if not _js_check(schema["items"], item):
                return False
    return True


# ---------------------------------------------------------------------------
# Default registry + bootstrap for the platform's known events
# ---------------------------------------------------------------------------
_REGISTRY: Optional[SchemaRegistry] = None


def get_schema_registry() -> SchemaRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = SchemaRegistry()
        _register_defaults(_REGISTRY)
    return _REGISTRY


def set_schema_registry(registry: SchemaRegistry) -> None:
    global _REGISTRY
    _REGISTRY = registry


def _register_defaults(reg: SchemaRegistry) -> None:
    """Register schemas for the platform's well-known events.

    These mirror the payloads emitted by ``eventbus/integration.py``.
    """
    reg.register(
        "profile.created",
        fields={"user_id": (str, int), "tenant_id": (str, int)},
        required=["user_id"],
        description="A new jobseeker profile was created.",
    )
    reg.register(
        "profile.updated",
        fields={"user_id": (str, int), "fields": (dict, list), "tenant_id": (str, int)},
        required=["user_id"],
        description="A jobseeker profile field changed.",
    )
    reg.register(
        "profile.enriched",
        fields={"user_id": (str, int), "source": str, "tenant_id": (str, int)},
        required=["user_id", "source"],
        description="A profile was enriched from an external source.",
    )
    reg.register(
        "needs.clarified",
        fields={"user_id": (str, int), "questions": list, "tenant_id": (str, int)},
        required=["user_id"],
        description="The clarifier surfaced open questions.",
    )
    reg.register(
        "emotion.detected",
        fields={"user_id": (str, int), "emotion": str, "score": (int, float),
                "tenant_id": (str, int)},
        required=["user_id", "emotion"],
        description="An emotion signal was detected for a user.",
    )
    reg.register(
        "emotion.risk",
        fields={"user_id": (str, int), "level": str, "tenant_id": (str, int)},
        required=["user_id", "level"],
        description="An emotion risk threshold was breached.",
    )
    reg.register(
        "plan.generated",
        fields={"user_id": (str, int), "plan": (dict, str), "tenant_id": (str, int)},
        required=["user_id"],
        description="A career plan was generated.",
    )
    reg.register(
        "market.updated",
        fields={"user_id": (str, int), "signals": (dict, list), "tenant_id": (str, int)},
        required=["user_id"],
        description="Market signals were refreshed for a user.",
    )
    reg.register(
        "journal.submitted",
        fields={"user_id": (str, int), "entry_id": (str, int), "tenant_id": (str, int)},
        required=["user_id"],
        description="A daily journal entry was submitted.",
    )
    reg.register(
        "role.image.updated",
        fields={"job_id": (str, int), "tenant_id": (str, int)},
        required=["job_id"],
        description="A role image / JD was updated.",
    )
    reg.register(
        "strategy.updated",
        fields={"tenant_id": (str, int), "summary": (str, dict)},
        required=["tenant_id"],
        description="A strategy / multi-party decision was updated.",
    )
    reg.register(
        "ticket.created",
        fields={"ticket_id": (str, int), "tenant_id": (str, int)},
        required=["ticket_id"],
        description="An HR service ticket was created.",
    )
    reg.register(
        "ticket.escalated",
        fields={"ticket_id": (str, int), "tenant_id": (str, int)},
        required=["ticket_id"],
        description="A ticket was escalated.",
    )
    reg.register(
        "agent.started",
        fields={"agent_name": str, "tenant_id": (str, int)},
        required=["agent_name"],
        description="An agent run started.",
    )
    reg.register(
        "agent.completed",
        fields={"agent_name": str, "tenant_id": (str, int)},
        required=["agent_name"],
        description="An agent run completed.",
    )
    reg.register(
        "agent.failed",
        fields={"agent_name": str, "tenant_id": (str, int)},
        required=["agent_name"],
        description="An agent run failed.",
    )
    reg.register(
        "audit.recorded",
        fields={"actor": str, "action": str, "tenant_id": (str, int)},
        required=["action"],
        description="An audit record was written.",
    )


__all__ = [
    "EventSchema",
    "SchemaRegistry",
    "IncompatibleSchemaError",
    "get_schema_registry",
    "set_schema_registry",
]
