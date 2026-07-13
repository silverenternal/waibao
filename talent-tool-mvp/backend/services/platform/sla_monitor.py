"""T2604 - SLA Monitor (7d / 30d / 90d) for the 5 platform services.

设计目标 (per docs/SLA.md):
  - 计算每个服务的 7/30/90 天 uptime / P95 latency / 错误率
  - 目标 uptime 99.9% (≤ 8.7 小时/年 downtime)
  - 异常 (SLA breach → 严重度映射) 自动复用 v6.0 告警通道

数据源:
  - Prometheus ``/api/v1/query_range`` (如果有 ``PROMETHEUS_URL`` 环境变量)
  - 降级到本地 metric store (in-memory + optional JSON dump)
  - 事件从 base.py EventBus 流入 (sliding window 1m/5m/1h)

API:
  - :func:`compute_sla`            主要入口, 返回 :class:`SLAMetrics`
  - :func:`record_event`           单事件记录 (请求响应)
  - :func:`evaluate_breach`        触发异常告警
  - :func:`render_monthly_report`  生成月度 PDF (ReportLab)

测试: tests/test_sla_monitor.py
"""
from __future__ import annotations

import io
import json
import logging
import math
import os
import statistics
import threading
import time
import urllib.parse
import urllib.request
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Deque, Iterable

logger = logging.getLogger("recruittech.platform.sla_monitor")


# ---------------------------------------------------------------------------
# 常量 / 配置
# ---------------------------------------------------------------------------

#: Five platform services monitored for 99.9% availability.
PLATFORM_SERVICES: tuple[str, ...] = ("api", "llm", "storage", "webhook", "database")

#: Target uptime per service (proportion, e.g. 0.999 = 99.9%).
DEFAULT_TARGET_UPTIME = 0.999

#: P95 latency threshold (ms). Exceed => "degraded".
DEFAULT_P95_LATENCY_MS = 1500.0

#: Error rate threshold (proportion). Exceed => "breach".
DEFAULT_ERROR_RATE = 0.01  # 1%

#: Eval windows (days).
WINDOWS = (7, 30, 90)

# Env
ENV_PROM_URL = "PROMETHEUS_URL"
ENV_DRY_RUN = "SLA_DRY_RUN"


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class SAMPLEvent:
    """One request sample feeding the SLA calculator."""

    ts: float                       # epoch seconds
    service: str                    # PLATFORM_SERVICES entry
    endpoint: str                   # route, e.g. /api/match
    tenant_id: str | None
    status_code: int
    latency_ms: float
    success: bool | None = None     # explicit override; else derived from status_code
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.success is None:
            self.success = 200 <= self.status_code < 500 and self.status_code != 429


@dataclass
class ServiceSLA:
    """SLA numbers for one service in one window."""

    service: str
    window_days: int
    uptime: float                               # 0.0 - 1.0
    p95_latency_ms: float
    error_rate: float
    request_count: int
    breached: bool
    target_uptime: float
    evaluated_at: str                           # ISO-8601 UTC

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SLAMetrics:
    """Full SLA roll-up, per service, per window."""

    generated_at: str
    windows_days: tuple[int, ...]
    services: dict[str, dict[int, ServiceSLA]] = field(default_factory=dict)
    overall_breaches: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "windows_days": list(self.windows_days),
            "services": {
                svc: {str(w): asdict(s) for w, s in windows.items()}
                for svc, windows in self.services.items()
            },
            "overall_breaches": list(self.overall_breaches),
        }


@dataclass
class SLABreachEvent:
    """Notify via AlertingService when SLA drops below target."""

    service: str
    window_days: int
    uptime: float
    target_uptime: float
    p95_latency_ms: float
    error_rate: float
    severity: str                # P0 / P1 / P2
    summary: str
    fired_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Storage Layer (in-memory + pluggable backend)
# ---------------------------------------------------------------------------

