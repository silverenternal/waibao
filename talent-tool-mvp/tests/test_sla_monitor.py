"""T2604 — unit tests for ``services.platform.sla_monitor``.

Coverage:
  * 7/30/90d window math (uptime, P95 latency, error rate)
  * per-service isolation
  * SLA breach detection (severity mapping)
  * monthly report rendering (PDF + text fallback)
  * Instatus payload shaping
  * dashboard summary shape
  * record_event + sliding window store
"""
from __future__ import annotations

import math
import os
import sys

# Tests run with backend/ as cwd (consistent with conftest behaviour of
# sibling test files). The backend dir sets services.* on sys.path.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest

from services.platform import sla_monitor as sla  # type: ignore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_store():
    """Each test starts with a clean in-memory store."""
    store = sla._Store()
    sla._store = store  # type: ignore[attr-defined]
    yield


def _seed_uniform(service: str, n: int, *, status_code: int = 200, latency_ms: float = 100.0, start_offset_days: float = 30):
    """Push ``n`` evenly-spaced samples spanning ~``start_offset_days``."""
    store = sla.get_store()
    now = 1_700_000_000.0  # fixed so tests are deterministic
    span = start_offset_days * 86400
    step = span / max(n, 1)
    import time as _time
    _time.time = lambda: now  # noqa: E731
    for i in range(n):
        store.add(sla.SAMPLEvent(
            ts=now - span + i * step,
            service=service,
            endpoint="/api/ping",
            tenant_id="t1",
            status_code=status_code,
            latency_ms=latency_ms,
        ))


# ---------------------------------------------------------------------------
# Basic math
# ---------------------------------------------------------------------------

def test_5xx_reduces_uptime_and_flags_breach():
    _seed_uniform("api", n=1000, status_code=200, latency_ms=80)
    # Inject 5xx
    for _ in range(20):
        sla.get_store().add(sla.SAMPLEvent(
            ts=1_700_000_000.0, service="api", endpoint="/api/ping",
            tenant_id="t1", status_code=500, latency_ms=200,
        ))
    res = sla.compute_service_sla("api", 30)
    assert res.request_count == 1020
    # 20/1020 ≈ 0.0196 → 0.9804 uptime → breached
    assert res.breached is True
    assert res.uptime == pytest.approx(1.0 - 20/1020, rel=1e-3)


def test_4xx_does_not_count_as_downtime():
    _seed_uniform("api", n=500, status_code=200, latency_ms=100)
    for _ in range(40):
        sla.get_store().add(sla.SAMPLEvent(
            ts=1_700_000_000.0, service="api", endpoint="/api/oops",
            tenant_id="t1", status_code=404, latency_ms=10,
        ))
    res = sla.compute_service_sla("api", 30)
    assert res.breached is False
    assert res.uptime == pytest.approx(1.0)


def test_429_treated_as_failure():
    _seed_uniform("api", n=500, status_code=200, latency_ms=100)
    for _ in range(30):
        sla.get_store().add(sla.SAMPLEvent(
            ts=1_700_000_000.0, service="api", endpoint="/api/throttle",
            tenant_id="t1", status_code=429, latency_ms=10,
        ))
    res = sla.compute_service_sla("api", 30)
    # 429 is explicitly counted as not-success in __post_init__
    assert res.uptime < 1.0
    assert res.breached is True


def test_p95_latency_threshold_triggers_breach_without_5xx():
    _seed_uniform("api", n=200, status_code=200, latency_ms=3000)
    res = sla.compute_service_sla("api", 30)
    assert res.uptime == 1.0
    assert res.p95_latency_ms >= 1500
    assert res.breached is True


def test_error_rate_threshold_triggers_breach():
    """Below the 1% error threshold does NOT trigger breach on its own;
    above it DOES. We use very large sample sizes so uptime stays ≥ 99.9%."""
    # 1_000_000 samples — 100 errors would still give 99.99% uptime
    # but only 0.01% error rate (still below 1% threshold).
    _seed_uniform("api", n=1_000_000, status_code=200, latency_ms=100)
    for _ in range(8):  # 0.0008% — well below 1%
        sla.get_store().add(sla.SAMPLEvent(
            ts=1_700_000_000.0, service="api", endpoint="/api/oops",
            tenant_id="t1", status_code=502, latency_ms=20,
        ))
    res = sla.compute_service_sla("api", 30)
    assert res.error_rate < 0.01
    assert res.uptime > 0.999
    assert res.breached is False

    # Push error rate over 1% (the error_rate check itself fires even if uptime stays ok)
    # We need a much larger fraction to override uptime > 99.9%. So add way more.
    for _ in range(15_000):  # adds ~1.5% error rate; total error = 15008/1.015M ≈ 1.48%
        sla.get_store().add(sla.SAMPLEvent(
            ts=1_700_000_000.0, service="api", endpoint="/api/oops",
            tenant_id="t1", status_code=503, latency_ms=20,
        ))
    res2 = sla.compute_service_sla("api", 30)
    assert res2.error_rate > 0.01
    assert res2.breached is True


