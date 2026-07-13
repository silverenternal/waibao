"""T2901 — Session manager.

After a successful SSO callback we mint a short-lived *application* JWT
(``access_token``, 15 min) plus a long-lived *refresh token* (30 d) the
client can use to rotate the access token. The refresh token is a random
opaque string stored in a small in-process table (in production this
should live in Redis / a database — see :class:`SessionStore`).

The split — short JWT for statelessness, long refresh token for UX — is
the de-facto SaaS pattern and matches what the NextAuth frontend expects
when wiring up the auto-refresh flow.
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from jose import JWTError, jwt

logger = logging.getLogger("recruittech.auth.session")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ACCESS_TOKEN_TTL = int(os.getenv("SSO_ACCESS_TOKEN_TTL", "900"))        # 15 min
REFRESH_TOKEN_TTL = int(os.getenv("SSO_REFRESH_TOKEN_TTL", str(30 * 24 * 60 * 60)))  # 30 d

JWT_SECRET = os.getenv(
    "SSO_JWT_SECRET",
    os.getenv("SUPABASE_JWT_SECRET", "super-secret-jwt-token-with-at-least-32-characters-long"),
)
JWT_ALG = "HS256"
JWT_ISSUER = "waibao-sso"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SSOSession:
    """A signed session bound to a particular user / IdP."""

    user_id: str
    email: str
    provider: str
    organisation_id: Optional[str] = None
    role: str = "member"
    groups: list[str] = field(default_factory=list)
    access_token: str = ""
    access_token_expires_at: float = 0.0
    refresh_token: str = ""
    refresh_token_expires_at: float = 0.0
    issued_at: float = field(default_factory=lambda: time.time())
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "email": self.email,
            "provider": self.provider,
            "organisation_id": self.organisation_id,
            "role": self.role,
            "groups": list(self.groups),
            "access_token": self.access_token,
            "access_token_expires_at": self.access_token_expires_at,
            "refresh_token": self.refresh_token,
            "refresh_token_expires_at": self.refresh_token_expires_at,
            "issued_at": self.issued_at,
        }


class SessionStore:
    """In-memory refresh-token store. Thread-safe.

    For production this is typically backed by Redis; the interface is
    intentionally narrow (3 ops) so a Redis-backed implementation is a
    drop-in replacement.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._refresh_to_session: Dict[str, str] = {}
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def put(self, session: SSOSession) -> None:
        with self._lock:
            # If this session_id already exists with a different refresh
            # token, drop the old mapping so the *old* refresh token can
            # never be used again.
            old = self._sessions.get(session.session_id)
            if old and old["refresh_token_hash"] != _hash(session.refresh_token):
                # We don't know which refresh token was previously bound
                # (only its hash), so iterate the mapping.
                stale = [
                    rt for rt, sid in self._refresh_to_session.items()
                    if sid == session.session_id and rt != session.refresh_token
                ]
                for rt in stale:
                    self._refresh_to_session.pop(rt, None)
            self._refresh_to_session[session.refresh_token] = session.session_id
            self._sessions[session.session_id] = {
                "user_id": session.user_id,
                "email": session.email,
                "provider": session.provider,
                "organisation_id": session.organisation_id,
                "role": session.role,
                "groups": list(session.groups),
                "refresh_token_hash": _hash(session.refresh_token),
                "refresh_token_expires_at": session.refresh_token_expires_at,
                "access_token_expires_at": session.access_token_expires_at,
                "issued_at": session.issued_at,
            }

    def get_by_refresh(self, refresh_token: str) -> Optional[SSOSession]:
        with self._lock:
            sid = self._refresh_to_session.get(refresh_token)
            if not sid:
                return None
            data = self._sessions.get(sid)
        if not data:
            return None
        if data["refresh_token_expires_at"] < time.time():
            self.revoke(refresh_token)
            return None
        if not _ct_eq(data["refresh_token_hash"], _hash(refresh_token)):
            return None
        return SSOSession(
            user_id=data["user_id"],
            email=data["email"],
            provider=data["provider"],
            organisation_id=data["organisation_id"],
            role=data["role"],
            groups=list(data["groups"]),
            refresh_token=refresh_token,
            refresh_token_expires_at=data["refresh_token_expires_at"],
            access_token_expires_at=data["access_token_expires_at"],
            issued_at=data["issued_at"],
            session_id=sid,
        )

    def rotate(self, old_refresh: str, new_session: SSOSession) -> bool:
        """Atomically replace the refresh token bound to ``new_session.session_id``.

        The new session must reuse the *same* session_id — we just swap the
        refresh token + access token. After the swap the old refresh token
        is no longer valid because its hash no longer matches.
        """
        with self._lock:
            if self._refresh_to_session.get(old_refresh) != new_session.session_id:
                return False
            self._refresh_to_session.pop(old_refresh, None)
        # ``put`` will detect the changed refresh_token_hash and atomically
        # drop any stale mappings pointing at this session_id.
        self.put(new_session)
        return True

    def revoke(self, refresh_token: str) -> None:
        with self._lock:
            sid = self._refresh_to_session.pop(refresh_token, None)
            if sid:
                self._sessions.pop(sid, None)

    def __len__(self) -> int:  # pragma: no cover - debug helper
        with self._lock:
            return len(self._sessions)


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class SessionManager:
    """Mint, refresh and revoke SSO sessions."""

    def __init__(self, store: Optional[SessionStore] = None) -> None:
        self.store = store or SessionStore()

    # -- public API -----------------------------------------------------

    def create(
        self,
        *,
        user_id: str,
        email: str,
        provider: str,
        role: str = "member",
        groups: Optional[list[str]] = None,
        organisation_id: Optional[str] = None,
    ) -> SSOSession:
        now = time.time()
        access = self._mint_access_token(
            user_id=user_id, email=email, provider=provider,
            role=role, organisation_id=organisation_id,
        )
        refresh = secrets.token_urlsafe(48)
        session = SSOSession(
            user_id=user_id,
            email=email,
            provider=provider,
            organisation_id=organisation_id,
            role=role,
            groups=list(groups or []),
            access_token=access,
            access_token_expires_at=now + ACCESS_TOKEN_TTL,
            refresh_token=refresh,
            refresh_token_expires_at=now + REFRESH_TOKEN_TTL,
        )
        self.store.put(session)
        return session

    def refresh(self, refresh_token: str) -> Optional[SSOSession]:
        old = self.store.get_by_refresh(refresh_token)
        if not old:
            return None
        # Rotate: mint a brand-new access token AND a brand-new refresh
        # token bound to the *same* session_id so we keep a single
        # row but invalidate the leaked refresh token.
        now = time.time()
        access = self._mint_access_token(
            user_id=old.user_id, email=old.email, provider=old.provider,
            role=old.role, organisation_id=old.organisation_id,
        )
        new_refresh = secrets.token_urlsafe(48)
        rotated = SSOSession(
            user_id=old.user_id,
            email=old.email,
            provider=old.provider,
            organisation_id=old.organisation_id,
            role=old.role,
            groups=list(old.groups),
            access_token=access,
            access_token_expires_at=now + ACCESS_TOKEN_TTL,
            refresh_token=new_refresh,
            refresh_token_expires_at=now + REFRESH_TOKEN_TTL,
            issued_at=now,
            session_id=old.session_id,
        )
        self.store.rotate(refresh_token, rotated)
        return rotated

    def revoke(self, refresh_token: str) -> None:
        self.store.revoke(refresh_token)

    def verify_access_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Return the JWT claims, or ``None`` on failure."""
        try:
            return jwt.decode(
                token,
                JWT_SECRET,
                algorithms=[JWT_ALG],
                options={"verify_aud": False},
                issuer=JWT_ISSUER,
            )
        except JWTError as exc:
            logger.warning("Access token verify failed: %s", exc)
            return None

    # -- internals ------------------------------------------------------

    def _mint_access_token(
        self,
        *,
        user_id: str,
        email: str,
        provider: str,
        role: str,
        organisation_id: Optional[str],
    ) -> str:
        now = int(time.time())
        claims = {
            "iss": JWT_ISSUER,
            "sub": user_id,
            "email": email,
            "provider": provider,
            "role": role,
            "organisation_id": organisation_id,
            "iat": now,
            "exp": now + ACCESS_TOKEN_TTL,
            "jti": str(uuid.uuid4()),
        }
        return jwt.encode(claims, JWT_SECRET, algorithm=JWT_ALG)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _ct_eq(a: str, b: str) -> bool:
    """Constant-time string comparison (avoids timing side-channels)."""
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a, b):
        result |= ord(x) ^ ord(y)
    return result == 0


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    global _manager
    if _manager is None:
        _manager = SessionManager()
    return _manager


__all__ = [
    "ACCESS_TOKEN_TTL",
    "REFRESH_TOKEN_TTL",
    "SSOSession",
    "SessionStore",
    "SessionManager",
    "get_session_manager",
]
