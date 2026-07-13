"""T2903 — Third-party Application Marketplace tests.

Coverage:

* catalog (publish, approve, reject, search, sort, validation)
* releases (semver validation, dedupe, manifest)
* install (1-click, plugin SDK fallback path, error paths)
* reviews (submit, dedupe, rating recompute, helpful)
* billing (purchase ledger, revenue split, refund, webhook signature)
* API (FastAPI endpoints for public + author + tenant + admin)
* Strapi bridge (no-op when not configured)
* Notification hooks
* Migration file (existence + key tables)

The tests are entirely offline — no DB, no Supabase, no Strapi.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

# Make `from services.marketplace ...` work in the test process.
BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset the marketplace singleton between tests."""
    from services.marketplace import reset_marketplace_service
    reset_marketplace_service()
    yield
    reset_marketplace_service()


@pytest.fixture
def svc():
    from services.marketplace import get_marketplace_service
    return get_marketplace_service()


@pytest.fixture
def published_plugin(svc):
    return svc.publish(
        slug="dingtalk-bot",
        name="DingTalk Approval Bot",
        tagline="钉钉审批机器人",
        description="Auto-approve leaves in DingTalk when match score > 0.9",
        category="integration",
        tags=["dingtalk", "approval", "automation"],
        author_id="dev-1",
        author_name="Acme Labs",
        author_email="dev@acme.io",
        pricing_model="free",
        price_cents=0,
    )


@pytest.fixture
def approved_plugin(published_plugin, svc):
    svc.catalog.add_release(
        plugin_id=published_plugin.id,
        version="1.0.0",
        artifact_url="https://artifacts.example.com/dingtalk-bot-1.0.0.tar.gz",
        artifact_sha256="a" * 64,
        changelog="initial release",
    )
    svc.approve(plugin_id=published_plugin.id, reviewer="mod-1")
    return published_plugin


# ---------------------------------------------------------------------------
# 1) Catalog — publish / approve / reject
# ---------------------------------------------------------------------------

