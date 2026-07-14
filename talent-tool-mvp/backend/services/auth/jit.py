"""T2901 — Just-In-Time (JIT) account provisioning.

When a user lands in the system for the first time via SSO, we:

  1. Look them up by ``(provider, subject)``.
  2. If they don't exist, we create a new ``users`` row, add them to a
     default organisation, and (optionally) link their SSO identity to
     existing accounts by email match.
  3. If they do exist, we refresh their profile from the latest IdP
     claims (display name, picture, group membership).

The provisioner is deliberately a *protocol* (interface) so the same
code path is reusable in tests, in the live FastAPI app, and in admin
tools.
"""

from __future__ import annotations

import logging
import os
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol

from services.auth.sso import SSOCallbackClaims

logger = logging.getLogger("recruittech.auth.jit")


# ---------------------------------------------------------------------------
# Storage interface
# ---------------------------------------------------------------------------

class UserStore(Protocol):
    """Minimal storage contract used by :class:`JITProvisioner`."""

    def get_by_sso(self, provider: str, subject: str) -> Optional[Dict[str, Any]]: ...
    def get_by_email(self, email: str) -> Optional[Dict[str, Any]]: ...
    def insert_user(self, user: Dict[str, Any]) -> Dict[str, Any]: ...
    def update_user(self, user_id: str, patch: Dict[str, Any]) -> Dict[str, Any]: ...
    def insert_identity(self, identity: Dict[str, Any]) -> Dict[str, Any]: ...
    def get_or_create_organisation(
        self, slug: str, *, name: str, default_role: str = "member"
    ) -> Dict[str, Any]: ...
    def add_membership(
        self, user_id: str, organisation_id: str, role: str
    ) -> Dict[str, Any]: ...


# ---------------------------------------------------------------------------
# In-memory store (used by unit tests and as the default dev backend)
# ---------------------------------------------------------------------------

