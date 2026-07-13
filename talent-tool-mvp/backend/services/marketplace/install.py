"""Marketplace install — delegate to v6.0 Plugin SDK (T2104).

The marketplace is the *public catalog*; the v6.0 Plugin SDK is the
*runtime*. When a tenant clicks "install" on a marketplace listing we
translate the catalog record into a ``plugin.yaml`` and hand it off to
``services.plugins.sdk.runner`` (or to the legacy ``PluginManager``
fallback if the SDK is unavailable).

This module also keeps a per-tenant install log so we can drive
recommendations, billing, and audit from one place.
"""
from __future__ import annotations

import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from .catalog import (
    CatalogService,
    PluginNotFoundError,
    PublishValidationError,
    sha256_hex,
)
# NOTE: do not import from .service here — that would create a circular
# import. We re-define ``PluginNotApprovedError`` and
# ``PluginVersionMismatchError`` locally; both are aliases of
# :class:`PublishValidationError` (so callers can ``except`` either).
PluginNotApprovedError = PublishValidationError
PluginVersionMismatchError = PublishValidationError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class InstallResult:
    success: bool
    plugin_id: str
    release_id: str | None
    version: str | None
    install_id: str
    duration_ms: float
    detail: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "plugin_id": self.plugin_id,
            "release_id": self.release_id,
            "version": self.version,
            "install_id": self.install_id,
            "duration_ms": self.duration_ms,
            "detail": self.detail,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Optional Plugin SDK import — best-effort
# ---------------------------------------------------------------------------

def _load_plugin_runner() -> Any | None:
    """Best-effort import of the v6.0 Plugin SDK runner.

    We avoid hard-coupling this module to the plugin SDK so that the
    marketplace can be unit-tested in isolation.
    """
    try:
        # The actual v6.0 SDK lives at backend/services/plugins/sdk/runner.py
        from services.plugins.sdk import runner as _runner  # type: ignore
        return _runner
    except Exception as exc:           # pragma: no cover
        logger.debug("plugin SDK runner not available: %s", exc)
        return None