class TestCatalog:
    def test_publish_creates_pending_listing(self, svc):
        plugin = svc.publish(
            slug="my-plugin", name="My Plugin",
            category="analytics", author_id="d1", author_name="Dev",
        )
        assert plugin.status == "pending_review"
        assert plugin.id
        assert svc.catalog.list_pending() == [plugin]

    def test_publish_validates_slug(self, svc):
        with pytest.raises(Exception):
            svc.publish(slug="Bad Slug", name="X",
                        author_id="d1", author_name="D")
        with pytest.raises(Exception):
            svc.publish(slug="-bad-", name="X",
                        author_id="d1", author_name="D")
        with pytest.raises(Exception):
            svc.publish(slug="ok", name="X",
                        author_id="d1", author_name="D")  # too short

    def test_publish_validates_category(self, svc):
        with pytest.raises(Exception):
            svc.publish(slug="x", name="X", category="invalid",
                        author_id="d", author_name="D")

    def test_publish_validates_pricing(self, svc):
        with pytest.raises(Exception):
            svc.publish(slug="x", name="X", pricing_model="free",
                        price_cents=100, author_id="d", author_name="D")
        with pytest.raises(Exception):
            svc.publish(slug="y", name="Y", pricing_model="one_time",
                        price_cents=0, author_id="d", author_name="D")

    def test_duplicate_slug_rejected(self, svc, published_plugin):
        with pytest.raises(Exception):
            svc.publish(
                slug=published_plugin.slug, name="dup",
                author_id="d2", author_name="D2",
            )

    def test_approve_changes_status(self, svc, published_plugin):
        approved = svc.approve(
            plugin_id=published_plugin.id, reviewer="mod-1",
        )
        assert approved.status == "approved"
        assert approved.reviewed_by == "mod-1"
        assert approved.reviewed_at is not None

    def test_reject_requires_reason(self, svc, published_plugin):
        with pytest.raises(Exception):
            svc.reject(plugin_id=published_plugin.id, reviewer="m",
                       reason="")

    def test_reject_records_reason(self, svc, published_plugin):
        rejected = svc.reject(
            plugin_id=published_plugin.id, reviewer="mod-1",
            reason="contains malware",
        )
        assert rejected.status == "rejected"
        assert rejected.rejection_reason == "contains malware"

    def test_list_public_only_returns_approved(self, svc, published_plugin):
        assert svc.catalog.list_public() == []  # pending, not visible
        svc.approve(plugin_id=published_plugin.id, reviewer="m")
        items = svc.catalog.list_public()
        assert len(items) == 1
        assert items[0].id == published_plugin.id

    def test_list_public_sort_modes(self, svc, approved_plugin):
        # Add 2 more approved plugins with different install counts
        for slug, installs in [("zebra-bot", 0), ("alpha-bot", 5)]:
            p = svc.publish(
                slug=slug, name=slug, category="utility",
                author_id="d", author_name="d",
            )
            svc.approve(plugin_id=p.id, reviewer="m")
            p.total_installs = installs
        popular = svc.catalog.list_public(sort="popular")
        # alpha-bot (5) first, then approved_plugin (0) and zebra-bot (0)
        assert popular[0].slug == "alpha-bot"
        # name sort: alpha < dingtalk-bot < zebra-bot
        by_name = svc.catalog.list_public(sort="name")
        assert [p.slug for p in by_name] == [
            "alpha-bot", "dingtalk-bot", "zebra-bot",
        ]
        # rating / recent sorts should not crash
        assert len(svc.catalog.list_public(sort="rating")) == 3
        assert len(svc.catalog.list_public(sort="recent")) == 3

    def test_list_public_unknown_sort_raises(self, svc, approved_plugin):
        with pytest.raises(Exception):
            svc.catalog.list_public(sort="bogus")

    def test_search_returns_matches(self, svc, approved_plugin):
        svc.publish(slug="wechat-bridge", name="WeChat Bridge",
                    category="integration", tags=["wechat"],
                    author_id="d", author_name="d")
        # approve wechat-bridge
        all_pending = svc.catalog.list_pending()
        for p in all_pending:
            svc.approve(plugin_id=p.id, reviewer="m")
        results = svc.catalog.search("wechat")
        assert any(r.slug == "wechat-bridge" for r in results)
        assert all(r.slug != "dingtalk-bot" for r in results)

    def test_search_with_category_filter(self, svc):
        for slug, cat in [("plugin-one", "video"), ("plugin-two", "analytics"),
                          ("plugin-three", "video")]:
            p = svc.publish(slug=slug, name=slug, category=cat,
                            author_id="d", author_name="d")
            svc.approve(plugin_id=p.id, reviewer="m")
        assert {p.slug for p in
                svc.catalog.search("", category="video")} == {"plugin-one", "plugin-three"}

    def test_search_empty_query_returns_all(self, svc):
        for slug in ("plugin-one", "plugin-two", "plugin-three"):
            p = svc.publish(slug=slug, name=slug, category="utility",
                            author_id="d", author_name="d")
            svc.approve(plugin_id=p.id, reviewer="m")
        assert len(svc.catalog.search("")) == 3

    def test_audit_log_records_actions(self, svc, published_plugin):
        svc.approve(plugin_id=published_plugin.id, reviewer="m")
        audit = svc.catalog.audit_log()
        assert any(a["action"] == "publish" for a in audit)
        assert any(a["action"] == "approve" for a in audit)


# ---------------------------------------------------------------------------
# 2) Releases
# ---------------------------------------------------------------------------