class InMemoryUserStore:
    """Thread-safe, in-process user store.

    Not for production — the real implementation will live behind the
    Supabase / Postgres RLS layer (T2601). This class exists so the JIT
    logic is unit-testable without external services.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._users: Dict[str, Dict[str, Any]] = {}
        self._by_email: Dict[str, str] = {}
        self._identities: Dict[str, Dict[str, Any]] = {}
        self._organisations: Dict[str, Dict[str, Any]] = {}
        self._memberships: List[Dict[str, Any]] = []

    # ---- lookups ----

    def get_by_sso(self, provider: str, subject: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            for ident in self._identities.values():
                if ident["provider"] == provider and ident["subject"] == subject:
                    return self._users.get(ident["user_id"])
        return None

    def get_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            uid = self._by_email.get(email.lower())
            if uid:
                return self._users.get(uid)
        return None

    # ---- writes ----

    def insert_user(self, user: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            if "id" not in user:
                user["id"] = str(uuid.uuid4())
            user.setdefault("created_at", datetime.utcnow().isoformat())
            user["updated_at"] = datetime.utcnow().isoformat()
            self._users[user["id"]] = dict(user)
            self._by_email[user["email"].lower()] = user["id"]
            return dict(user)

    def update_user(self, user_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            current = self._users.get(user_id)
            if not current:
                raise KeyError(f"Unknown user_id: {user_id}")
            current.update(patch)
            current["updated_at"] = datetime.utcnow().isoformat()
            return dict(current)

    def insert_identity(self, identity: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            identity = dict(identity)
            identity.setdefault("id", str(uuid.uuid4()))
            identity.setdefault("created_at", datetime.utcnow().isoformat())
            self._identities[identity["id"]] = identity
            return dict(identity)

    def get_or_create_organisation(
        self, slug: str, *, name: str, default_role: str = "member"
    ) -> Dict[str, Any]:
        with self._lock:
            for org in self._organisations.values():
                if org["slug"] == slug:
                    return dict(org)
            org = {
                "id": str(uuid.uuid4()),
                "slug": slug,
                "name": name,
                "default_role": default_role,
                "created_at": datetime.utcnow().isoformat(),
            }
            self._organisations[org["id"]] = org
            return dict(org)

    def add_membership(
        self, user_id: str, organisation_id: str, role: str
    ) -> Dict[str, Any]:
        with self._lock:
            for m in self._memberships:
                if m["user_id"] == user_id and m["organisation_id"] == organisation_id:
                    return dict(m)
            m = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "organisation_id": organisation_id,
                "role": role,
                "created_at": datetime.utcnow().isoformat(),
            }
            self._memberships.append(m)
            return dict(m)

    # ---- debug ----

    def stats(self) -> Dict[str, int]:  # pragma: no cover - debug only
        with self._lock:
            return {
                "users": len(self._users),
                "identities": len(self._identities),
                "organisations": len(self._organisations),
                "memberships": len(self._memberships),
            }


# ---------------------------------------------------------------------------
# Provisioner
# ---------------------------------------------------------------------------

@dataclass
class JITResult:
    user: Dict[str, Any]
    organisation: Dict[str, Any]
    identity: Dict[str, Any]
    created: bool
    linked_by_email: bool = False
    groups: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user": dict(self.user),
            "organisation": dict(self.organisation),
            "identity": dict(self.identity),
            "created": self.created,
            "linked_by_email": self.linked_by_email,
            "groups": list(self.groups),
        }


class JITProvisioner:
    """Idempotent Just-In-Time provisioner.

    The provisioner is *stateless* — it only knows about the storage
    backend. This means it can be invoked concurrently (e.g. from the
    callback handler running on multiple workers) without coordination.
    """

    def __init__(
        self,
        store: UserStore,
        *,
        default_org_slug: Optional[str] = None,
        default_org_name: Optional[str] = None,
        default_org_role: str = "member",
        link_by_email: bool = False,
        allowed_domains: Optional[list[str]] = None,
    ) -> None:
        """v10.0 T5018 — JIT governance hardening.

        ``link_by_email`` now defaults to **False**.  Linking an SSO identity
        to a pre-existing account purely by email match is an account-takeover
        vector (register the victim's email at a rogue IdP, then SSO in).
        Operators who understand the risk and want the convenience can opt
        back in by setting ``SSO_JIT_LINK_BY_EMAIL=1`` or passing
        ``link_by_email=True``.

        ``allowed_domains`` is an optional email-domain allow-list (e.g.
        ``["acme.com"]``).  When set, JIT provisioning refuses any email whose
        domain is not on the list — so a private deployment only ever admits
        its own workforce.  Defaults to the ``SSO_JIT_ALLOWED_DOMAINS`` env
        var (comma-separated) or ``None`` (no restriction).
        """
        self.store = store
        self.default_org_slug = default_org_slug or os.getenv(
            "SSO_DEFAULT_ORG_SLUG", "default"
        )
        self.default_org_name = default_org_name or os.getenv(
            "SSO_DEFAULT_ORG_NAME", "RecruitTech"
        )
        self.default_org_role = default_org_role
        # T5018: default off; env opt-in.
        self.link_by_email = link_by_email or os.getenv(
            "SSO_JIT_LINK_BY_EMAIL", "0"
        ).lower() in ("1", "true", "yes")
        env_domains = os.getenv("SSO_JIT_ALLOWED_DOMAINS", "").strip()
        self.allowed_domains: Optional[set[str]] = (
            allowed_domains
            if allowed_domains is not None
            else ({d.strip().lower().lstrip("@") for d in env_domains.split(",") if d.strip()}
                  if env_domains else None)
        )

    def provision(self, claims: SSOCallbackClaims) -> JITResult:
        """Run the JIT flow and return a :class:`JITResult`."""
        if not claims.email or not claims.subject:
            raise ValueError("Claims missing email/subject")
        # T5018: enforce the email-domain allow-list before any provisioning.
        if self.allowed_domains is not None:
            domain = claims.email.rsplit("@", 1)[-1].lower() if "@" in claims.email else ""
            if domain not in self.allowed_domains:
                raise PermissionError(
                    f"email domain '{domain}' not in JIT allowed domains"
                )

        # 1. Identity → user
        user = self.store.get_by_sso(claims.provider, claims.subject)
        created = False
        linked_by_email = False

        if user is None and self.link_by_email:
            user = self.store.get_by_email(claims.email)
            linked_by_email = user is not None

        if user is None:
            user = self.store.insert_user(self._user_from_claims(claims))
            created = True
        else:
            patch = self._patch_from_claims(claims)
            if patch:
                user = self.store.update_user(user["id"], patch)

        # 2. Identity row
        identity = self.store.insert_identity({
            "user_id": user["id"],
            "provider": claims.provider,
            "subject": claims.subject,
            "email": claims.email,
        })

        # 3. Default organisation + membership
        org = self.store.get_or_create_organisation(
            self.default_org_slug,
            name=self.default_org_name,
            default_role=self.default_org_role,
        )
        self.store.add_membership(
            user["id"], org["id"], self.default_org_role
        )

        return JITResult(
            user=user,
            organisation=org,
            identity=identity,
            created=created,
            linked_by_email=linked_by_email,
            groups=list(claims.groups),
        )

    # -- helpers -------------------------------------------------------

    def _user_from_claims(self, claims: SSOCallbackClaims) -> Dict[str, Any]:
        name = claims.display_name or (
            f"{claims.given_name or ''} {claims.family_name or ''}".strip() or claims.email
        )
        return {
            "email": claims.email.lower(),
            "display_name": name,
            "given_name": claims.given_name,
            "family_name": claims.family_name,
            "picture": claims.picture,
            "role": self.default_org_role,
            "is_active": True,
            "email_verified": claims.email_verified,
            "sso_provider": claims.provider,
            "sso_subject": claims.subject,
        }

    def _patch_from_claims(self, claims: SSOCallbackClaims) -> Dict[str, Any]:
        patch: Dict[str, Any] = {}
        if claims.given_name and claims.given_name != claims.subject:
            patch["given_name"] = claims.given_name
        if claims.family_name:
            patch["family_name"] = claims.family_name
        if claims.picture:
            patch["picture"] = claims.picture
        if claims.display_name:
            patch["display_name"] = claims.display_name
        return patch


# ---------------------------------------------------------------------------
# Singleton (with shared in-memory store; production swaps this for a
# Supabase/Postgres-backed implementation).
# ---------------------------------------------------------------------------

_store: Optional[InMemoryUserStore] = None
_provisioner: Optional[JITProvisioner] = None


def get_jit_provisioner() -> JITProvisioner:
    global _store, _provisioner
    if _provisioner is None:
        _store = InMemoryUserStore()
        _provisioner = JITProvisioner(_store)
    return _provisioner


__all__ = [
    "UserStore",
    "InMemoryUserStore",
    "JITResult",
    "JITProvisioner",
    "get_jit_provisioner",
]
