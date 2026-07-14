"""v10.0 T5017 — tests for 3-tier rate limiting, webhook SSRF guard, and CSRF."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.security.ssrf import (
    SSRFError,
    assert_safe_url,
    is_private_ip,
    is_safe_url,
)
from services.security.csrf import (
    CSRF_COOKIE,
    CSRF_HEADER,
    CSRFMiddleware,
    generate_token,
    install_csrf,
    verify_token,
)
from services.security.rate_limiter import (
    DEFAULT_L1_PER_MIN,
    TIER_L1,
    TIER_L2,
    TIER_L3,
    check,
    RateLimitDecision,
)


# ===========================================================================
# SSRF
# ===========================================================================
class TestSSRF:
    @pytest.mark.parametrize("url", [
        "http://127.0.0.1/",
        "http://localhost/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://metadata.google.internal/computeMetadata/",
        "http://[::1]/",
        "http://service.internal/",
        "ftp://example.com/",
        "file:///etc/passwd",
        "gopher://x/",
        "",
    ])
    def test_unsafe_urls_rejected(self, url):
        with pytest.raises((SSRFError, AssertionError)):
            assert_safe_url(url)

    @pytest.mark.parametrize("url", [
        "https://example.com/webhook",
        "http://8.8.8.8/",           # public IP literal
        "https://hooks.slack.com/x",
    ])
    def test_safe_urls_accepted(self, url):
        assert_safe_url(url)  # no raise

    def test_private_ip_classification(self):
        assert is_private_ip("127.0.0.1")
        assert is_private_ip("10.1.2.3")
        assert is_private_ip("172.16.0.1")
        assert is_private_ip("192.168.0.1")
        assert is_private_ip("169.254.169.254")
        assert is_private_ip("::1")
        assert not is_private_ip("8.8.8.8")
        assert not is_private_ip("1.1.1.1")

    def test_is_safe_url_non_raising(self):
        assert is_safe_url("https://ok.example.com") is True
        assert is_safe_url("http://127.0.0.1") is False

    def test_ipv4_mapped_ipv6_blocked(self):
        assert is_private_ip("::ffff:127.0.0.1")

    def test_egress_allowlist(self, monkeypatch):
        import services.security.ssrf as ssrf_mod
        monkeypatch.setattr(ssrf_mod, "EGRESS_ALLOWLIST", frozenset({"allow.example.com"}))
        assert_safe_url("https://allow.example.com/x")
        with pytest.raises(SSRFError):
            assert_safe_url("https://other.example.com/x")


# ===========================================================================
# 3-tier rate limiter (pure decision logic)
# ===========================================================================
class FakeLimiter:
    """Records calls and lets the Nth call against a key fail."""

    def __init__(self):
        self.counts: dict[str, int] = {}
        self.limits: dict[str, int] = {}

    def _consume(self, key, limit):
        self.limits[key] = limit
        self.counts[key] = self.counts.get(key, 0) + 1
        return (self.counts[key] <= limit, 60)


class TestRateLimiter:
    def test_anonymous_only_hits_l1(self):
        fl = FakeLimiter()
        d = check("1.2.3.4", None, None, limiter=fl, l1_per_min=10)
        assert d.allowed is True
        assert "ip:1.2.3.4" in fl.counts
        assert "user:None" not in fl.counts

    def test_authenticated_hits_all_three(self):
        fl = FakeLimiter()
        check("1.2.3.4", "u1", "t1", limiter=fl)
        assert "ip:1.2.3.4" in fl.counts
        assert "user:u1" in fl.counts
        assert "tenant:t1" in fl.counts

    def test_l1_violation_short_circuits_and_reports_tier(self):
        fl = FakeLimiter()
        # force L1 to fail on the 2nd call (limit 1)
        check("1.2.3.4", "u1", "t1", limiter=fl, l1_per_min=1)
        d = check("1.2.3.4", "u1", "t1", limiter=fl, l1_per_min=1)
        assert d.allowed is False
        assert d.tier == TIER_L1
        assert d.retry_after_seconds == 60

    def test_l2_violation_when_user_specific(self):
        fl = FakeLimiter()
        check("1.2.3.4", "u1", "t1", limiter=fl, l2_per_min=1)
        d = check("1.2.3.4", "u1", "t1", limiter=fl, l2_per_min=1)
        assert d.allowed is False
        assert d.tier == TIER_L2

    def test_l3_tenant_violation(self):
        fl = FakeLimiter()
        check("1.2.3.4", "u1", "t1", limiter=fl, l3_per_min=1)
        d = check("1.2.3.4", "u1", "t1", limiter=fl, l3_per_min=1)
        assert d.allowed is False
        assert d.tier == TIER_L3

    def test_different_ips_are_independent(self):
        fl = FakeLimiter()
        check("1.1.1.1", None, None, limiter=fl, l1_per_min=1)
        d = check("2.2.2.2", None, None, limiter=fl, l1_per_min=1)
        assert d.allowed is True


# ===========================================================================
# CSRF
# ===========================================================================
class TestCSRF:
    def test_token_roundtrip(self):
        tok = generate_token()
        assert verify_token(tok) is True
        assert verify_token("") is False
        assert verify_token("garbage") is False
        assert verify_token("a.b.c") is False  # bad signature

    def test_tampered_token_rejected(self):
        tok = generate_token()
        rand, ts, sig = tok.split(".")
        bad = f"{rand}.{ts}.deadbeef"
        assert verify_token(bad) is False

    def test_safe_method_sets_cookie(self):
        app = FastAPI()

        @app.get("/x")
        def x():
            return {"ok": True}

        app.add_middleware(CSRFMiddleware, enabled=True)
        with TestClient(app) as c:
            r = c.get("/x")
            assert r.status_code == 200
            assert CSRF_COOKIE in r.cookies

    def test_unsafe_without_token_rejected(self):
        app = FastAPI()

        @app.post("/x")
        def x():
            return {"ok": True}

        app.add_middleware(CSRFMiddleware, enabled=True)
        with TestClient(app) as c:
            r = c.post("/x")
            assert r.status_code == 403
            assert r.json()["code"] == "csrf_failed"

    def test_unsafe_with_jwt_header_exempt(self):
        app = FastAPI()

        @app.post("/x")
        def x():
            return {"ok": True}

        app.add_middleware(CSRFMiddleware, enabled=True)
        with TestClient(app) as c:
            r = c.post("/x", headers={"Authorization": "Bearer eyxxx"})
            assert r.status_code == 200

    def test_double_submit_accepts_matching_token(self):
        app = FastAPI()

        @app.post("/x")
        def x():
            return {"ok": True}

        app.add_middleware(CSRFMiddleware, enabled=True)
        tok = generate_token()
        with TestClient(app) as c:
            # Send the cookie value directly in the Cookie header + matching
            # X-CSRF-Token header — this is exactly the double-submit contract.
            r = c.post("/x", headers={CSRF_HEADER: tok, "Cookie": f"{CSRF_COOKIE}={tok}"})
            assert r.status_code == 200, r.text

    def test_double_submit_rejects_mismatched_token(self):
        app = FastAPI()

        @app.post("/x")
        def x():
            return {"ok": True}

        app.add_middleware(CSRFMiddleware, enabled=True)
        with TestClient(app) as c:
            cookie_tok = generate_token()
            r = c.post(
                "/x",
                headers={CSRF_HEADER: generate_token(), "Cookie": f"{CSRF_COOKIE}={cookie_tok}"},
            )
            assert r.status_code == 403

    def test_disabled_is_passthrough(self):
        app = FastAPI()

        @app.post("/x")
        def x():
            return {"ok": True}

        app.add_middleware(CSRFMiddleware, enabled=False)
        with TestClient(app) as c:
            r = c.post("/x")
            assert r.status_code == 200

    def test_install_csrf_idempotent(self):
        app = FastAPI()
        install_csrf(app)
        n1 = len(app.user_middleware)
        install_csrf(app)
        assert len(app.user_middleware) == n1


# ===========================================================================
# Webhook dispatcher SSRF integration
# ===========================================================================
class TestWebhookSSRF:
    def test_register_blocks_private_url(self):
        import asyncio
        from services.webhook.dispatcher import WebhookDispatcher
        from services.webhook.types import WebhookConfig, WebhookEvent
        d = WebhookDispatcher()
        cfg = WebhookConfig(
            id="c1", tenant_id="t1", url="http://169.254.169.254/latest/",
            secret="s", events=[WebhookEvent.TICKET_CREATED],
        )
        with pytest.raises(SSRFError):
            d.register(cfg)

    def test_register_accepts_public_url(self):
        from services.webhook.dispatcher import WebhookDispatcher
        from services.webhook.types import WebhookConfig, WebhookEvent
        d = WebhookDispatcher()
        cfg = WebhookConfig(
            id="c1", tenant_id="t1", url="https://example.com/hook",
            secret="s", events=[WebhookEvent.TICKET_CREATED],
        )
        d.register(cfg)  # no raise
        assert "c1" in d._configs

    def test_deliver_dead_letters_ssrf(self):
        import asyncio
        from services.webhook.dispatcher import WebhookDispatcher
        from services.webhook.types import WebhookConfig, WebhookPayload, WebhookEvent
        d = WebhookDispatcher()
        # Bypass register's check by poking the config directly, then ensure
        # _deliver re-validates and dead-letters.
        cfg = WebhookConfig(
            id="c1", tenant_id="t1", url="http://10.0.0.99/internal",
            secret="s", events=[WebhookEvent.TICKET_CREATED],
        )
        d._configs["c1"] = cfg
        payload = WebhookPayload.make(WebhookEvent.TICKET_CREATED, "t1", {"id": 1})
        rec = asyncio.run(d._deliver(cfg, payload))
        assert "ssrf" in (rec.last_error or "")
        # dead-lettered exactly once (no retries consumed for SSRF)
        assert rec.attempt == 1