class TestReleases:
    def test_add_release_validates_semver(self, svc, published_plugin):
        with pytest.raises(Exception):
            svc.add_release(
                plugin_id=published_plugin.id, version="not-semver",
                artifact_url="https://x", artifact_sha256="a" * 64,
            )

    def test_add_release_validates_sha256_length(self, svc, published_plugin):
        with pytest.raises(Exception):
            svc.add_release(
                plugin_id=published_plugin.id, version="1.0.0",
                artifact_url="https://x", artifact_sha256="short",
            )

    def test_add_release_artifact_url_required(self, svc, published_plugin):
        with pytest.raises(Exception):
            svc.add_release(
                plugin_id=published_plugin.id, version="1.0.0",
                artifact_url="", artifact_sha256="a" * 64,
            )

    def test_add_release_dedupes_version(self, svc, published_plugin):
        svc.add_release(
            plugin_id=published_plugin.id, version="1.0.0",
            artifact_url="https://x", artifact_sha256="a" * 64,
        )
        with pytest.raises(Exception):
            svc.add_release(
                plugin_id=published_plugin.id, version="1.0.0",
                artifact_url="https://x", artifact_sha256="b" * 64,
            )

    def test_approve_cascades_to_pending_releases(self, svc, published_plugin):
        svc.add_release(
            plugin_id=published_plugin.id, version="1.0.0",
            artifact_url="https://x", artifact_sha256="a" * 64,
        )
        svc.approve(plugin_id=published_plugin.id, reviewer="m")
        plugin = svc.catalog.get_plugin(plugin_id=published_plugin.id)
        assert plugin.releases[0].status == "approved"

    def test_get_plugin_includes_releases(self, svc, published_plugin):
        svc.add_release(
            plugin_id=published_plugin.id, version="1.0.0",
            artifact_url="https://x", artifact_sha256="a" * 64,
        )
        plugin = svc.catalog.get_plugin(plugin_id=published_plugin.id)
        assert len(plugin.releases) == 1
        assert plugin.releases[0].version == "1.0.0"

    def test_get_plugin_not_found(self, svc):
        from services.marketplace import PluginNotFoundError
        with pytest.raises(PluginNotFoundError):
            svc.catalog.get_plugin(slug="missing")

    def test_get_plugin_by_slug(self, svc, published_plugin):
        plugin = svc.catalog.get_plugin(slug=published_plugin.slug)
        assert plugin.id == published_plugin.id

    def test_sha256_helper(self, svc):
        from services.marketplace.catalog import sha256_hex
        assert len(sha256_hex("hi")) == 64
        assert sha256_hex("hi") == sha256_hex(b"hi")


# ---------------------------------------------------------------------------
# 3) Install
# ---------------------------------------------------------------------------

class TestInstall:
    def test_install_unknown_plugin_returns_error(self, svc):
        result = svc.install(
            tenant_id="t1", slug="does-not-exist", accept_terms=True,
        )
        assert result.success is False
        assert "not_found" in result.error or "not found" in result.error

    def test_install_rejects_pending_plugin(self, svc, published_plugin):
        from services.marketplace import PublishValidationError
        with pytest.raises(PublishValidationError):
            svc.install(tenant_id="t1", slug=published_plugin.slug,
                        accept_terms=True)

    def test_install_rejects_rejected_plugin(self, svc, published_plugin):
        from services.marketplace import PublishValidationError
        svc.reject(plugin_id=published_plugin.id, reviewer="m",
                   reason="bad")
        with pytest.raises(PublishValidationError):
            svc.install(tenant_id="t1", slug=published_plugin.slug,
                        accept_terms=True)

    def test_install_paid_requires_accept_terms(self, svc, approved_plugin):
        from services.marketplace import PublishValidationError
        approved_plugin.pricing_model = "one_time"
        approved_plugin.price_cents = 1999
        with pytest.raises(PublishValidationError):
            svc.install(tenant_id="t1", slug=approved_plugin.slug,
                        accept_terms=False)

    def test_install_free_succeeds(self, svc, approved_plugin):
        result = svc.install(tenant_id="t1", slug=approved_plugin.slug)
        assert result.success
        assert result.version == "1.0.0"
        assert svc.installer.is_installed("t1", "dingtalk-bot")

    def test_install_with_specific_version(self, svc, approved_plugin):
        svc.add_release(
            plugin_id=approved_plugin.id, version="1.1.0",
            artifact_url="https://x", artifact_sha256="b" * 64,
        )
        # Re-approve so the new release is installable
        # (in this codebase, releases keep their status from add_release,
        # we just flip them manually for the test)
        approved_plugin.releases[-1].status = "approved"
        result = svc.install(tenant_id="t1", slug=approved_plugin.slug,
                             version="1.1.0")
        assert result.success
        assert result.version == "1.1.0"

    def test_install_with_unknown_version_fails(self, svc, approved_plugin):
        from services.marketplace import PublishValidationError
        with pytest.raises(PublishValidationError):
            svc.install(tenant_id="t1", slug=approved_plugin.slug,
                        version="9.9.9")

    def test_install_no_releases_fails(self, svc, approved_plugin):
        from services.marketplace import PublishValidationError
        approved_plugin.releases.clear()
        with pytest.raises(PublishValidationError):
            svc.install(tenant_id="t1", slug=approved_plugin.slug)

    def test_uninstall_removes_install(self, svc, approved_plugin):
        svc.install(tenant_id="t1", slug=approved_plugin.slug)
        result = svc.uninstall(tenant_id="t1", slug=approved_plugin.slug)
        assert result["success"] is True
        assert not svc.installer.is_installed("t1", "dingtalk-bot")

    def test_uninstall_when_not_installed(self, svc):
        result = svc.uninstall(tenant_id="t1", slug="missing")
        assert result["success"] is False
        assert result["error"] == "not_installed"

    def test_list_installed_returns_records(self, svc, approved_plugin):
        svc.install(tenant_id="t1", slug=approved_plugin.slug)
        items = svc.installer.list_installed("t1")
        assert len(items) == 1
        assert items[0]["slug"] == "dingtalk-bot"
        assert items[0]["version"] == "1.0.0"

    def test_install_increments_total(self, svc, approved_plugin):
        svc.install(tenant_id="t1", slug=approved_plugin.slug)
        svc.install(tenant_id="t2", slug=approved_plugin.slug)
        plugin = svc.catalog.get_plugin(plugin_id=approved_plugin.id)
        assert plugin.total_installs == 2

    def test_install_audit_trail(self, svc, approved_plugin):
        svc.install(tenant_id="t1", slug=approved_plugin.slug)
        actions = [a["action"] for a in svc.installer.audit]
        assert "install" in actions

    def test_install_falls_back_to_noop(self, svc, approved_plugin):
        # No SDK / manager loaded — service should still succeed.
        result = svc.install(tenant_id="t1", slug=approved_plugin.slug)
        assert result.success
        assert result.detail.get("via") == "noop"

    def test_ip_hash_is_salted(self):
        from services.marketplace.install import ip_hash
        a = ip_hash("1.2.3.4", salt="x")
        b = ip_hash("1.2.3.4", salt="y")
        assert a != b
        assert len(a) == 64