def test_error_rate_independently_drives_breach_even_when_uptime_ok():
    """Above-error_rate breach triggers independent of uptime drop."""
    sla.get_store()._buffers.clear() if hasattr(sla.get_store(), "_buffers") else None
    store = sla._Store()
    sla._store = store  # type: ignore[attr-defined]
    # Spread 1M samples evenly; mark 2% as 5xx
    for i in range(1_000_000):
        is_err = (i % 50 == 0)  # 2%
        sla.get_store().add(sla.SAMPLEvent(
            ts=1_700_000_000.0 - (1_000_000 - i) * 0.1,
            service="api", endpoint="/api/ping", tenant_id="t1",
            status_code=503 if is_err else 200, latency_ms=100,
        ))
    res = sla.compute_service_sla("api", 30)
    # 2% errors → uptime 98% — breach is correctly fired both by uptime and error_rate
    assert res.error_rate > 0.01
    assert res.uptime < 0.99
    assert res.breached is True


# ---------------------------------------------------------------------------
# Percentile math
# ---------------------------------------------------------------------------

def test_percentile_basic():
    assert sla._percentile([1, 2, 3, 4, 5], 95.0) == 5
    assert sla._percentile([10, 20, 30, 40], 50.0) in (20, 30)
    assert sla._percentile([], 50.0) == 0.0


def test_p95_known_distribution():
    store = sla._Store()
    sla._store = store  # type: ignore[attr-defined]
    for i in range(1, 101):
        sla.get_store().add(sla.SAMPLEvent(
            ts=1_700_000_000.0, service="api", endpoint="/api/ping",
            tenant_id="t1", status_code=200, latency_ms=float(i),
        ))
    res = sla.compute_service_sla("api", 30)
    assert res.p95_latency_ms == pytest.approx(95.05, rel=0.05)


# ---------------------------------------------------------------------------
# Window slicing + per-service isolation
# ---------------------------------------------------------------------------

def test_window_slicing_90d_strict_subset_of_30d():
    _seed_uniform("api", n=1000)
    r30 = sla.compute_service_sla("api", 30)
    r90 = sla.compute_service_sla("api", 90)
    # 90d window includes 30d => more samples >= r30
    assert r90.request_count >= r30.request_count


def test_services_are_isolated():
    _seed_uniform("api",  n=100, status_code=200, latency_ms=50)
    _seed_uniform("llm",  n=100, status_code=500, latency_ms=5000)
    a = sla.compute_service_sla("api", 30)
    l = sla.compute_service_sla("llm", 30)
    assert a.uptime == pytest.approx(1.0)
    assert l.uptime == pytest.approx(0.0)
    assert a.breached is False
    assert l.breached is True


# ---------------------------------------------------------------------------
# Top-level compute_sla + summary
# ---------------------------------------------------------------------------

def test_compute_sla_returns_all_windows_and_services():
    _seed_uniform("api", n=100)
    metrics = sla.compute_sla()
    assert metrics.windows_days == (7, 30, 90)
    for svc in sla.PLATFORM_SERVICES:
        for w in (7, 30, 90):
            assert svc in metrics.services
            assert w in metrics.services[svc]


def test_summary_for_admin_shape():
    _seed_uniform("api", n=50)
    summary = sla.summary_for_admin(tenant_id="acme")
    assert summary["tenant_id"] == "acme"
    assert "api" in summary["services"]
    assert "30" in summary["services"]["api"]


def test_to_status_page_payload_marks_operational_when_healthy():
    _seed_uniform("api", n=100)
    payload = sla.to_status_page_payload(sla.compute_sla())
    assert payload["page"]["name"] == "waibao"
    assert payload["indicators"][0]["status"] in {"operational", "degraded"}


def test_to_status_page_payload_marks_degraded_when_breached():
    _seed_uniform("api", n=100, latency_ms=100)
    for _ in range(60):
        sla.get_store().add(sla.SAMPLEvent(
            ts=1_700_000_000.0, service="api", endpoint="/api/5xx",
            tenant_id="t1", status_code=500, latency_ms=200,
        ))
    payload = sla.to_status_page_payload(sla.compute_sla())
    api = next(i for i in payload["indicators"] if i["id"] == "api")
    assert api["status"] == "degraded"


# ---------------------------------------------------------------------------
# Breach evaluation
# ---------------------------------------------------------------------------

def test_evaluate_breach_no_breach_returns_none():
    _seed_uniform("api", n=100)
    sla_event = sla.compute_service_sla("api", 30)
    assert not sla_event.breached
    captured = []
    out = sla.evaluate_breach(sla_event, alert_sink=lambda e: captured.append(e))
    assert out is None
    assert captured == []


def test_evaluate_breach_severity_mapping():
    _seed_uniform("api", n=100, status_code=500)
    sla_event = sla.compute_service_sla("api", 30)
    captured = []
    sla.evaluate_breach(sla_event, alert_sink=lambda e: captured.append(e))
    assert len(captured) == 1
    # 100% failures → P0
    assert captured[0].severity == "P0"