class _Store:
    """Per-service sliding-window sample buffer.

    Each service keeps up to ``max_samples_per_service`` events; eviction is
    FIFO by timestamp so a long-running process naturally truncates old data.
    """

    def __init__(self, max_samples_per_service: int = 2_000_000) -> None:
        self._max = max_samples_per_service
        self._buffers: dict[str, Deque[SAMPLEvent]] = {
            s: deque(maxlen=max_samples_per_service) for s in PLATFORM_SERVICES
        }
        self._lock = threading.Lock()

    def add(self, evt: SAMPLEvent) -> None:
        if evt.service not in self._buffers:
            # Allow dynamic services (test fixtures).
            self._buffers.setdefault(evt.service, deque(maxlen=self._max))
        with self._lock:
            self._buffers[evt.service].append(evt)

    def add_many(self, evts: Iterable[SAMPLEvent]) -> None:
        for evt in evts:
            self.add(evt)

    def drain(self, service: str, since_ts: float) -> list[SAMPLEvent]:
        with self._lock:
            buf = self._buffers.get(service)
            if not buf:
                return []
            return [e for e in buf if e.ts >= since_ts]

    def latest_ts(self, service: str) -> float:
        with self._lock:
            buf = self._buffers.get(service)
            if not buf:
                return 0.0
            return buf[-1].ts


_store = _Store()


def get_store() -> _Store:
    """Public accessor for tests / metrics endpoints."""
    return _store


# ---------------------------------------------------------------------------
# Recording API
# ---------------------------------------------------------------------------

def record_event(
    service: str,
    endpoint: str,
    status_code: int,
    latency_ms: float,
    tenant_id: str | None = None,
    success: bool | None = None,
    **metadata: Any,
) -> SAMPLEvent:
    """Convenience helper: package + persist one sample."""
    evt = SAMPLEvent(
        ts=time.time(),
        service=service,
        endpoint=endpoint,
        tenant_id=tenant_id,
        status_code=status_code,
        latency_ms=float(latency_ms),
        success=success,
        metadata=dict(metadata),
    )
    get_store().add(evt)
    return evt


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------

def _percentile(values: list[float], p: float) -> float:
    """Standard nearest-rank percentile. ``p`` in 0..100."""
    if not values:
        return 0.0
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, int(round((p / 100.0) * (len(ordered) - 1)))))
    return ordered[k]


def _uptime_per_window(events: list[SAMPLEvent]) -> float:
    """Uptime = fraction of *successful* events (excluding 4xx client errors).

    Requests with 5xx or explicit success=False count as downtime. 4xx (except
    429 throttling) reflects client mistakes, not platform outages.
    """
    if not events:
        return 1.0
    bad = sum(1 for e in events if (not e.success) or e.status_code >= 500)
    return 1.0 - (bad / len(events))


def _error_rate(events: list[SAMPLEvent]) -> float:
    if not events:
        return 0.0
    err = sum(1 for e in events if e.status_code >= 500 or e.success is False)
    return err / len(events)


def compute_service_sla(
    service: str,
    window_days: int,
    target_uptime: float = DEFAULT_TARGET_UPTIME,
    store: _Store | None = None,
) -> ServiceSLA:
    """Aggregate :class:`ServiceSLA` for a single service + window."""
    store = store or get_store()
    now = time.time()
    cutoff = now - (window_days * 86400.0)
    events = store.drain(service, cutoff)
    latencies = [e.latency_ms for e in events]
    p95 = _percentile(latencies, 95.0)
    error_rate = _error_rate(events)
    uptime = _uptime_per_window(events)
    breached = uptime < target_uptime or p95 > DEFAULT_P95_LATENCY_MS or error_rate > DEFAULT_ERROR_RATE
    return ServiceSLA(
        service=service,
        window_days=window_days,
        uptime=round(uptime, 6),
        p95_latency_ms=round(p95, 2),
        error_rate=round(error_rate, 6),
        request_count=len(events),
        breached=breached,
        target_uptime=target_uptime,
        evaluated_at=datetime.now(timezone.utc).isoformat(),
    )


