"""Marketplace catalog — publish, approve, search.

* ``publish_plugin``    — author submits a new listing (status=pending_review)
* ``add_release``       — author uploads a new semver version
* ``approve_plugin``    — moderator approves (status=approved)
* ``reject_plugin``     — moderator rejects (status=rejected)
* ``list_public``       — read public catalog with filters
* ``get_plugin``        — single listing detail (with releases & reviews)
* ``search``            — substring/tag/category search

Designed to work fully offline (in-memory) and against Supabase when
the table is present, mirroring the pattern used by
:mod:`services.platform.developer_portal`.
"""
from __future__ import annotations

import hashlib
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class CatalogError(Exception):
    """Base class for catalog problems."""


class PluginNotFoundError(CatalogError):
    pass


class PluginVersionExistsError(CatalogError):
    pass


class PublishValidationError(CatalogError):
    pass


class PermissionDeniedError(CatalogError):
    pass


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$")
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-]+)?$")
VALID_CATEGORIES = {
    "integration", "analytics", "automation", "sourcing",
    "assessment", "video", "utility", "other",
}
VALID_PRICING = {"free", "one_time", "subscription", "usage"}


def validate_slug(slug: str) -> str:
    s = (slug or "").strip().lower()
    if not _SLUG_RE.match(s):
        raise PublishValidationError(
            f"invalid slug {slug!r}: must be 3-64 chars, lowercase a-z0-9-, "
            "must start/end with alphanumeric"
        )
    return s


def validate_semver(version: str) -> str:
    v = (version or "").strip()
    if not _SEMVER_RE.match(v):
        raise PublishValidationError(f"invalid semver {version!r}")
    return v


def validate_category(cat: str) -> str:
    if cat not in VALID_CATEGORIES:
        raise PublishValidationError(
            f"invalid category {cat!r}; must be one of {sorted(VALID_CATEGORIES)}"
        )
    return cat


def validate_pricing(p: str) -> str:
    if p not in VALID_PRICING:
        raise PublishValidationError(
            f"invalid pricing_model {p!r}; must be one of {sorted(VALID_PRICING)}"
        )
    return p


def validate_price_cents(amount: int, pricing_model: str) -> int:
    if amount < 0 or amount > 1_000_000_00:  # $1M cap
        raise PublishValidationError(f"price_cents out of range: {amount}")
    if pricing_model == "free" and amount != 0:
        raise PublishValidationError("free plugins must have price_cents=0")
    if pricing_model != "free" and amount == 0:
        raise PublishValidationError(
            f"pricing_model={pricing_model!r} requires price_cents>0"
        )
    return amount


# ---------------------------------------------------------------------------
# Datatypes
# ---------------------------------------------------------------------------

@dataclass
class PluginRelease:
    id: str
    plugin_id: str
    version: str
    changelog: str
    artifact_url: str
    artifact_sha256: str
    min_waibao_ver: str = "6.0.0"
    max_waibao_ver: str | None = None
    manifest: dict[str, Any] = field(default_factory=dict)
    status: str = "pending_review"
    size_bytes: int = 0
    downloads: int = 0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "plugin_id": self.plugin_id,
            "version": self.version,
            "changelog": self.changelog,
            "artifact_url": self.artifact_url,
            "artifact_sha256": self.artifact_sha256,
            "min_waibao_ver": self.min_waibao_ver,
            "max_waibao_ver": self.max_waibao_ver,
            "manifest": self.manifest,
            "status": self.status,
            "size_bytes": self.size_bytes,
            "downloads": self.downloads,
            "created_at": self.created_at,
        }


@dataclass
class MarketplacePlugin:
    id: str
    slug: str
    name: str
    tagline: str = ""
    description: str = ""
    category: str = "integration"
    tags: list[str] = field(default_factory=list)
    author_id: str = ""
    author_name: str = ""
    author_email: str | None = None
    homepage_url: str | None = None
    repo_url: str | None = None
    icon_url: str | None = None
    screenshots: list[str] = field(default_factory=list)
    pricing_model: str = "free"
    price_cents: int = 0
    revenue_share: float = 0.70
    status: str = "pending_review"
    rejection_reason: str | None = None
    reviewed_by: str | None = None
    reviewed_at: float | None = None
    total_installs: int = 0
    avg_rating: float = 0.0
    rating_count: int = 0
    manifest: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    releases: list[PluginRelease] = field(default_factory=list)

    # --- serialization -------------------------------------------------
    def to_dict(self, *, with_releases: bool = False) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "slug": self.slug,
            "name": self.name,
            "tagline": self.tagline,
            "description": self.description,
            "category": self.category,
            "tags": list(self.tags),
            "author_id": self.author_id,
            "author_name": self.author_name,
            "author_email": self.author_email,
            "homepage_url": self.homepage_url,
            "repo_url": self.repo_url,
            "icon_url": self.icon_url,
            "screenshots": list(self.screenshots),
            "pricing_model": self.pricing_model,
            "price_cents": self.price_cents,
            "revenue_share": self.revenue_share,
            "status": self.status,
            "rejection_reason": self.rejection_reason,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at,
            "total_installs": self.total_installs,
            "avg_rating": self.avg_rating,
            "rating_count": self.rating_count,
            "manifest": self.manifest,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if with_releases:
            out["releases"] = [r.to_dict() for r in self.releases]
        return out


