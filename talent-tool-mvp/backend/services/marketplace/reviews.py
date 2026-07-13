"""Reviews & ratings for marketplace plugins.

One author can publish at most one review per plugin (service-level
constraint — Supabase doesn't have a unique index by tenant_id because
``author_id`` may be a user or org).

A review re-computes the plugin's ``avg_rating`` and ``rating_count``.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from .catalog import CatalogService, PluginNotFoundError, PublishValidationError

logger = logging.getLogger(__name__)


class ReviewValidationError(PublishValidationError):
    """Review-level validation error."""


class ReviewNotFoundError(Exception):
    pass


@dataclass
class Review:
    id: str
    plugin_id: str
    author_id: str
    author_name: str
    rating: int
    title: str = ""
    body: str = ""
    status: str = "published"
    helpful_count: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "plugin_id": self.plugin_id,
            "author_id": self.author_id,
            "author_name": self.author_name,
            "rating": self.rating,
            "title": self.title,
            "body": self.body,
            "status": self.status,
            "helpful_count": self.helpful_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class ReviewService:
    def __init__(self, catalog: CatalogService) -> None:
        self.catalog = catalog
        # plugin_id -> { author_id -> Review }
        self._reviews: dict[str, dict[str, Review]] = {}

    def submit(
        self,
        *,
        plugin_id: str,
        author_id: str,
        author_name: str,
        rating: int,
        title: str = "",
        body: str = "",
    ) -> Review:
        if not (1 <= rating <= 5):
            raise ReviewValidationError(
                f"rating must be 1..5, got {rating}"
            )
        if not author_id or not author_name:
            raise ReviewValidationError("author_id and author_name required")
        if len(title) > 200:
            raise ReviewValidationError("title too long (max 200)")
        if len(body) > 5000:
            raise ReviewValidationError("body too long (max 5000)")
        try:
            plugin = self.catalog.get_plugin(plugin_id=plugin_id)
        except PluginNotFoundError as exc:
            raise ReviewNotFoundError(str(exc)) from exc
        existing = self._reviews.get(plugin.id, {}).get(author_id)
        if existing is not None:
            raise ReviewValidationError(
                f"author {author_id!r} already reviewed {plugin.slug!r}; "
                "use update instead"
            )
        review = Review(
            id=str(uuid.uuid4()),
            plugin_id=plugin.id,
            author_id=author_id,
            author_name=author_name,
            rating=rating,
            title=title.strip(),
            body=body.strip(),
        )
        self._reviews.setdefault(plugin.id, {})[author_id] = review
        self._recompute_rating(plugin.id)
        self.catalog._store.append_audit({  # noqa: SLF001
            "plugin_id": plugin.id,
            "action": "review",
            "actor": author_id,
            "detail": {"rating": rating, "review_id": review.id},
            "created_at": time.time(),
        })
        return review

    def update(
        self,
        *,
        review_id: str,
        author_id: str,
        rating: int | None = None,
        title: str | None = None,
        body: str | None = None,
    ) -> Review:
        review = self._find_by_id(review_id)
        if review.author_id != author_id:
            raise ReviewValidationError("cannot edit another author's review")
        if rating is not None:
            if not (1 <= rating <= 5):
                raise ReviewValidationError(f"rating must be 1..5, got {rating}")
            review.rating = rating
        if title is not None:
            review.title = title.strip()[:200]
        if body is not None:
            review.body = body.strip()[:5000]
        review.updated_at = time.time()
        self._recompute_rating(review.plugin_id)
        return review

    def hide(self, *, review_id: str, moderator: str) -> Review:
        review = self._find_by_id(review_id)
        review.status = "hidden"
        self._recompute_rating(review.plugin_id)
        self.catalog._store.append_audit({  # noqa: SLF001
            "plugin_id": review.plugin_id,
            "action": "review",
            "actor": moderator,
            "detail": {"hide": True, "review_id": review_id},
            "created_at": time.time(),
        })
        return review

    def mark_helpful(self, *, review_id: str) -> Review:
        review = self._find_by_id(review_id)
        review.helpful_count += 1
        return review

    def list_for_plugin(
        self,
        plugin_id: str,
        *,
        status: str = "published",
        limit: int = 50,
        offset: int = 0,
        sort: str = "recent",       # recent | helpful | rating
    ) -> list[Review]:
        plugin = self.catalog.get_plugin(plugin_id=plugin_id)
        reviews = list(self._reviews.get(plugin.id, {}).values())
        if status is not None:
            reviews = [r for r in reviews if r.status == status]
        if sort == "recent":
            reviews.sort(key=lambda r: -r.created_at)
        elif sort == "helpful":
            reviews.sort(key=lambda r: (-r.helpful_count, -r.created_at))
        elif sort == "rating":
            reviews.sort(key=lambda r: (-r.rating, -r.created_at))
        else:
            raise ReviewValidationError(f"unknown sort: {sort}")
        return reviews[offset:offset + limit]

    def summary(self, plugin_id: str) -> dict[str, Any]:
        plugin = self.catalog.get_plugin(plugin_id=plugin_id)
        reviews = [
            r for r in self._reviews.get(plugin.id, {}).values()
            if r.status == "published"
        ]
        if not reviews:
            return {
                "plugin_id": plugin.id,
                "count": 0, "avg": 0.0,
                "distribution": {str(i): 0 for i in range(1, 6)},
            }
        dist = {str(i): 0 for i in range(1, 6)}
        for r in reviews:
            dist[str(r.rating)] += 1
        avg = sum(r.rating for r in reviews) / len(reviews)
        return {
            "plugin_id": plugin.id,
            "count": len(reviews),
            "avg": round(avg, 2),
            "distribution": dist,
        }

    # ---- helpers --------------------------------------------------------

    def _find_by_id(self, review_id: str) -> Review:
        for by_author in self._reviews.values():
            for r in by_author.values():
                if r.id == review_id:
                    return r
        raise ReviewNotFoundError(f"review {review_id!r} not found")

    def _recompute_rating(self, plugin_id: str) -> None:
        plugin = self.catalog.get_plugin(plugin_id=plugin_id)
        published = [
            r for r in self._reviews.get(plugin.id, {}).values()
            if r.status == "published"
        ]
        plugin.rating_count = len(published)
        if plugin.rating_count == 0:
            plugin.avg_rating = 0.0
        else:
            plugin.avg_rating = round(
                sum(r.rating for r in published) / plugin.rating_count, 2
            )
        plugin.updated_at = time.time()