# ---------------------------------------------------------------------------
# Prometheus Pull (best-effort, no hard dependency)
# ---------------------------------------------------------------------------

def _fetch_prometheus_samples(
    service: str,
    *,
    prom_url: str | None = None,
    window_days: int = 30,
) -> list[SAMPLEvent] | None:
    """If ``PROMETHEUS_URL`` is set, request platform_http_requests_* and convert.

    Returns ``None`` if disabled or upstream error — caller falls back to local
    store.
    """
    base = prom_url or os.getenv(ENV_PROM_URL)
    if not base:
        return None
    end = int(time.time())
    start = end - window_days * 86400
    promql = (
        f'sum by (status_code, route) ('
        f'increase(platform_http_requests_total{{service="{service}"}}[{window_days}d]))'
    )
    qs = urllib.parse.urlencode({"query": promql, "start": start, "end": end, "step": "300"})
    url = f"{base.rstrip('/')}/api/v1/query_range?{qs}"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310 - controlled URL
            payload = json.loads(resp.read())
            results = payload.get("data", {}).get("result", [])
            if not results:
                return []
            # Synthesize coarse samples — Prometheus query_range values are
            # rollups, not per-request. We expose the rollup as 1 sample per
            # (route, status_code) bucket.
            out: list[SAMPLEvent] = []
            for bucket in results:
                metric = bucket.get("metric", {})
                route = metric.get("route", "unknown")
                status = int(metric.get("status_code", 200))
                for _ts, val in bucket.get("values", []):
                    count = float(val)
                    for _ in range(int(min(count, 1000))):
                        out.append(SAMPLEvent(
                            ts=float(_ts),
                            service=service,
                            endpoint=route,
                            tenant_id=None,
                            status_code=status,
                            latency_ms=0.0,
                            success=200 <= status < 500 and status != 429,
                            metadata={"source": "prometheus"},
                        ))
            return out
    except Exception as exc:  # pragma: no cover - network failures
        logger.warning("Prometheus pull failed for %s: %s", service, exc)
        return None


# ---------------------------------------------------------------------------
# Top-level compute_sla
# ---------------------------------------------------------------------------

def compute_sla(
    services: Iterable[str] = PLATFORM_SERVICES,
    windows: Iterable[int] = WINDOWS,
    target_uptime: float = DEFAULT_TARGET_UPTIME,
) -> SLAMetrics:
    """Compute :class:`SLAMetrics` over all windows for the given services.

    Pulls from Prometheus when configured, otherwise falls back to the in-memory
    :class:`_Store`. Breaches across services/windows are aggregated into
    ``overall_breaches`` as ``"<service>:<window>d"`` markers.
    """
    now = datetime.now(timezone.utc).isoformat()
    metrics = SLAMetrics(generated_at=now, windows_days=tuple(sorted(windows)))
    overall: list[str] = []
    for svc in services:
        metrics.services.setdefault(svc, {})
        for w in sorted(windows):
            prom_samples = _fetch_prometheus_samples(svc, window_days=w)
            if prom_samples is not None:
                merged_store = _Store()
                merged_store.add_many(prom_samples)
                # Always include the local store too — operational rollups may
                # span the merge boundary in tests.
                merged_store.add_many(get_store().drain(svc, 0))
                sla = compute_service_sla(svc, w, target_uptime, store=merged_store)
            else:
                sla = compute_service_sla(svc, w, target_uptime)
            metrics.services[svc][w] = sla
            if sla.breached:
                overall.append(f"{svc}:{w}d")
    metrics.overall_breaches = overall
    return metrics


# ---------------------------------------------------------------------------
# Breach evaluation + alerting
# ---------------------------------------------------------------------------

def _severity(sla: ServiceSLA) -> str:
    if sla.uptime < 0.95:
        return "P0"
    if sla.uptime < 0.99:
        return "P1"
    return "P2"