# ---------------------------------------------------------------------------
# 4) Reviews
# ---------------------------------------------------------------------------

class TestReviews:
    def test_submit_review_basic(self, svc, approved_plugin):
        r = svc.submit_review(
            plugin_id=approved_plugin.id, author_id="u1",
            author_name="Alice", rating=5, title="Great", body="Loved it",
        )
        assert r.rating == 5
        assert r.status == "published"

    def test_submit_review_validates_rating_range(self, svc, approved_plugin):
        from services.marketplace import ReviewValidationError
        with pytest.raises(ReviewValidationError):
            svc.submit_review(plugin_id=approved_plugin.id, author_id="u",
                              author_name="u", rating=0)
        with pytest.raises(ReviewValidationError):
            svc.submit_review(plugin_id=approved_plugin.id, author_id="u",
                              author_name="u", rating=6)

    def test_submit_review_dedupes_per_author(self, svc, approved_plugin):
        from services.marketplace import ReviewValidationError
        svc.submit_review(plugin_id=approved_plugin.id, author_id="u1",
                          author_name="u1", rating=4)
        with pytest.raises(ReviewValidationError):
            svc.submit_review(plugin_id=approved_plugin.id, author_id="u1",
                              author_name="u1", rating=5)

    def test_submit_review_validates_lengths(self, svc, approved_plugin):
        from services.marketplace import ReviewValidationError
        with pytest.raises(ReviewValidationError):
            svc.submit_review(
                plugin_id=approved_plugin.id, author_id="u", author_name="u",
                rating=5, title="x" * 201,
            )
        with pytest.raises(ReviewValidationError):
            svc.submit_review(
                plugin_id=approved_plugin.id, author_id="u", author_name="u",
                rating=5, body="x" * 5001,
            )

    def test_review_updates_avg_rating(self, svc, approved_plugin):
        svc.submit_review(plugin_id=approved_plugin.id, author_id="u1",
                          author_name="u1", rating=5)
        svc.submit_review(plugin_id=approved_plugin.id, author_id="u2",
                          author_name="u2", rating=3)
        plugin = svc.catalog.get_plugin(plugin_id=approved_plugin.id)
        assert plugin.rating_count == 2
        assert plugin.avg_rating == 4.0

    def test_review_summary_distribution(self, svc, approved_plugin):
        for i, rating in enumerate([5, 5, 3, 1, 1, 1], start=1):
            svc.submit_review(
                plugin_id=approved_plugin.id, author_id=f"u{i}",
                author_name=f"u{i}", rating=rating,
            )
        summary = svc.reviews.summary(approved_plugin.id)
        assert summary["count"] == 6
        assert summary["distribution"] == {
            "1": 3, "2": 0, "3": 1, "4": 0, "5": 2,
        }
        assert summary["avg"] == round((5 + 5 + 3 + 1 + 1 + 1) / 6, 2)

    def test_review_update(self, svc, approved_plugin):
        r = svc.submit_review(
            plugin_id=approved_plugin.id, author_id="u1", author_name="u1",
            rating=3,
        )
        updated = svc.reviews.update(review_id=r.id, author_id="u1", rating=5)
        assert updated.rating == 5

    def test_review_update_by_other_author_rejected(self, svc, approved_plugin):
        from services.marketplace import ReviewValidationError
        r = svc.submit_review(
            plugin_id=approved_plugin.id, author_id="u1", author_name="u1",
            rating=3,
        )
        with pytest.raises(ReviewValidationError):
            svc.reviews.update(review_id=r.id, author_id="u2", rating=5)

    def test_review_hide_excludes_from_avg(self, svc, approved_plugin):
        r = svc.submit_review(
            plugin_id=approved_plugin.id, author_id="u1", author_name="u1",
            rating=5,
        )
        svc.submit_review(
            plugin_id=approved_plugin.id, author_id="u2", author_name="u2",
            rating=1,
        )
        plugin = svc.catalog.get_plugin(plugin_id=approved_plugin.id)
        assert plugin.avg_rating == 3.0
        svc.reviews.hide(review_id=r.id, moderator="mod-1")
        assert plugin.avg_rating == 1.0
        assert plugin.rating_count == 1

    def test_mark_helpful_increments(self, svc, approved_plugin):
        r = svc.submit_review(
            plugin_id=approved_plugin.id, author_id="u1", author_name="u1",
            rating=4,
        )
        svc.reviews.mark_helpful(review_id=r.id)
        svc.reviews.mark_helpful(review_id=r.id)
        assert r.helpful_count == 2

    def test_review_sort_modes(self, svc, approved_plugin):
        r1 = svc.submit_review(
            plugin_id=approved_plugin.id, author_id="u1", author_name="u1",
            rating=1,
        )
        r2 = svc.submit_review(
            plugin_id=approved_plugin.id, author_id="u2", author_name="u2",
            rating=5,
        )
        r1.helpful_count = 5
        recent = svc.reviews.list_for_plugin(
            approved_plugin.id, sort="recent",
        )
        helpful = svc.reviews.list_for_plugin(
            approved_plugin.id, sort="helpful",
        )
        rating = svc.reviews.list_for_plugin(
            approved_plugin.id, sort="rating",
        )
        assert recent[0].id == r2.id
        assert helpful[0].id == r1.id
        assert rating[0].id == r2.id

    def test_review_unknown_plugin_raises(self, svc):
        from services.marketplace import ReviewNotFoundError
        with pytest.raises(ReviewNotFoundError):
            svc.submit_review(
                plugin_id="missing", author_id="u", author_name="u",
                rating=4,
            )

    def test_mark_helpful_unknown_review(self, svc):
        from services.marketplace import ReviewNotFoundError
        with pytest.raises(ReviewNotFoundError):
            svc.reviews.mark_helpful(review_id="missing")


