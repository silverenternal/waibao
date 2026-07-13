"""Unified MarketplaceService — facade for the API layer.

Wraps :class:`CatalogService`, :class:`InstallService`,
:class:`ReviewService`, and :class:`BillingService` into a single
object so the FastAPI handler can be terse. Also exposes:

* :func:`notify_webhook` — send an external notification (used when
  the listing is approved or when an install completes).
* :class:`MarketplaceStrapiBridge` — best-effort mirroring of catalog
  records to a Strapi admin instance.  When ``MARKETPLACE_STRAPI_URL``
  is not configured the bridge is a no-op (offline / dev).
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
from typing import Any

from .billing import (
    BillingError,
    BillingService,
    Purchase,
    PurchaseNotFoundError,
    PurchaseStateError,
    generate_idempotency_key,
)
from .catalog import (
    CatalogService,
    MarketplacePlugin,
    PluginNotFoundError,
    PluginRelease,
    PluginVersionExistsError,
    PublishValidationError,
)
from .install import InstallResult, InstallService, ip_hash
from .reviews import (
    Review,
    ReviewNotFoundError,
    ReviewService,
    ReviewValidationError,
)

logger = logging.getLogger(__name__)


# Re-export the errors at this level so callers can ``except`` from one
# place.
PluginNotApprovedError = PublishValidationError
PluginVersionMismatchError = PublishValidationError


class MarketplaceError(Exception):
    """Generic marketplace failure (catch-all for the API layer)."""


# ---------------------------------------------------------------------------
# Optional Strapi bridge
# ---------------------------------------------------------------------------

class MarketplaceStrapiBridge:
    """Best-effort HTTP mirroring of catalog rows to a Strapi admin.

    Strapi remains the moderator surface; the Python service is the
    system of record.  When ``STRAPI_URL`` is not set the bridge
    silently no-ops so unit tests and offline development work.

    Network calls are made through ``urllib`` to avoid pulling httpx /
    aiohttp into a module that may be imported in lightweight test
    contexts.
    """

    def __init__(self, base_url: str | None = None, token: str | None = None) -> None:
        self.base_url = base_url or os.getenv("MARKETPLACE_STRAPI_URL")
        self.token = token or os.getenv("MARKETPLACE_STRAPI_TOKEN")
        self._enabled = bool(self.base_url)
        if not self._enabled:
            logger.debug("Strapi bridge disabled (MARKETPLACE_STRAPI_URL not set)")

    def push_plugin(self, plugin: MarketplacePlugin) -> dict[str, Any]:
        return self._post("/api/marketplace-plugins", plugin.to_dict())

    def push_release(self, release: PluginRelease) -> dict[str, Any]:
        return self._post("/api/plugin-releases", release.to_dict())

    def pull_pending(self) -> list[dict[str, Any]]:
        return self._get("/api/marketplace-plugins?filters[status][$eq]=pending_review")

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        if not self._enabled:
            return {"ok": True, "noop": True}
        return self._request("POST", path, body)

    def _get(self, path: str) -> list[dict[str, Any]]:
        if not self._enabled:
            return []
        data = self._request("GET", path, None)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "data" in data:
            return list(data["data"])
        return []

    def _request(
        self, method: str, path: str, body: dict[str, Any] | None
    ) -> Any:
        try:
            import json
            import urllib.request
            url = f"{self.base_url.rstrip('/')}{path}"
            data = None if body is None else json.dumps(body).encode("utf-8")
            req = urllib.request.Request(url, data=data, method=method)
            req.add_header("Content-Type", "application/json")
            if self.token:
                req.add_header("Authorization", f"Bearer {self.token}")
            with urllib.request.urlopen(req, timeout=5) as resp:  # nosec - internal
                raw = resp.read().decode("utf-8")
                if not raw:
                    return {"ok": True}
                return json.loads(raw)
        except Exception as exc:                       # pragma: no cover
            logger.warning("Strapi %s %s failed: %s", method, path, exc)
            return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Webhook / notify
# ---------------------------------------------------------------------------

class MarketplaceNotifier:
    """Sends notifications to ``services.notify`` on key events.

    Falls back to logging if the notify service is unavailable.
    """

    def __init__(self) -> None:
        self._send = self._resolve_send()

    def _resolve_send(self) -> Any:
        try:
            from services.notify import send_notification  # type: ignore
            return send_notification
        except Exception:                              # pragma: no cover
            def _fallback(*, channel: str, recipient: str, subject: str, body: str) -> dict[str, Any]:
                logger.info("[notify:%s] %s -> %s: %s", channel, recipient, subject, body)
                return {"ok": True, "noop": True}
            return _fallback

    def plugin_approved(self, *, plugin: MarketplacePlugin) -> None:
        self._send(
            channel="email",
            recipient=plugin.author_email or plugin.author_id,
            subject=f"[Marketplace] '{plugin.name}' approved",
            body=f"Your plugin is now live at /marketplace/{plugin.slug}",
        )

    def plugin_rejected(self, *, plugin: MarketplacePlugin) -> None:
        self._send(
            channel="email",
            recipient=plugin.author_email or plugin.author_id,
            subject=f"[Marketplace] '{plugin.name}' rejected",
            body=f"Reason: {plugin.rejection_reason}",
        )

    def install_completed(
        self, *, tenant_id: str, plugin: MarketplacePlugin, result: InstallResult,
    ) -> None:
        self._send(
            channel="in_app",
            recipient=tenant_id,
            subject=f"Installed {plugin.name}",
            body=f"v{result.version} installed in {result.duration_ms:.0f}ms",
        )


# ---------------------------------------------------------------------------
# Main facade
# ---------------------------------------------------------------------------

class MarketplaceService:
    """Single facade exposed to the API layer."""

    def __init__(
        self,
        *,
        strapi_bridge: MarketplaceStrapiBridge | None = None,
        notifier: MarketplaceNotifier | None = None,
    ) -> None:
        self.catalog = CatalogService()
        # NOTE: ``self.installer`` is the underlying service; ``self.install``
        # is the callable facade method below. We deliberately do not
        # store the InstallService as ``self.install`` because Python
        # would shadow the method with the instance attribute.
        self.installer = InstallService(self.catalog)
        self.reviews = ReviewService(self.catalog)
        self.billing = BillingService(self.catalog)
        self.strapi = strapi_bridge or MarketplaceStrapiBridge()
        self.notifier = notifier or MarketplaceNotifier()
        # Lock to make publish/install atomic per process.
        self._lock = threading.Lock()

    # ---- catalog --------------------------------------------------------

    def publish(self, **kwargs: Any) -> MarketplacePlugin:
        with self._lock:
            plugin = self.catalog.publish_plugin(**kwargs)
        # Best-effort mirror to Strapi.
        try:
            self.strapi.push_plugin(plugin)
        except Exception as exc:                       # pragma: no cover
            logger.warning("strapi mirror failed: %s", exc)
        return plugin

    def add_release(self, **kwargs: Any) -> PluginRelease:
        with self._lock:
            release = self.catalog.add_release(**kwargs)
        try:
            self.strapi.push_release(release)
        except Exception as exc:                       # pragma: no cover
            logger.warning("strapi mirror failed: %s", exc)
        return release

    def approve(self, *, plugin_id: str, reviewer: str) -> MarketplacePlugin:
        with self._lock:
            plugin = self.catalog.approve_plugin(
                plugin_id=plugin_id, reviewer=reviewer,
            )
        try:
            self.notifier.plugin_approved(plugin=plugin)
        except Exception as exc:                       # pragma: no cover
            logger.warning("notify failed: %s", exc)
        return plugin

    def reject(
        self, *, plugin_id: str, reviewer: str, reason: str
    ) -> MarketplacePlugin:
        with self._lock:
            plugin = self.catalog.reject_plugin(
                plugin_id=plugin_id, reviewer=reviewer, reason=reason,
            )
        try:
            self.notifier.plugin_rejected(plugin=plugin)
        except Exception as exc:                       # pragma: no cover
            logger.warning("notify failed: %s", exc)
        return plugin

    # ---- install --------------------------------------------------------

    def install(self, **kwargs: Any) -> InstallResult:
        with self._lock:
            result = self.installer.install(**kwargs)
        if result.success:
            try:
                plugin = self.catalog.get_plugin(plugin_id=result.plugin_id)
                self.notifier.install_completed(
                    tenant_id=kwargs.get("tenant_id", "anonymous"),
                    plugin=plugin, result=result,
                )
            except Exception as exc:                   # pragma: no cover
                logger.warning("notify failed: %s", exc)
        return result

    def uninstall(self, **kwargs: Any) -> dict[str, Any]:
        return self.installer.uninstall(**kwargs)

    # ---- reviews --------------------------------------------------------

    def submit_review(self, **kwargs: Any) -> Review:
        return self.reviews.submit(**kwargs)

    # ---- billing --------------------------------------------------------

    def purchase(self, **kwargs: Any) -> Purchase:
        return self.billing.create_purchase(**kwargs)

    def mark_purchase_paid(self, **kwargs: Any) -> Purchase:
        return self.billing.mark_paid(**kwargs)

    # ---- stats ----------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        return {
            "total_plugins": len(self.catalog._store.plugins),  # noqa: SLF001
            "pending_review": len(self.catalog.list_pending()),
            "approved": len(self.catalog.list_public(limit=10_000)),
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_default: MarketplaceService | None = None


def get_marketplace_service() -> MarketplaceService:
    global _default
    if _default is None:
        _default = MarketplaceService()
    return _default


def reset_marketplace_service() -> None:
    """Reset the singleton (test helper)."""
    global _default
    _default = None