def evaluate_breach(
    sla: ServiceSLA,
    *,
    alert_sink: Callable[[SLABreachEvent], None] | None = None,
) -> SLABreachEvent | None:
    """Build + dispatch a :class:`SLABreachEvent` if service is outside SLO.

    ``alert_sink`` defaults to the platform alerting service (``services.observability.alerting``).
    Returns the event (or ``None`` when no breach).
    """
    if not sla.breached:
        return None
    evt = SLABreachEvent(
        service=sla.service,
        window_days=sla.window_days,
        uptime=sla.uptime,
        target_uptime=sla.target_uptime,
        p95_latency_ms=sla.p95_latency_ms,
        error_rate=sla.error_rate,
        severity=_severity(sla),
        summary=(
            f"{sla.service} SLA breach ({sla.window_days}d): "
            f"uptime={sla.uptime * 100:.3f}% < "
            f"{sla.target_uptime * 100:.1f}%, "
            f"p95={sla.p95_latency_ms:.0f}ms, err={sla.error_rate * 100:.2f}%"
        ),
        fired_at=datetime.now(timezone.utc).isoformat(),
    )
    if alert_sink is None:
        try:
            from services.observability.alerting import (  # type: ignore
                Alert, AlertingService, AlertSeverity, get_default_service,
            )
        except Exception:
            logger.warning("alerting service unavailable; logging breach: %s", evt.summary)
            return evt
        sev_map = {
            "P0": AlertSeverity.P0,
            "P1": AlertSeverity.P1,
            "P2": AlertSeverity.P2,
        }
        alert = Alert(
            name=f"SLA Breach {sla.service}",
            severity=sev_map.get(evt.severity, AlertSeverity.P2),
            summary=evt.summary,
            labels={"service": sla.service, "window": str(sla.window_days)},
            source="sla_monitor",
        )
        svc: AlertingService = get_default_service()
        try:
            if hasattr(svc, "fire_async"):
                asyncio_run(svc.fire_async(alert))
            else:
                svc.fire(alert)
        except Exception as exc:  # pragma: no cover - never raise
            logger.warning("alert dispatch failed: %s", exc)
        return evt
    try:
        alert_sink(evt)
    except Exception as exc:  # pragma: no cover
        logger.warning("alert_sink raised: %s", exc)
    return evt


# Tiny stdlib-only runner so we don't make asyncio a hard dep of this module
def asyncio_run(coro: Any) -> None:
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # caller is in an event loop — schedule and return immediately
            loop.create_task(coro)
            return
        loop.run_until_complete(coro)
    except RuntimeError:
        asyncio.run(coro)


# ---------------------------------------------------------------------------
# Monthly PDF report (uses ReportLab; falls back to plain text if unavailable)
# ---------------------------------------------------------------------------