# ---------------------------------------------------------------------------
# In-memory catalog (default fallback; Supabase overlay if available)
# ---------------------------------------------------------------------------

class _CatalogStore:
    """In-memory catalog used when Supabase is unreachable / tests."""

    def __init__(self) -> None:
        self.plugins: dict[str, MarketplacePlugin] = {}    # by id
        self.slug_index: dict[str, str] = {}              # slug -> id
        self.audit: list[dict[str, Any]] = []

    def add(self, plugin: MarketplacePlugin) -> None:
        if plugin.slug in self.slug_index:
            raise PublishValidationError(
                f"slug {plugin.slug!r} already exists"
            )
        self.plugins[plugin.id] = plugin
        self.slug_index[plugin.slug] = plugin.id

    def append_audit(self, entry: dict[str, Any]) -> None:
        self.audit.append(entry)


# ---------------------------------------------------------------------------
# Catalog service
# ---------------------------------------------------------------------------

class CatalogService:
    """Publish / approve / search the public marketplace.

    All public methods are synchronous and side-effect free apart from
    the in-memory store. The ``supabase`` parameter is accepted for
    future overlay use but is not required.
    """

    def __init__(self, *, supabase: Any | None = None) -> None:
        self._supabase = supabase
        self._store = _CatalogStore()

    # ---- publish / releases --------------------------------------------

    def publish_plugin(
        self,
        *,
        slug: str,
        name: str,
        tagline: str = "",
        description: str = "",
        category: str = "integration",
        tags: Iterable[str] = (),
        author_id: str,
        author_name: str,
        author_email: str | None = None,
        homepage_url: str | None = None,
        repo_url: str | None = None,
        icon_url: str | None = None,
        screenshots: Iterable[str] = (),
        pricing_model: str = "free",
        price_cents: int = 0,
        revenue_share: float = 0.70,
        manifest: dict[str, Any] | None = None,
    ) -> MarketplacePlugin:
        slug = validate_slug(slug)
        validate_category(category)
        validate_pricing(pricing_model)
        validate_price_cents(price_cents, pricing_model)
        if not (0.0 <= revenue_share <= 1.0):
            raise PublishValidationError(
                f"revenue_share out of range: {revenue_share}"
            )
        if not author_id or not author_name:
            raise PublishValidationError(
                "author_id and author_name are required"
            )
        if not name or len(name) > 100:
            raise PublishValidationError("name must be 1..100 chars")
        plugin = MarketplacePlugin(
            id=str(uuid.uuid4()),
            slug=slug,
            name=name.strip(),
            tagline=(tagline or "")[:200],
            description=(description or "")[:10000],
            category=category,
            tags=[t.strip() for t in tags if t and t.strip()][:20],
            author_id=author_id,
            author_name=author_name,
            author_email=author_email,
            homepage_url=homepage_url,
            repo_url=repo_url,
            icon_url=icon_url,
            screenshots=list(screenshots)[:10],
            pricing_model=pricing_model,
            price_cents=price_cents,
            revenue_share=revenue_share,
            manifest=manifest or {},
        )
        self._store.add(plugin)
        self._store.append_audit({
            "plugin_id": plugin.id,
            "action": "publish",
            "actor": author_id,
            "detail": {"slug": slug, "name": name},
            "created_at": time.time(),
        })
        return plugin

    def add_release(
        self,
        *,
        plugin_id: str,
        version: str,
        artifact_url: str,
        artifact_sha256: str,
        changelog: str = "",
        min_waibao_ver: str = "6.0.0",
        max_waibao_ver: str | None = None,
        size_bytes: int = 0,
        manifest: dict[str, Any] | None = None,
    ) -> PluginRelease:
        plugin = self._store.plugins.get(plugin_id)
        if plugin is None:
            raise PluginNotFoundError(f"plugin {plugin_id!r} not found")
        version = validate_semver(version)
        if not artifact_url:
            raise PublishValidationError("artifact_url is required")
        if not artifact_sha256 or len(artifact_sha256) != 64:
            raise PublishValidationError(
                "artifact_sha256 must be 64 hex chars (sha256 digest)"
            )
        for r in plugin.releases:
            if r.version == version:
                raise PluginVersionExistsError(
                    f"version {version!r} already exists for {plugin.slug}"
                )
        release = PluginRelease(
            id=str(uuid.uuid4()),
            plugin_id=plugin_id,
            version=version,
            changelog=changelog or "",
            artifact_url=artifact_url,
            artifact_sha256=artifact_sha256,
            min_waibao_ver=min_waibao_ver,
            max_waibao_ver=max_waibao_ver,
            manifest=manifest or {},
            size_bytes=size_bytes,
        )
        plugin.releases.append(release)
        plugin.updated_at = time.time()
        self._store.append_audit({
            "plugin_id": plugin_id,
            "release_id": release.id,
            "action": "update",
            "actor": plugin.author_id,
            "detail": {"version": version},
            "created_at": time.time(),
        })
        return release

    # ---- moderation ----------------------------------------------------

    def approve_plugin(self, *, plugin_id: str, reviewer: str) -> MarketplacePlugin:
        plugin = self._store.plugins.get(plugin_id)
        if plugin is None:
            raise PluginNotFoundError(f"plugin {plugin_id!r} not found")
        plugin.status = "approved"
        plugin.rejection_reason = None
        plugin.reviewed_by = reviewer
        plugin.reviewed_at = time.time()
        plugin.updated_at = time.time()
        # Approving cascades to pending releases
        for r in plugin.releases:
            if r.status == "pending_review":
                r.status = "approved"
        self._store.append_audit({
            "plugin_id": plugin_id,
            "action": "approve",
            "actor": reviewer,
            "created_at": time.time(),
        })
        return plugin

    def reject_plugin(
        self,
        *,
        plugin_id: str,
        reviewer: str,
        reason: str,
    ) -> MarketplacePlugin:
        plugin = self._store.plugins.get(plugin_id)
        if plugin is None:
            raise PluginNotFoundError(f"plugin {plugin_id!r} not found")
        if not reason:
            raise PublishValidationError("rejection reason is required")
        plugin.status = "rejected"
        plugin.rejection_reason = reason
        plugin.reviewed_by = reviewer
        plugin.reviewed_at = time.time()
        plugin.updated_at = time.time()
        self._store.append_audit({
            "plugin_id": plugin_id,
            "action": "reject",
            "actor": reviewer,
            "detail": {"reason": reason},
            "created_at": time.time(),
        })
        return plugin

    # ---- read -----------------------------------------------------------

    def get_plugin(
        self,
        plugin_id: str | None = None,
        *,
        slug: str | None = None,
        include_releases: bool = True,
    ) -> MarketplacePlugin:
        if slug is not None:
            pid = self._store.slug_index.get(slug)
            if pid is None:
                raise PluginNotFoundError(f"slug {slug!r} not found")
            plugin_id = pid
        if plugin_id is None:
            raise PluginNotFoundError("plugin_id or slug required")
        plugin = self._store.plugins.get(plugin_id)
        if plugin is None:
            raise PluginNotFoundError(f"plugin {plugin_id!r} not found")
        return plugin

    def list_public(
        self,
        *,
        category: str | None = None,
        status: str = "approved",
        limit: int = 50,
        offset: int = 0,
        sort: str = "popular",     # popular | recent | rating | name
    ) -> list[MarketplacePlugin]:
        items = [p for p in self._store.plugins.values() if p.status == status]
        if category is not None:
            items = [p for p in items if p.category == category]
        if sort == "popular":
            items.sort(key=lambda p: (-p.total_installs, -p.avg_rating, p.name))
        elif sort == "recent":
            items.sort(key=lambda p: -p.created_at)
        elif sort == "rating":
            items.sort(key=lambda p: (-p.avg_rating, -p.rating_count, p.name))
        elif sort == "name":
            items.sort(key=lambda p: p.name.lower())
        else:
            raise PublishValidationError(f"unknown sort: {sort}")
        return items[offset:offset + limit]

    def list_pending(self) -> list[MarketplacePlugin]:
        return [p for p in self._store.plugins.values()
                if p.status == "pending_review"]

    def search(
        self,
        query: str,
        *,
        category: str | None = None,
        limit: int = 25,
    ) -> list[MarketplacePlugin]:
        q = (query or "").strip().lower()
        out: list[MarketplacePlugin] = []
        for p in self._store.plugins.values():
            if p.status != "approved":
                continue
            if category is not None and p.category != category:
                continue
            haystack = " ".join([
                p.slug, p.name, p.tagline, p.description,
                " ".join(p.tags), p.author_name,
            ]).lower()
            if q and q not in haystack:
                continue
            out.append(p)
        out.sort(key=lambda p: (-p.total_installs, -p.avg_rating))
        return out[:limit]

    # ---- introspection --------------------------------------------------

    def audit_log(self, *, limit: int = 100) -> list[dict[str, Any]]:
        return list(self._store.audit)[-limit:][::-1]


# ---------------------------------------------------------------------------
# SHA-256 helper for callers uploading artifacts
# ---------------------------------------------------------------------------

def sha256_hex(data: bytes | str) -> str:
    """SHA-256 of bytes or string (utf-8), returned as lowercase hex."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()
