"""v8.0 T3501 — Service Catalog data classes.

Pure dataclasses / enums shared by service_toggle, service_registry,
feature_access and admin_services API. No I/O here — keep this module
small so it can be imported anywhere without side effects.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional


class ServiceStatus(str, Enum):
    """Lifecycle status of a registered service."""

    ENABLED = "enabled"
    DISABLED = "disabled"
    MAINTENANCE = "maintenance"
    BETA = "beta"

    @classmethod
    def coerce(cls, value: Any) -> "ServiceStatus":
        if isinstance(value, cls):
            return value
        s = str(value).lower().strip()
        for m in cls:
            if m.value == s:
                return m
        raise ValueError(f"Invalid ServiceStatus: {value!r}")


class ServiceCategory(str, Enum):
    """High-level grouping for the catalog UI."""

    AGENT = "agent"
    API = "api"
    BUSINESS = "business"
    INTEGRATION = "integration"
    PLATFORM = "platform"
    FRONTEND = "frontend"
    ANALYTICS = "analytics"
    MISC = "misc"


class PlanTier(str, Enum):
    """Subscription plan required to access a service."""

    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"
    INTERNAL = "internal"  # not exposed to customers

    @classmethod
    def rank(cls, value: Any) -> int:
        """Comparable rank — higher tier wins."""
        order = [cls.FREE, cls.PRO, cls.ENTERPRISE, cls.INTERNAL]
        try:
            return order.index(cls.coerce(value))
        except ValueError:
            return 0

    @classmethod
    def coerce(cls, value: Any) -> "PlanTier":
        if isinstance(value, cls):
            return value
        s = str(value).lower().strip()
        for m in cls:
            if m.value == s:
                return m
        return cls.FREE


# Plan ordering used when evaluating "does the customer's plan cover plan_required?"
_PLAN_RANK = {
    PlanTier.FREE.value: 0,
    PlanTier.PRO.value: 1,
    PlanTier.ENTERPRISE.value: 2,
    PlanTier.INTERNAL.value: 3,
}


@dataclass
class Service:
    """A registered service entry.

    The combination of these fields determines whether the service is
    reachable for a (org_id, plan, role) tuple at request time.
    """

    name: str
    display_name: str
    description: str = ""
    category: ServiceCategory = ServiceCategory.MISC
    status: ServiceStatus = ServiceStatus.ENABLED
    plan_required: PlanTier = PlanTier.FREE
    roles_allowed: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    version: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def __post_init__(self) -> None:
        if not self.name or not isinstance(self.name, str):
            raise ValueError("Service.name must be a non-empty string")
        if len(self.name) < 2 or len(self.name) > 64:
            raise ValueError("Service.name must be 2-64 chars")
        # Coerce enum-like fields
        if isinstance(self.category, str):
            self.category = ServiceCategory(self.category)
        if isinstance(self.status, str):
            self.status = ServiceStatus(self.status)
        if isinstance(self.plan_required, str):
            self.plan_required = PlanTier(self.plan_required)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        d["category"] = self.category.value
        d["plan_required"] = self.plan_required.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Service":
        """Build from a database / API dict."""
        if "category" in data and isinstance(data["category"], str):
            data = {**data, "category": ServiceCategory(data["category"])}
        if "status" in data and isinstance(data["status"], str):
            data = {**data, "status": ServiceStatus(data["status"])}
        if "plan_required" in data and isinstance(data["plan_required"], str):
            data = {**data, "plan_required": PlanTier(data["plan_required"])}
        # metadata may be missing
        if "metadata" not in data:
            data = {**data, "metadata": {}}
        return cls(**data)


@dataclass
class ServiceOverride:
    """Per-org override (highest priority)."""

    org_id: str
    service_name: str
    override_status: ServiceStatus
    reason: str = ""
    expires_at: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[str] = None

    def __post_init__(self) -> None:
        if isinstance(self.override_status, str):
            self.override_status = ServiceStatus(self.override_status)

    def is_expired(self, now_iso: Optional[str] = None) -> bool:
        if not self.expires_at:
            return False
        # simple lex compare on ISO strings (UTC Z-suffixed) is enough
        return (self.expires_at or "") < (now_iso or "9999")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "org_id": self.org_id,
            "service_name": self.service_name,
            "override_status": self.override_status.value,
            "reason": self.reason,
            "expires_at": self.expires_at,
            "created_by": self.created_by,
            "created_at": self.created_at,
        }


def plan_covers(user_plan: Any, required: Any) -> bool:
    """Return True if `user_plan` is at least as high as `required`."""
    return _PLAN_RANK.get(str(user_plan), 0) >= _PLAN_RANK.get(str(required), 0)