# ---------------------------------------------------------------------------
# 5) Billing
# ---------------------------------------------------------------------------

class TestBilling:
    def test_purchase_free_plugin_rejected(self, svc, approved_plugin):
        from services.marketplace import PublishValidationError
        with pytest.raises(PublishValidationError):
            svc.purchase(
                plugin_id=approved_plugin.id, tenant_id="t1",
                user_id="u1", payment_method="stripe",
            )

    def test_purchase_paid_plugin(self, svc, approved_plugin):
        approved_plugin.pricing_model = "one_time"
        approved_plugin.price_cents = 2000
        approved_plugin.revenue_share = 0.7
        p = svc.purchase(
            plugin_id=approved_plugin.id, tenant_id="t1", user_id="u1",
            payment_method="stripe", currency="USD",
        )
        assert p.amount_cents == 2000
        assert p.author_share_cents == 1400
        assert p.platform_share_cents == 600
        assert p.payment_status == "pending"

    def test_purchase_invalid_method(self, svc, approved_plugin):
        from services.marketplace import PublishValidationError
        approved_plugin.pricing_model = "one_time"
        approved_plugin.price_cents = 1000
        with pytest.raises(PublishValidationError):
            svc.purchase(
                plugin_id=approved_plugin.id, tenant_id="t1", user_id="u1",
                payment_method="bitcoin",
            )

    def test_purchase_invalid_currency(self, svc, approved_plugin):
        from services.marketplace import PublishValidationError
        approved_plugin.pricing_model = "one_time"
        approved_plugin.price_cents = 1000
        with pytest.raises(PublishValidationError):
            svc.purchase(
                plugin_id=approved_plugin.id, tenant_id="t1", user_id="u1",
                currency="XYZ",
            )

    def test_mark_paid_flow(self, svc, approved_plugin):
        from services.marketplace.billing import PurchaseNotFoundError, \
            PurchaseStateError
        approved_plugin.pricing_model = "one_time"
        approved_plugin.price_cents = 1000
        p = svc.purchase(
            plugin_id=approved_plugin.id, tenant_id="t1", user_id="u1",
        )
        paid = svc.mark_purchase_paid(
            purchase_id=p.id, payment_ref="pi_xxx",
        )
        assert paid.payment_status == "paid"
        assert paid.payment_ref == "pi_xxx"
        assert paid.paid_at is not None
        # idempotent
        paid2 = svc.mark_purchase_paid(
            purchase_id=p.id, payment_ref="pi_xxx",
        )
        assert paid2.payment_status == "paid"
        # not found
        with pytest.raises(PurchaseNotFoundError):
            svc.mark_purchase_paid(purchase_id="missing",
                                   payment_ref="x")

    def test_refund_only_paid(self, svc, approved_plugin):
        from services.marketplace.billing import PurchaseStateError
        approved_plugin.pricing_model = "one_time"
        approved_plugin.price_cents = 1000
        p = svc.purchase(
            plugin_id=approved_plugin.id, tenant_id="t1", user_id="u1",
        )
        with pytest.raises(PurchaseStateError):
            svc.billing.refund(purchase_id=p.id)
        svc.mark_purchase_paid(purchase_id=p.id, payment_ref="pi_x")
        r = svc.billing.refund(purchase_id=p.id, reason="user request")
        assert r.payment_status == "refunded"

    def test_author_earnings_aggregate(self, svc, approved_plugin):
        approved_plugin.pricing_model = "one_time"
        approved_plugin.price_cents = 1000
        approved_plugin.revenue_share = 0.5
        for _ in range(3):
            p = svc.purchase(
                plugin_id=approved_plugin.id, tenant_id="t1", user_id="u1",
            )
            svc.mark_purchase_paid(purchase_id=p.id, payment_ref="pi_x")
        # Plus one pending
        svc.purchase(
            plugin_id=approved_plugin.id, tenant_id="t1", user_id="u1",
        )
        summary = svc.billing.author_earnings(author_id="dev-1")
        assert summary["paid_count"] == 3
        assert summary["pending_count"] == 1
        assert summary["paid_cents"] == 1500
        assert summary["pending_cents"] == 500

    def test_list_purchases_filter(self, svc, approved_plugin):
        approved_plugin.pricing_model = "one_time"
        approved_plugin.price_cents = 1000
        svc.purchase(
            plugin_id=approved_plugin.id, tenant_id="t1", user_id="u1",
        )
        items = svc.billing.list_purchases(tenant_id="t1")
        assert len(items) == 1
        items = svc.billing.list_purchases(tenant_id="t2")
        assert items == []
        items = svc.billing.list_purchases(plugin_id=approved_plugin.id)
        assert len(items) == 1
        items = svc.billing.list_purchases(status="paid")
        assert items == []

    def test_webhook_signature_validates(self):
        import hashlib
        import hmac
        import time as _t
        from services.marketplace.billing import BillingError
        body = json.dumps({"type": "plugin.purchased", "data": {}}).encode()
        ts = int(_t.time())
        payload = f"{ts}.".encode() + body
        secret = "topsecret"
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        b = __import__("services.marketplace.billing", fromlist=["BillingService"]).BillingService(
            __import__("services.marketplace", fromlist=["MarketplaceService"]).MarketplaceService().catalog,
        )
        # Construct the same payload as BillingService expects
        signed = f"{ts}.".encode() + body
        out = b.verify_webhook(payload=signed, signature=sig, secret=secret)
        assert out["type"] == "plugin.purchased"
        # wrong signature
        with pytest.raises(BillingError):
            b.verify_webhook(payload=signed, signature="x" * 64, secret=secret)
        # expired timestamp
        old_payload = f"{ts - 1000}.".encode() + body
        with pytest.raises(BillingError):
            b.verify_webhook(payload=old_payload, signature=sig, secret=secret)

    def test_idempotency_key_is_unique(self):
        from services.marketplace.billing import generate_idempotency_key
        keys = {generate_idempotency_key() for _ in range(50)}
        assert len(keys) == 50