def _load_plugin_manager() -> Any | None:
    try:
        from services.plugins import manager as _mgr   # type: ignore
        return _mgr
    except Exception as exc:           # pragma: no cover
        logger.debug("plugin manager not available: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Tenant install registry — kept here (not in catalog) because it's the
# per-tenant install state, which the SDK already persists elsewhere.
# ---------------------------------------------------------------------------

class _TenantInstalls:
    def __init__(self) -> None:
        # tenant_id -> { plugin_slug -> {release_id, version, installed_at, install_id} }
        self._map: dict[str, dict[str, dict[str, Any]]] = {}

    def record(
        self,
        tenant_id: str,
        slug: str,
        *,
        plugin_id: str,
        release_id: str,
        version: str,
    ) -> str:
        install_id = str(uuid.uuid4())
        self._map.setdefault(tenant_id, {})[slug] = {
            "install_id": install_id,
            "plugin_id": plugin_id,
            "release_id": release_id,
            "version": version,
            "installed_at": time.time(),
        }
        return install_id

    def remove(self, tenant_id: str, slug: str) -> dict[str, Any] | None:
        slot = self._map.get(tenant_id, {})
        info = slot.pop(slug, None)
        if not slot:
            self._map.pop(tenant_id, None)
        return info

    def get(self, tenant_id: str, slug: str) -> dict[str, Any] | None:
        return self._map.get(tenant_id, {}).get(slug)

    def list_for_tenant(self, tenant_id: str) -> dict[str, dict[str, Any]]:
        return dict(self._map.get(tenant_id, {}))


# ---------------------------------------------------------------------------
# Install service
# ---------------------------------------------------------------------------

class InstallService:
    """1-click install / uninstall, glued to the v6.0 Plugin SDK."""

    def __init__(
        self,
        catalog: CatalogService,
        *,
        sdk_runner: Any | None = None,
        plugin_manager: Any | None = None,
    ) -> None:
        self.catalog = catalog
        self._runner = sdk_runner or _load_plugin_runner()
        self._manager = plugin_manager or _load_plugin_manager()
        self._tenant_installs = _TenantInstalls()
        # Record of every install attempt (for audit / tests).
        self.audit: list[dict[str, Any]] = []

    # ---- public API -----------------------------------------------------

    def install(
        self,
        *,
        tenant_id: str,
        slug: str,
        version: str | None = None,
        actor: str = "user",
        waibao_version: str = "6.0.0",
        accept_terms: bool = False,
    ) -> InstallResult:
        start = time.time()
        install_id = str(uuid.uuid4())
        try:
            plugin = self.catalog.get_plugin(slug=slug)
        except PluginNotFoundError as exc:
            self._audit(tenant_id, slug, "install", actor, "not_found", str(exc))
            return InstallResult(
                success=False, plugin_id="", release_id=None, version=None,
                install_id=install_id, duration_ms=0.0, error=str(exc),
            )

        if plugin.status != "approved":
            self._audit(tenant_id, slug, "install", actor, "not_approved",
                        f"status={plugin.status}")
            raise PluginNotApprovedError(
                f"plugin {slug!r} is {plugin.status!r}; not installable"
            )

        release = self._resolve_release(plugin, version, waibao_version)
        if release is None:
            if version is not None:
                self._audit(tenant_id, slug, "install", actor, "version_mismatch",
                            f"requested {version}, current waibao {waibao_version}")
                raise PluginVersionMismatchError(
                    f"no compatible release for version={version!r} "
                    f"on waibao {waibao_version}"
                )
            raise PluginVersionMismatchError(
                f"plugin {slug!r} has no approved releases"
            )

        if not accept_terms and plugin.pricing_model != "free":
            self._audit(tenant_id, slug, "install", actor, "terms_not_accepted",
                        f"pricing_model={plugin.pricing_model}")
            raise PublishValidationError(
                f"plugin {slug!r} requires explicit accept_terms=true "
                f"(pricing_model={plugin.pricing_model})"
            )

        manifest = self._build_manifest(plugin, release)
        sdk_result = self._invoke_sdk(plugin, release, manifest)
        if not sdk_result.get("ok"):
            self._audit(tenant_id, slug, "install", actor, "sdk_failed",
                        sdk_result.get("error", "unknown"))
            return InstallResult(
                success=False, plugin_id=plugin.id, release_id=release.id,
                version=release.version, install_id=install_id,
                duration_ms=(time.time() - start) * 1000,
                detail=sdk_result, error=sdk_result.get("error", "sdk_failed"),
            )

        # Persist tenant-level install record.
        self._tenant_installs.record(
            tenant_id, slug, plugin_id=plugin.id,
            release_id=release.id, version=release.version,
        )
        # Update aggregate counters.
        plugin.total_installs += 1
        release.downloads += 1
        self._audit(tenant_id, slug, "install", actor, "ok", None,
                    extra={"release_id": release.id, "version": release.version})
        return InstallResult(
            success=True, plugin_id=plugin.id, release_id=release.id,
            version=release.version, install_id=install_id,
            duration_ms=(time.time() - start) * 1000, detail=sdk_result,
        )

    def uninstall(
        self,
        *,
        tenant_id: str,
        slug: str,
        actor: str = "user",
    ) -> dict[str, Any]:
        info = self._tenant_installs.get(tenant_id, slug)
        if info is None:
            return {"success": False, "error": "not_installed",
                    "tenant_id": tenant_id, "slug": slug}
        # Ask the SDK to unload. The runner is best-effort: if the
        # plugin is not actually loaded the call is a no-op.
        sdk_result: dict[str, Any]
        if self._runner is not None and hasattr(self._runner, "uninstall"):
            try:
                sdk_result = self._runner.uninstall(slug)  # type: ignore[attr-defined]
                if not isinstance(sdk_result, dict):
                    sdk_result = {"ok": True, "raw": sdk_result}
            except Exception as exc:                           # pragma: no cover
                sdk_result = {"ok": False, "error": str(exc)}
        else:
            sdk_result = {"ok": True, "noop": True}

        self._tenant_installs.remove(tenant_id, slug)
        self._audit(tenant_id, slug, "uninstall", actor, "ok", None,
                    extra={"release_id": info.get("release_id")})
        return {
            "success": True,
            "tenant_id": tenant_id,
            "slug": slug,
            "previous_release_id": info.get("release_id"),
            "sdk": sdk_result,
        }

    def list_installed(self, tenant_id: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for slug, info in self._tenant_installs.list_for_tenant(tenant_id).items():
            try:
                plugin = self.catalog.get_plugin(slug=slug)
            except PluginNotFoundError:
                continue
            out.append({
                "install_id": info["install_id"],
                "slug": slug,
                "plugin_id": plugin.id,
                "name": plugin.name,
                "version": info["version"],
                "release_id": info["release_id"],
                "installed_at": info["installed_at"],
            })
        return out

    def is_installed(self, tenant_id: str, slug: str) -> bool:
        return self._tenant_installs.get(tenant_id, slug) is not None

    # ---- helpers --------------------------------------------------------

    def _resolve_release(
        self,
        plugin: Any,
        version: str | None,
        waibao_version: str,
    ) -> Any | None:
        approved = [r for r in plugin.releases if r.status == "approved"]
        if not approved:
            return None
        if version is not None:
            for r in approved:
                if r.version == version:
                    return r
            return None
        # Pick latest approved by semver
        def key(r: Any) -> tuple[int, int, int, str]:
            try:
                nums = tuple(int(x) for x in r.version.split(".")[:3])
                return (nums[0], nums[1], nums[2], r.version)
            except Exception:
                return (0, 0, 0, r.version)
        return sorted(approved, key=key, reverse=True)[0]

    def _build_manifest(self, plugin: Any, release: Any) -> dict[str, Any]:
        """Compose a plugin.yaml-style manifest for the SDK runner."""
        manifest = dict(plugin.manifest or {})
        manifest.setdefault("name", plugin.slug)
        manifest.setdefault("version", release.version)
        manifest.setdefault("description", plugin.tagline or plugin.description[:200])
        manifest["__marketplace"] = {
            "plugin_id": plugin.id,
            "release_id": release.id,
            "slug": plugin.slug,
            "category": plugin.category,
            "author_id": plugin.author_id,
            "sha256": release.artifact_sha256,
            "artifact_url": release.artifact_url,
        }
        return manifest

    def _invoke_sdk(
        self,
        plugin: Any,
        release: Any,
        manifest: dict[str, Any],
    ) -> dict[str, Any]:
        # 1) Try the v6.0 SDK runner first.
        if self._runner is not None and hasattr(self._runner, "install"):
            try:
                result = self._runner.install(manifest)  # type: ignore[attr-defined]
                if isinstance(result, dict):
                    return {"ok": True, "via": "sdk", **result}
                return {"ok": True, "via": "sdk", "raw": result}
            except Exception as exc:                       # pragma: no cover
                logger.warning("plugin SDK install failed: %s", exc)
                return {"ok": False, "via": "sdk", "error": str(exc)}
        # 2) Fall back to the legacy PluginManager (T2104 base).
        if self._manager is not None and hasattr(self._manager, "install"):
            try:
                result = self._manager.install(manifest)  # type: ignore[attr-defined]
                if isinstance(result, dict):
                    return {"ok": True, "via": "manager", **result}
                return {"ok": True, "via": "manager", "raw": result}
            except Exception as exc:                       # pragma: no cover
                logger.warning("plugin manager install failed: %s", exc)
                return {"ok": False, "via": "manager", "error": str(exc)}
        # 3) Offline / no SDK — synthesize success.
        return {
            "ok": True,
            "via": "noop",
            "manifest_sha256": sha256_hex(str(manifest)),
        }

    def _audit(
        self,
        tenant_id: str,
        slug: str,
        action: str,
        actor: str,
        status: str,
        error: str | None,
        *,
        extra: dict[str, Any] | None = None,
    ) -> None:
        entry = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "slug": slug,
            "action": action,
            "actor": actor,
            "status": status,
            "error": error,
            "created_at": time.time(),
        }
        if extra:
            entry.update(extra)
        self.audit.append(entry)
        # Mirror to the catalog's audit log so the admin UI can see it.
        try:
            plugin = self.catalog.get_plugin(slug=slug)
            self.catalog._store.append_audit({   # noqa: SLF001
                "plugin_id": plugin.id,
                "action": action,
                "actor": actor,
                "detail": {"tenant_id": tenant_id, "status": status,
                           "error": error, **(extra or {})},
                "created_at": time.time(),
            })
        except PluginNotFoundError:
            pass


def ip_hash(ip: str, salt: str = "waibao-mkt") -> str:
    """One-way salted hash for GDPR-friendly IP storage."""
    return hashlib.sha256(f"{salt}:{ip}".encode("utf-8")).hexdigest()