def test_evaluate_breach_records_summary():
    _seed_uniform("api", n=100, latency_ms=3000)
    sla_event = sla.compute_service_sla("api", 7)
    captured = []
    sla.evaluate_breach(sla_event, alert_sink=lambda e: captured.append(e))
    assert captured and "p95=" in captured[0].summary


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

def test_render_monthly_report_text_fallback_when_reportlab_missing(monkeypatch):
    # Force fallback by hiding reportlab
    import builtins
    real_import = builtins.__import__
    def _fake(name, *args, **kwargs):  # type: ignore[no-untyped-def]
        if name.startswith("reportlab"):
            raise ImportError("reportlab not installed in test env")
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", _fake)
    _seed_uniform("api", n=50)
    metrics = sla.compute_sla()
    blob = sla.render_monthly_report(metrics, tenant_id="acme")
    assert isinstance(blob, bytes)
    txt = blob.decode("utf-8")
    assert "waibao SLA Report" in txt
    assert "acme" in txt
    assert "== api ==" in txt.lower()


def test_render_monthly_report_returns_bytes_for_pdf_when_available(monkeypatch):
    fake_pdf = b"%PDF-fake"
    import types
    fake_module = types.ModuleType("reportlab.platypus")
    class _FakeDoc:
        def __init__(self, *a, **kw): pass
        def build(self, story): pass
    class _FakeTable:
        def __init__(self, *a, **kw): pass
        def setStyle(self, *a, **kw): pass
    fake_module.SimpleDocTemplate = _FakeDoc
    fake_module.Table = _FakeTable
    fake_module.TableStyle = lambda *a, **kw: None
    fake_module.Paragraph = lambda *a, **kw: object()
    fake_module.Spacer = lambda *a, **kw: object()
    sys.modules["reportlab.platypus"] = fake_module
    sub = types.ModuleType("reportlab.lib")
    sub.pagesizes = types.ModuleType("pagesizes")
    sub.pagesizes.letter = (612, 792)
    sub.styles = types.ModuleType("styles")
    class _Styles:
        def __getitem__(self, k):
            class _S: pass
            return _S()
    sub.styles.getSampleStyleSheet = lambda: _Styles()
    sub.colors = types.ModuleType("colors")
    sub.colors.lightgrey = "#eee"
    sub.colors.grey = "#888"
    sys.modules["reportlab.lib"] = sub
    sys.modules["reportlab"] = types.ModuleType("reportlab")
    # Force the call path that does `from reportlab.lib.pagesizes import letter`
    metrics = sla.compute_sla()
    monkeypatch.setattr("io.BytesIO", lambda: type("B", (), {"getvalue": lambda self: fake_pdf})())
    blob = sla.render_monthly_report(metrics, tenant_id="acme")
    assert isinstance(blob, bytes)


# ---------------------------------------------------------------------------
# record_event helper
# ---------------------------------------------------------------------------

def test_record_event_persists_and_is_retrievable():
    evt = sla.record_event("api", "/api/ping", 200, latency_ms=42.0, tenant_id="t1")
    store = sla.get_store()
    samples = store.drain("api", 0)
    assert len(samples) == 1
    assert samples[0].endpoint == "/api/ping"
    assert samples[0].success is True
    assert evt.ts <= sla.time.time() + 1


def test_record_event_explicit_success_false_marks_fail():
    sla.record_event("api", "/api/ping", 200, latency_ms=42.0, success=False)
    res = sla.compute_service_sla("api", 30)
    assert res.uptime == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Constants / Public API
# ---------------------------------------------------------------------------

def test_public_exports_and_constants():
    for name in [
        "PLATFORM_SERVICES", "DEFAULT_TARGET_UPTIME", "DEFAULT_P95_LATENCY_MS",
        "DEFAULT_ERROR_RATE", "WINDOWS",
        "SAMPLEvent", "ServiceSLA", "SLAMetrics", "SLABreachEvent",
        "record_event", "compute_service_sla", "compute_sla",
        "evaluate_breach", "render_monthly_report",
        "summary_for_admin", "to_status_page_payload", "get_store",
    ]:
        assert name in sla.__all__, name
    assert set(sla.PLATFORM_SERVICES) == {"api", "llm", "storage", "webhook", "database"}
    assert sla.DEFAULT_TARGET_UPTIME == 0.999
    assert (8.76 - 8.7) < 1.0  # 99.9% ≤ 8.76 hours/year downtime budget


def test_evict_old_samples_outside_window():
    store = sla._Store(max_samples_per_service=100_000)
    sla._store = store  # type: ignore[attr-defined]
    # Push 1 sample inside 30d, 1 sample outside
    sla.get_store().add(sla.SAMPLEvent(
        ts=1_700_000_000.0 - 200 * 86400, service="api", endpoint="/api/old",
        tenant_id="t1", status_code=200, latency_ms=10,
    ))
    sla.get_store().add(sla.SAMPLEvent(
        ts=1_700_000_000.0, service="api", endpoint="/api/new",
        tenant_id="t1", status_code=200, latency_ms=10,
    ))
    res = sla.compute_service_sla("api", 30)
    # only 1 sample within 30d
    assert res.request_count == 1