# ---------------------------------------------------------------------------
# 6) FastAPI surface
# ---------------------------------------------------------------------------

class TestMarketplaceAPI:
    """FastAPI surface tests — uses a minimal app (no main.py import)."""

    @pytest.fixture
    def client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.marketplace import router as mkt_router

        app = FastAPI()
        app.include_router(mkt_router)
        with TestClient(app) as c:
            yield c

    def _override_user(self, app, *, role: str = "admin"):
        from uuid import uuid4
        from api.auth import CurrentUser
        from api.marketplace import get_current_user
        from contracts.shared import UserRole

        def _u():
            return CurrentUser(
                id=uuid4(), email="a@x.com", role=UserRole(role),
            )

        app.dependency_overrides[get_current_user] = _u

    def test_publish_endpoint_creates_listing(self, client):
        from fastapi import FastAPI
        self._override_user(client.app, role="admin")
        try:
            r = client.post("/api/marketplace/publish", json={
                "slug": "feishu-bot",
                "name": "Feishu Bot",
                "category": "integration",
                "author_id": "d1",
                "author_name": "Dev",
                "pricing_model": "free",
                "price_cents": 0,
            })
            assert r.status_code == 201, r.text
            body = r.json()
            assert body["slug"] == "feishu-bot"
            assert body["status"] == "pending_review"
        finally:
            client.app.dependency_overrides.clear()

    def test_publish_endpoint_validates_payload(self, client):
        self._override_user(client.app, role="admin")
        try:
            r = client.post("/api/marketplace/publish", json={
                "slug": "Bad Slug!", "name": "X",
                "author_id": "d", "author_name": "d",
            })
            assert r.status_code == 400
        finally:
            client.app.dependency_overrides.clear()

    def test_list_endpoint_returns_approved(self, client, approved_plugin):
        r = client.get("/api/marketplace")
        assert r.status_code == 200
        body = r.json()
        assert any(p["slug"] == "dingtalk-bot" for p in body["items"])

    def test_search_endpoint(self, client, approved_plugin):
        r = client.get("/api/marketplace/search", params={"q": "dingtalk"})
        assert r.status_code == 200
        body = r.json()
        assert body["count"] >= 1

    def test_get_plugin_404_for_missing(self, client):
        r = client.get("/api/marketplace/does-not-exist")
        assert r.status_code == 404

    def test_install_endpoint(self, client, approved_plugin):
        r = client.post(
            "/api/marketplace/dingtalk-bot/install",
            json={"tenant_id": "t1", "accept_terms": True},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True

    def test_install_installed_endpoint(self, client, approved_plugin):
        client.post(
            "/api/marketplace/dingtalk-bot/install",
            json={"tenant_id": "t1"},
        )
        r = client.get("/api/marketplace/installed",
                       params={"tenant_id": "t1"})
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 1

    def test_submit_review_endpoint(self, client, approved_plugin):
        self._override_user(client.app, role="talent_partner")
        try:
            r = client.post(
                "/api/marketplace/dingtalk-bot/reviews",
                json={"author_id": "u", "author_name": "u",
                      "rating": 5, "title": "good", "body": "ok"},
            )
            assert r.status_code == 201
        finally:
            client.app.dependency_overrides.clear()

    def test_admin_endpoints_require_role(self, client, published_plugin):
        self._override_user(client.app, role="talent_partner")
        try:
            r = client.get("/api/marketplace/admin/pending")
            assert r.status_code == 403
        finally:
            client.app.dependency_overrides.clear()

    def test_admin_endpoints_work_for_admin(self, client, published_plugin):
        self._override_user(client.app, role="admin")
        try:
            r = client.get("/api/marketplace/admin/pending")
            assert r.status_code == 200
            body = r.json()
            assert any(p["slug"] == "dingtalk-bot" for p in body["items"])

            r = client.post(
                f"/api/marketplace/admin/{published_plugin.id}/approve",
            )
            assert r.status_code == 200
            assert r.json()["status"] == "approved"

            # audit
            r = client.get("/api/marketplace/admin/audit")
            assert r.status_code == 200
        finally:
            client.app.dependency_overrides.clear()

    def test_admin_reject_requires_reason(self, client, published_plugin):
        self._override_user(client.app, role="admin")
        try:
            r = client.post(
                f"/api/marketplace/admin/{published_plugin.id}/reject",
                json={"reason": ""},
            )
            assert r.status_code == 400
            r = client.post(
                f"/api/marketplace/admin/{published_plugin.id}/reject",
                json={"reason": "spam"},
            )
            assert r.status_code == 200
            assert r.json()["status"] == "rejected"
        finally:
            client.app.dependency_overrides.clear()

    def test_purchase_and_mark_paid(self, client, approved_plugin):
        approved_plugin.pricing_model = "one_time"
        approved_plugin.price_cents = 2000
        r = client.post(
            "/api/marketplace/dingtalk-bot/purchase",
            json={
                "plugin_id": approved_plugin.id, "tenant_id": "t1",
                "user_id": "u1", "payment_method": "stripe",
            },
        )
        assert r.status_code == 201
        purchase_id = r.json()["id"]
        r = client.post(
            f"/api/marketplace/purchases/{purchase_id}/paid",
            json={"payment_ref": "pi_abc"},
        )
        assert r.status_code == 200
        assert r.json()["payment_status"] == "paid"

    def test_webhook_accepts_unsigned_in_dev(self, client, monkeypatch):
        monkeypatch.delenv("MARKETPLACE_WEBHOOK_SECRET", raising=False)
        r = client.post(
            "/api/marketplace/webhook",
            json={"type": "plugin.approved", "data": {"plugin_id": "x"}},
        )
        assert r.status_code == 200
        assert r.json()["received"] is True

    def test_stats_endpoint(self, client, approved_plugin):
        r = client.get("/api/marketplace/stats")
        assert r.status_code == 200
        body = r.json()
        assert "total_plugins" in body


# ---------------------------------------------------------------------------
# 7) Strapi bridge / notifier
# ---------------------------------------------------------------------------

class TestStrapiBridgeAndNotifier:
    def test_strapi_bridge_disabled_by_default(self):
        from services.marketplace.service import MarketplaceStrapiBridge
        b = MarketplaceStrapiBridge()
        assert b._enabled is False
        plugin = type("P", (), {"to_dict": lambda self: {"id": "x"}})()
        result = b.push_plugin(plugin)
        assert result["noop"] is True

    def test_strapi_bridge_post_returns_error_offline(self):
        from services.marketplace.service import MarketplaceStrapiBridge
        b = MarketplaceStrapiBridge(
            base_url="http://127.0.0.1:1", token="x",   # unreachable
        )
        b._enabled = True  # force enabled for test
        result = b._post("/api/test", {"a": 1})
        assert result["ok"] is False

    def test_notifier_uses_log_when_notify_unavailable(self, caplog):
        from services.marketplace.service import MarketplaceNotifier
        n = MarketplaceNotifier()
        # Inject a fake plugin
        from types import SimpleNamespace
        plugin = SimpleNamespace(
            name="x", slug="x", author_email="a@x.com",
            author_id="u", rejection_reason="bad",
        )
        n.plugin_approved(plugin=plugin)
        n.plugin_rejected(plugin=plugin)
        n.install_completed(
            tenant_id="t1", plugin=plugin,
            result=SimpleNamespace(version="1.0.0", duration_ms=12.3),
        )
        # No exception == ok (logger fallback)
        assert True


# ---------------------------------------------------------------------------
# 8) Migration file
# ---------------------------------------------------------------------------

class TestMigration:
    def test_migration_file_exists(self):
        path = Path(__file__).resolve().parents[1] / "supabase" \
            / "migrations" / "051_marketplace.sql"
        assert path.exists()
        text = path.read_text()
        for table in (
            "marketplace_plugins", "plugin_releases", "plugin_reviews",
            "plugin_downloads", "plugin_purchases", "marketplace_audit",
        ):
            assert f"CREATE TABLE" in text
            assert table in text

    def test_migration_enables_rls(self):
        path = Path(__file__).resolve().parents[1] / "supabase" \
            / "migrations" / "051_marketplace.sql"
        text = path.read_text()
        assert "ENABLE ROW LEVEL SECURITY" in text
        assert "CREATE POLICY" in text