def render_monthly_report(
    metrics: SLAMetrics,
    *,
    tenant_id: str | None = None,
    as_bytes: bool = True,
) -> bytes:
    """Generate the monthly SLA report as PDF (or text fallback)."""
    try:
        from reportlab.lib import colors  # type: ignore
        from reportlab.lib.pagesizes import letter  # type: ignore
        from reportlab.lib.styles import getSampleStyleSheet  # type: ignore
        from reportlab.platypus import (  # type: ignore
            Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
        )
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=letter, title="waibao SLA Report")
        styles = getSampleStyleSheet()
        story = [
            Paragraph("waibao — Monthly SLA Report", styles["Title"]),
            Paragraph(
                f"Generated at {metrics.generated_at} (UTC). "
                f"Tenant: {tenant_id or 'all'}.",
                styles["Normal"],
            ),
            Spacer(1, 12),
        ]
        for svc, by_window in metrics.services.items():
            story.append(Paragraph(f"<b>{svc}</b>", styles["Heading2"]))
            rows = [["Window (d)", "Uptime %", "P95 (ms)", "Err %", "Reqs", "Status"]]
            for w, sla in sorted(by_window.items()):
                rows.append([
                    str(w),
                    f"{sla.uptime * 100:.4f}",
                    f"{sla.p95_latency_ms:.1f}",
                    f"{sla.error_rate * 100:.3f}",
                    str(sla.request_count),
                    "BREACH" if sla.breached else "OK",
                ])
            table = Table(rows, hAlign="LEFT")
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ]))
            story.append(table)
            story.append(Spacer(1, 12))
        story.append(Paragraph(
            f"Target uptime {DEFAULT_TARGET_UPTIME * 100:.1f}%. "
            f"Overall breaches: {', '.join(metrics.overall_breaches) or 'none'}.",
            styles["Italic"],
        ))
        doc.build(story)
        return buf.getvalue()
    except ImportError:
        # Fallback: text file (still useful in CI / minimal installs)
        lines = [f"waibao SLA Report — {metrics.generated_at}",
                 f"Tenant: {tenant_id or 'all'}", ""]
        for svc, by_window in metrics.services.items():
            lines.append(f"== {svc} ==")
            for w, sla in sorted(by_window.items()):
                lines.append(
                    f"  {w:>3}d  uptime={sla.uptime * 100:.4f}%  "
                    f"p95={sla.p95_latency_ms:.1f}ms  err={sla.error_rate * 100:.3f}%  "
                    f"reqs={sla.request_count}  "
                    f"{'BREACH' if sla.breached else 'OK'}"
                )
            lines.append("")
        text = "\n".join(lines)
        return text.encode("utf-8") if as_bytes else text


# ---------------------------------------------------------------------------
# FastAPI integration shim (used by api/sla.py)
# ---------------------------------------------------------------------------

def summary_for_admin(
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """Slim admin summary used by ``GET /api/admin/sla/...``."""
    metrics = compute_sla()
    return {
        "tenant_id": tenant_id,
        "generated_at": metrics.generated_at,
        "target_uptime": DEFAULT_TARGET_UPTIME,
        "windows": list(metrics.windows_days),
        "services": {
            svc: {str(w): s.to_dict() for w, s in by_window.items()}
            for svc, by_window in metrics.services.items()
        },
        "breaches": metrics.overall_breaches,
    }


# ---------------------------------------------------------------------------
# Status page (Instatus) sync helper
# ---------------------------------------------------------------------------

def to_status_page_payload(metrics: SLAMetrics) -> dict[str, Any]:
    """Shape the data so the public status page can render it directly."""
    indicators: list[dict[str, Any]] = []
    history: list[dict[str, Any]] = []
    for svc, by_window in metrics.services.items():
        rollup = by_window.get(30) or by_window.get(7)
        if rollup is None:
            continue
        indicators.append({
            "id": svc,
            "name": svc.upper(),
            "status": "operational" if not rollup.breached else "degraded",
            "uptime_90d_pct": round(by_window.get(90, rollup).uptime * 100, 4),
        })
    if 90 in metrics.windows_days:
        # The 90d window already covers the public view
        for svc, by_window in metrics.services.items():
            s90 = by_window.get(90)
            if s90:
                history.append({"service": svc, "uptime_pct": s90.uptime * 100})
    return {
        "page": {"name": "waibao", "url": "https://status.waibao.cn"},
        "indicators": indicators,
        "history_90d": history,
        "updated_at": metrics.generated_at,
    }


__all__ = [
    "PLATFORM_SERVICES",
    "DEFAULT_TARGET_UPTIME",
    "DEFAULT_P95_LATENCY_MS",
    "DEFAULT_ERROR_RATE",
    "WINDOWS",
    "SAMPLEvent",
    "ServiceSLA",
    "SLAMetrics",
    "SLABreachEvent",
    "record_event",
    "compute_service_sla",
    "compute_sla",
    "evaluate_breach",
    "render_monthly_report",
    "summary_for_admin",
    "to_status_page_payload",
    "get_store",
]
