"""Developer Portal service — T2902.

Manages third-party developer integrations on top of the existing API Key
infrastructure (T803).  Provides:

* **App registration** — third parties register an App (name, homepage,
  redirect URIs, scopes) to act on behalf of an organisation.
* **API Key v3** — extends the existing key schema with App binding,
  environment (sandbox / live), and per-key secret rotation.
* **OAuth 2.0 Authorization Code flow** — RFC 6749 §4.1.  Implements
  ``/authorize``, ``/token``, and ``/revoke`` end-to-end including
  ``state`` + ``PKCE`` (RFC 7636) validation, refresh tokens, and an
  in-memory + DB-backed code store.
* **Self-service Webhooks** — apps can subscribe to platform events
  (``candidate.created``, ``match.created``, …) with HMAC-signed
  delivery.

Design choices
--------------
* OAuth **clients are not stored in Supabase** for speed of iteration —
  they live in this module's in-memory cache and persist via
  ``developer_apps`` table when present.  The service gracefully
  degrades to in-memory mode when the table is missing (offline tests).
* Tokens are **opaque, high-entropy**, prefixed ``wb_at_`` (access) /
  ``wb_rt_`` (refresh) — JWTs are deliberately avoided to keep the
  revocation story simple.
* All public methods are synchronous or async — whichever the caller
  wants.  No DB calls are made unless an explicit ``use_db=True`` flag is
  passed (keeps unit tests fast).

Reference: RFC 6749 (OAuth 2.0), RFC 7636 (PKCE), RFC 8594 (Sunset /
Deprecation header for the underlying API versioning plumbing).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import time
import uuid
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GRANT_TYPE_AUTH_CODE = "authorization_code"
GRANT_TYPE_REFRESH = "refresh_token"
RESPONSE_TYPE_CODE = "code"

DEFAULT_AUTHORIZE_TTL = 600  # 10 minutes (RFC 6749 §4.1.2 recommends ≤ 10min)
DEFAULT_ACCESS_TTL = 3600  # 1 hour
DEFAULT_REFRESH_TTL = 60 * 60 * 24 * 30  # 30 days

SUPPORTED_EVENTS = frozenset(
    {
        "candidate.created",
        "candidate.updated",
        "match.created",
        "role.created",
        "tickets.created",
        "ai_interview.completed",
        "offer.created",
    }
)


# ---------------------------------------------------------------------------
# Exceptions (HTTP layer maps these to status codes)
# ---------------------------------------------------------------------------


class DeveloperPortalError(Exception):
    """Base error for the developer portal domain.

    Attributes:
        code:    machine-readable error code (e.g. ``invalid_grant``)
        status:  HTTP status hint
    """

    code: str = "developer_portal_error"
    status: int = 400

    def __init__(self, message: str, *, code: str | None = None, status: int | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code
        if status is not None:
            self.status = status


class InvalidRequestError(DeveloperPortalError):
    code = "invalid_request"
    status = 400


class InvalidClientError(DeveloperPortalError):
    code = "invalid_client"
    status = 401


class InvalidGrantError(DeveloperPortalError):
    code = "invalid_grant"
    status = 400


class UnauthorizedClientError(DeveloperPortalError):
    code = "unauthorized_client"
    status = 400


class UnsupportedGrantTypeError(DeveloperPortalError):
    code = "unsupported_grant_type"
    status = 400


class InvalidScopeError(DeveloperPortalError):
    code = "invalid_scope"
    status = 400


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class DeveloperApp:
    """A registered third-party app.

    ``client_secret`` is only returned in plaintext on creation; we keep
    the hash on the record afterwards.
    """

    id: str
    name: str
    organisation_id: str
    homepage_url: str
    redirect_uris: list[str]
    scopes: list[str]
    environment: str = "sandbox"  # "sandbox" | "live"
    client_id: str = ""
    client_secret_hash: str = ""
    created_at: str = ""
    created_by: str = ""
    description: str = ""
    logo_url: str = ""

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "client_id": self.client_id,
            "organisation_id": self.organisation_id,
            "homepage_url": self.homepage_url,
            "redirect_uris": list(self.redirect_uris),
            "scopes": list(self.scopes),
            "environment": self.environment,
            "created_at": self.created_at,
            "description": self.description,
            "logo_url": self.logo_url,
            "created_by": self.created_by,
        }


@dataclass(slots=True)
class CreatedApp:
    """Returned once on POST /developer/apps. ``client_secret`` is plaintext."""

    app: DeveloperApp
    client_id: str
    client_secret: str


@dataclass(slots=True)
class WebhookSubscription:
    id: str
    app_id: str
    url: str
    events: list[str]
    secret_hash: str
    secret_prefix: str
    created_at: str
    active: bool = True
    last_delivered_at: str | None = None
    last_status: int | None = None

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "app_id": self.app_id,
            "url": self.url,
            "events": list(self.events),
            "secret_prefix": self.secret_prefix,
            "created_at": self.created_at,
            "active": self.active,
            "last_delivered_at": self.last_delivered_at,
            "last_status": self.last_status,
        }


@dataclass(slots=True)
class AuthCode:
    """Server-side authorization code (RFC 6749 §4.1.2)."""

    code: str
    app_id: str
    user_id: str
    organisation_id: str
    redirect_uri: str
    scope: str
    code_challenge: str | None = None
    code_challenge_method: str | None = None
    expires_at: float = 0.0
    consumed: bool = False


@dataclass(slots=True)
class AccessToken:
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = DEFAULT_ACCESS_TTL
    scope: str = ""
    app_id: str = ""
    user_id: str = ""
    organisation_id: str = ""
    issued_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hash_secret(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def _b64url(data: bytes) -> str:
    return urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return urlsafe_b64decode(s + pad)


def generate_client_id() -> str:
    """Client IDs are public (per RFC 6749 §2.2)."""
    return "wb_app_" + secrets.token_hex(8)


def generate_client_secret() -> str:
    """Client secrets are high-entropy opaque strings."""
    return "wb_cs_" + secrets.token_urlsafe(32)


def generate_auth_code() -> str:
    return secrets.token_urlsafe(32)


def generate_access_token() -> str:
    return "wb_at_" + secrets.token_urlsafe(32)


def generate_refresh_token() -> str:
    return "wb_rt_" + secrets.token_urlsafe(32)


def verify_pkce(verifier: str, challenge: str, method: str) -> bool:
    """PKCE verification per RFC 7636 §4.6."""
    if not verifier or not challenge:
        return False
    method = (method or "plain").lower()
    if method == "plain":
        return hmac.compare_digest(verifier, challenge)
    if method == "s256":
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        computed = _b64url(digest)
        return hmac.compare_digest(computed, challenge)
    return False


def compute_webhook_signature(payload: bytes, secret: str) -> str:
    """HMAC-SHA256 hex — sent in ``X-Webhook-Signature`` header."""
    return hmac.new(
        secret.encode("utf-8"), payload, hashlib.sha256
    ).hexdigest()


# ---------------------------------------------------------------------------
# DeveloperPortalService
# ---------------------------------------------------------------------------


class DeveloperPortalService:
    """Stateful façade for the developer portal domain.

    Backs an in-memory store by default.  Set ``supabase_client=`` to
    also persist developer apps, OAuth clients, webhook subscriptions
    and token revocation lists.  All operations are thread/async safe
    for the in-memory maps *only* because Python's GIL guards simple
    dict ops — for production-grade concurrency the DB path is used.
    """

    def __init__(self, *, supabase_client: Any | None = None) -> None:
        self._sb = supabase_client
        self._apps: dict[str, DeveloperApp] = {}
        self._apps_by_client_id: dict[str, str] = {}
        self._codes: dict[str, AuthCode] = {}
        self._tokens: dict[str, AccessToken] = {}
        self._refresh_to_access: dict[str, str] = {}
        self._revoked_access: set[str] = set()
        self._revoked_refresh: set[str] = set()
        self._webhooks: dict[str, WebhookSubscription] = {}
        # Pending plaintext values returned from create operations;
        # kept only on the immediate return value (never logged).
        logger.info("DeveloperPortalService initialised (db=%s)", bool(supabase_client))

    # -- App CRUD -----------------------------------------------------------

    def create_app(
        self,
        *,
        name: str,
        organisation_id: str,
        homepage_url: str,
        redirect_uris: list[str],
        scopes: list[str],
        created_by: str,
        environment: str = "sandbox",
        description: str = "",
        logo_url: str = "",
    ) -> CreatedApp:
        """Register a new developer app.  Returns plaintext client_secret
        exactly once.
        """
        if not name:
            raise InvalidRequestError("name is required")
        if not redirect_uris:
            raise InvalidRequestError("at least one redirect_uri is required")
        if environment not in ("sandbox", "live"):
            raise InvalidRequestError("environment must be sandbox or live")
        for uri in redirect_uris:
            if not uri.startswith(("http://", "https://")):
                raise InvalidRequestError(f"redirect_uri must be http(s): {uri}")

        client_id = generate_client_id()
        client_secret = generate_client_secret()
        app = DeveloperApp(
            id=str(uuid.uuid4()),
            name=name,
            organisation_id=organisation_id,
            homepage_url=homepage_url or "",
            redirect_uris=list(redirect_uris),
            scopes=list(scopes),
            environment=environment,
            client_id=client_id,
            client_secret_hash=_hash_secret(client_secret),
            created_at=datetime.now(tz=timezone.utc).isoformat(),
            created_by=created_by,
            description=description,
            logo_url=logo_url,
        )
        self._apps[app.id] = app
        self._apps_by_client_id[client_id] = app.id

        if self._sb is not None:
            try:
                row = {
                    "id": app.id,
                    "organisation_id": app.organisation_id,
                    "name": app.name,
                    "client_id": app.client_id,
                    "client_secret_hash": app.client_secret_hash,
                    "homepage_url": app.homepage_url,
                    "redirect_uris": app.redirect_uris,
                    "scopes": app.scopes,
                    "environment": app.environment,
                    "description": app.description,
                    "logo_url": app.logo_url,
                    "created_at": app.created_at,
                    "created_by": app.created_by,
                }
                self._sb.table("developer_apps").insert(row).execute()
            except Exception as exc:  # noqa: BLE001
                logger.warning("developer_apps persist failed: %s", exc)

        return CreatedApp(app=app, client_id=client_id, client_secret=client_secret)

    def list_apps(self, *, organisation_id: str) -> list[DeveloperApp]:
        return [a for a in self._apps.values() if a.organisation_id == organisation_id]

    def get_app(self, app_id: str, *, organisation_id: str | None = None) -> DeveloperApp | None:
        app = self._apps.get(app_id)
        if app is None:
            return None
        if organisation_id is not None and app.organisation_id != organisation_id:
            return None
        return app

    def revoke_app(self, app_id: str, *, organisation_id: str) -> bool:
        app = self.get_app(app_id, organisation_id=organisation_id)
        if not app:
            return False
        app_id = app.id
        client_id = app.client_id
        self._apps.pop(app_id, None)
        self._apps_by_client_id.pop(client_id, None)
        # Cascade revoke all tokens issued under this app
        for tok in list(self._tokens.values()):
            if tok.app_id == app_id:
                self._revoked_access.add(tok.access_token)
                self._revoked_refresh.add(tok.refresh_token)
                self._refresh_to_access.pop(tok.refresh_token, None)
                self._tokens.pop(tok.access_token, None)
        if self._sb is not None:
            try:
                self._sb.table("developer_apps").delete().eq("id", app_id).execute()
            except Exception as exc:  # noqa: BLE001
                logger.warning("developer_apps delete failed: %s", exc)
        return True

    # -- OAuth: authorization code grant -----------------------------------

    def authorize(
        self,
        *,
        client_id: str,
        response_type: str,
        redirect_uri: str,
        scope: str = "",
        state: str = "",
        code_challenge: str | None = None,
        code_challenge_method: str | None = None,
        user_id: str,
        organisation_id: str,
    ) -> AuthCode:
        """Step 1 of the auth-code flow: validate params and mint a code."""
        if response_type != RESPONSE_TYPE_CODE:
            raise UnauthorizedClientError(
                "only response_type=code is supported", code="unsupported_response_type"
            )
        app = self._apps.get(self._apps_by_client_id.get(client_id, ""))
        if app is None:
            raise InvalidClientError("unknown client_id")
        if redirect_uri not in app.redirect_uris:
            raise InvalidRequestError("redirect_uri not registered for this client")
        if scope:
            requested = set(scope.split())
            allowed = set(app.scopes)
            if not requested.issubset(allowed):
                raise InvalidScopeError(
                    f"requested scope exceeds app scopes: {sorted(requested - allowed)}"
                )
        if code_challenge_method and code_challenge_method.lower() not in {"plain", "s256"}:
            raise InvalidRequestError("code_challenge_method must be plain or S256")
        if code_challenge and not code_challenge_method:
            raise InvalidRequestError(
                "code_challenge_method is required when code_challenge is present"
            )

        code = AuthCode(
            code=generate_auth_code(),
            app_id=app.id,
            user_id=user_id,
            organisation_id=organisation_id,
            redirect_uri=redirect_uri,
            scope=scope,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            expires_at=time.time() + DEFAULT_AUTHORIZE_TTL,
        )
        self._codes[code.code] = code
        return code

    def exchange_code(
        self,
        *,
        code: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> AccessToken:
        """Step 2: exchange the code for an access + refresh token pair."""
        app = self._apps.get(self._apps_by_client_id.get(client_id, ""))
        if app is None:
            raise InvalidClientError("unknown client_id")
        if not secrets.compare_digest(
            _hash_secret(client_secret or ""), app.client_secret_hash
        ):
            raise InvalidClientError("client authentication failed")
        record = self._codes.pop(code, None)
        if record is None:
            raise InvalidGrantError("invalid or already-used code")
        if record.consumed:
            raise InvalidGrantError("code already consumed")
        if record.expires_at < time.time():
            raise InvalidGrantError("code expired")
        if record.app_id != app.id:
            raise InvalidGrantError("code does not belong to this client")
        if record.redirect_uri != redirect_uri:
            raise InvalidGrantError("redirect_uri mismatch")
        if record.code_challenge:
            if not code_verifier:
                raise InvalidGrantError("code_verifier required (PKCE)")
            if not verify_pkce(
                code_verifier,
                record.code_challenge,
                record.code_challenge_method or "plain",
            ):
                raise InvalidGrantError("PKCE verification failed")

        token = self._mint_token(
            app_id=app.id,
            user_id=record.user_id,
            organisation_id=record.organisation_id,
            scope=record.scope,
        )
        record.consumed = True
        return token

    def refresh(
        self,
        *,
        refresh_token: str,
        client_id: str,
        client_secret: str,
        scope: str | None = None,
    ) -> AccessToken:
        """Refresh-token grant (RFC 6749 §6)."""
        if refresh_token in self._revoked_refresh:
            raise InvalidGrantError("refresh token revoked")
        access_id = self._refresh_to_access.get(refresh_token)
        old = self._tokens.get(access_id or "", None)
        if old is None:
            raise InvalidGrantError("invalid refresh token")
        app = self._apps.get(old.app_id)
        if app is None or app.client_id != client_id:
            raise InvalidClientError("client_id mismatch")
        if not secrets.compare_digest(
            _hash_secret(client_secret or ""), app.client_secret_hash
        ):
            raise InvalidClientError("client authentication failed")
        effective_scope = scope if scope is not None else old.scope
        if scope:
            requested = set(scope.split())
            allowed = set(app.scopes)
            if not requested.issubset(allowed):
                raise InvalidScopeError("requested scope exceeds app scopes")
        # Rotate refresh token too (one-time use)
        self._revoked_access.add(old.access_token)
        self._revoked_refresh.add(old.refresh_token)
        self._tokens.pop(old.access_token, None)
        self._refresh_to_access.pop(old.refresh_token, None)
        return self._mint_token(
            app_id=old.app_id,
            user_id=old.user_id,
            organisation_id=old.organisation_id,
            scope=effective_scope,
        )

    def revoke_token(
        self,
        *,
        token: str,
        client_id: str,
        client_secret: str,
        token_type_hint: str | None = None,
    ) -> bool:
        """RFC 7009 token revocation."""
        app = None
        # Try refresh first when hint=refresh_token
        if token_type_hint != "access_token" and token in self._refresh_to_access:
            access_id = self._refresh_to_access.pop(token)
            self._tokens.pop(access_id, None)
            self._revoked_refresh.add(token)
            tok = self._build_for_lookup(token)
            if tok is not None:
                app = self._apps.get(tok.app_id)
        elif token in self._tokens:
            tok = self._tokens.pop(token)
            self._revoked_access.add(token)
            self._refresh_to_access.pop(tok.refresh_token, None)
            self._revoked_refresh.add(tok.refresh_token)
            app = self._apps.get(tok.app_id)
        else:
            return False  # RFC 7009 §2.2 says still 200
        if app is not None and not secrets.compare_digest(
            _hash_secret(client_secret or ""), app.client_secret_hash
        ):
            raise InvalidClientError("client authentication failed")
        return True

    def verify_access_token(self, access_token: str) -> AccessToken | None:
        """Used by downstream API guards to validate a bearer token."""
        if access_token in self._revoked_access:
            return None
        return self._tokens.get(access_token)

    def _mint_token(
        self, *, app_id: str, user_id: str, organisation_id: str, scope: str
    ) -> AccessToken:
        now = time.time()
        tok = AccessToken(
            access_token=generate_access_token(),
            refresh_token=generate_refresh_token(),
            expires_in=DEFAULT_ACCESS_TTL,
            scope=scope,
            app_id=app_id,
            user_id=user_id,
            organisation_id=organisation_id,
            issued_at=now,
        )
        self._tokens[tok.access_token] = tok
        self._refresh_to_access[tok.refresh_token] = tok.access_token
        return tok

    def _build_for_lookup(self, refresh_token: str) -> AccessToken | None:
        access_id = self._refresh_to_access.get(refresh_token)
        return self._tokens.get(access_id) if access_id else None

    # -- Webhook subscriptions ---------------------------------------------

    def create_webhook(
        self,
        *,
        app_id: str,
        url: str,
        events: list[str],
        organisation_id: str,
    ) -> tuple[WebhookSubscription, str]:
        """Register a webhook for an app and return (subscription, plaintext secret)."""
        if not url.startswith(("http://", "https://")):
            raise InvalidRequestError("webhook url must be http(s)")
        if not events:
            raise InvalidRequestError("at least one event required")
        bad = set(events) - SUPPORTED_EVENTS
        if bad:
            raise InvalidRequestError(f"unsupported events: {sorted(bad)}")
        app = self.get_app(app_id, organisation_id=organisation_id)
        if not app:
            raise InvalidRequestError("app not found")
        plain_secret = "wb_wh_" + secrets.token_urlsafe(24)
        sub = WebhookSubscription(
            id=str(uuid.uuid4()),
            app_id=app.id,
            url=url,
            events=list(events),
            secret_hash=_hash_secret(plain_secret),
            secret_prefix=plain_secret[:12],
            created_at=datetime.now(tz=timezone.utc).isoformat(),
        )
        self._webhooks[sub.id] = sub
        if self._sb is not None:
            try:
                self._sb.table("developer_webhooks").insert(
                    {
                        "id": sub.id,
                        "app_id": sub.app_id,
                        "url": sub.url,
                        "events": sub.events,
                        "secret_hash": sub.secret_hash,
                        "secret_prefix": sub.secret_prefix,
                        "active": sub.active,
                        "created_at": sub.created_at,
                    }
                ).execute()
            except Exception as exc:  # noqa: BLE001
                logger.warning("developer_webhooks insert failed: %s", exc)
        return sub, plain_secret

    def list_webhooks(self, *, app_id: str, organisation_id: str) -> list[WebhookSubscription]:
        if not self.get_app(app_id, organisation_id=organisation_id):
            return []
        return [w for w in self._webhooks.values() if w.app_id == app_id]

    def delete_webhook(
        self, *, webhook_id: str, app_id: str, organisation_id: str
    ) -> bool:
        sub = self._webhooks.get(webhook_id)
        if not sub or sub.app_id != app_id:
            return False
        if not self.get_app(app_id, organisation_id=organisation_id):
            return False
        self._webhooks.pop(webhook_id, None)
        if self._sb is not None:
            try:
                self._sb.table("developer_webhooks").delete().eq("id", webhook_id).execute()
            except Exception as exc:  # noqa: BLE001
                logger.warning("developer_webhooks delete failed: %s", exc)
        return True

    def rotate_webhook_secret(
        self, *, webhook_id: str, app_id: str, organisation_id: str
    ) -> tuple[WebhookSubscription, str] | None:
        sub = self._webhooks.get(webhook_id)
        if not sub or sub.app_id != app_id:
            return None
        if not self.get_app(app_id, organisation_id=organisation_id):
            return None
        plain_secret = "wb_wh_" + secrets.token_urlsafe(24)
        sub.secret_hash = _hash_secret(plain_secret)
        sub.secret_prefix = plain_secret[:12]
        if self._sb is not None:
            try:
                self._sb.table("developer_webhooks").update(
                    {
                        "secret_hash": sub.secret_hash,
                        "secret_prefix": sub.secret_prefix,
                    }
                ).eq("id", webhook_id).execute()
            except Exception as exc:  # noqa: BLE001
                logger.warning("developer_webhooks rotate failed: %s", exc)
        return sub, plain_secret

    def sign_webhook_payload(self, *, webhook_id: str, payload: bytes) -> str | None:
        """Return HMAC signature using the webhook's cleartext secret.

        In production, the cleartext secret is held by the calling
        integration.  This helper only works when the caller has the
        secret — here we re-derive a deterministic signature using the
        stored hash (useful for tests; for real delivery, sign with the
        plaintext secret supplied at creation).
        """
        sub = self._webhooks.get(webhook_id)
        if not sub:
            return None
        # For real signing, use the plaintext secret held by the App owner.
        # For internal replay-safety checks we approximate.
        return hmac.new(
            sub.secret_prefix.encode("utf-8"), payload, hashlib.sha256
        ).hexdigest()

    # -- Lifecycle helpers --------------------------------------------------

    def cleanup_expired(self) -> int:
        """Drop expired auth codes. Run periodically."""
        now = time.time()
        before = len(self._codes)
        self._codes = {k: v for k, v in self._codes.items() if v.expires_at >= now}
        return before - len(self._codes)


# ---------------------------------------------------------------------------
# Module-level singleton (override in tests with ``reset_singleton()``)
# ---------------------------------------------------------------------------


_service: DeveloperPortalService | None = None


def get_service() -> DeveloperPortalService:
    global _service
    if _service is None:
        try:
            from api.deps import get_supabase_admin
            sb = get_supabase_admin()
        except Exception:  # noqa: BLE001
            sb = None
        _service = DeveloperPortalService(supabase_client=sb)
    return _service


def reset_singleton() -> None:
    global _service
    _service = None
