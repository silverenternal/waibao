"""v8.0 T3901 — 异常检测与用户行为分析服务.

Responsibilities:
    * 实时异常检测:
        - 匹配率突降 (> 20%)
        - 用户活跃度突降
        - 工单积压 (> 50)
        - 错误率突增
    * 自动告警: 复用 v6.0 通知通道 (smtp / 钉钉 / 飞书 / im / webhook)
    * 用户行为分析:
        - 哪些功能用得多 (>= MIN_USAGE 阈值)
        - 哪些被忽略 (> 7 天没人用)
    * 提示给 PM (返回 analysis report)

设计要点:
    * 纯 Python 计算, 不强依赖数据库 (mock fallback)
    * 阈值可通过环境变量 / 注入覆盖
    * AnomalyResult 对象可序列化给 admin/insights 前端展示
"""
from __future__ import annotations

import logging
import math
import os
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger("recruittech.platform.anomaly_detector")


# ---------------------------------------------------------------------------
# 阈值 (可注入 / 环境变量覆盖)
# ---------------------------------------------------------------------------


DEFAULT_THRESHOLDS: Dict[str, float] = {
    "match_rate_drop_pct": 20.0,   # 匹配率突降 %
    "active_user_drop_pct": 15.0,  # 日活突降 %
    "ticket_backlog_count": 50,    # 工单积压
    "error_rate_spike_pct": 5.0,   # 错误率突增 (绝对百分点)
    "feature_abandoned_days": 7,   # >7 天无调用视为被忽略
    "feature_min_usage": 5,        # 一周内 < 5 次调用视为低使用
    "z_score_threshold": 2.0,      # 标准差阈值 (用于突降检测)
}


# ---------------------------------------------------------------------------
# 枚举 / 数据结构
# ---------------------------------------------------------------------------


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AnomalyType(str, Enum):
    MATCH_RATE_DROP = "match_rate_drop"
    ACTIVE_USER_DROP = "active_user_drop"
    TICKET_BACKLOG = "ticket_backlog"
    ERROR_RATE_SPIKE = "error_rate_spike"
    FEATURE_ABANDONED = "feature_abandoned"


@dataclass
class AnomalyResult:
    type: str
    severity: str
    metric: str
    current: float
    baseline: float
    delta_pct: float
    message: str
    detected_at: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "severity": self.severity,
            "metric": self.metric,
            "current": self.current,
            "baseline": self.baseline,
            "delta_pct": self.delta_pct,
            "message": self.message,
            "detected_at": self.detected_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AnomalyResult":
        return cls(
            type=d["type"],
            severity=d["severity"],
            metric=d["metric"],
            current=float(d.get("current", 0)),
            baseline=float(d.get("baseline", 0)),
            delta_pct=float(d.get("delta_pct", 0)),
            message=str(d.get("message", "")),
            detected_at=str(d.get("detected_at", "")),
            metadata=dict(d.get("metadata", {})),
        )


@dataclass
class FeatureUsageRow:
    feature: str
    invocations: int
    unique_users: int
    last_used_at: Optional[str] = None  # ISO8601

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "FeatureUsageRow":
        return cls(
            feature=str(d["feature"]),
            invocations=int(d.get("invocations", 0)),
            unique_users=int(d.get("unique_users", 0)),
            last_used_at=d.get("last_used_at"),
        )


@dataclass
class BehaviorInsight:
    category: str  # "popular" | "abandoned" | "low_usage"
    feature: str
    invocations: int
    unique_users: int
    last_used_at: Optional[str] = None
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "feature": self.feature,
            "invocations": self.invocations,
            "unique_users": self.unique_users,
            "last_used_at": self.last_used_at,
            "note": self.note,
        }


# ---------------------------------------------------------------------------
# 工具方法
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def _percent_change(current: float, baseline: float) -> float:
    if baseline == 0:
        return 0.0 if current == 0 else 100.0
    return (current - baseline) / abs(baseline) * 100.0


def _severity_for_anomaly(anomaly_type: str, delta_pct: float) -> Severity:
    abs_delta = abs(delta_pct)
    if anomaly_type == AnomalyType.TICKET_BACKLOG.value:
        return Severity.CRITICAL
    if anomaly_type == AnomalyType.MATCH_RATE_DROP.value:
        if abs_delta >= 40:
            return Severity.CRITICAL
        if abs_delta >= 25:
            return Severity.WARNING
        return Severity.INFO
    if anomaly_type == AnomalyType.ERROR_RATE_SPIKE.value:
        if abs_delta >= 15:
            return Severity.CRITICAL
        if abs_delta >= 8:
            return Severity.WARNING
        return Severity.INFO
    if anomaly_type == AnomalyType.ACTIVE_USER_DROP.value:
        if abs_delta >= 30:
            return Severity.CRITICAL
        if abs_delta >= 20:
            return Severity.WARNING
        return Severity.INFO
    if anomaly_type == AnomalyType.FEATURE_ABANDONED.value:
        return Severity.WARNING
    return Severity.INFO


# ---------------------------------------------------------------------------
# 默认数据源
# ---------------------------------------------------------------------------


def _default_supabase_factory():
    try:
        from api.deps import get_supabase_admin

        return get_supabase_admin()
    except Exception:  # pragma: no cover
        return None


def _default_dispatcher_factory():
    try:
        from services.notify import get_dispatcher

        return get_dispatcher()
    except Exception:  # pragma: no cover
        return None


def _default_clock() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# AnomalyDetector
# ---------------------------------------------------------------------------


class AnomalyDetector:
    """异常检测器.

    既支持实时指标 (传入 current vs baseline) 检测,
    也支持 ``detect_from_metrics`` 一站式从数据源拉数据.
    """

    def __init__(
        self,
        *,
        thresholds: Optional[Dict[str, float]] = None,
        clock: Callable[[], datetime] = _default_clock,
        supabase_factory: Callable[[], Any] = _default_supabase_factory,
        dispatcher_factory: Callable[[], Any] = _default_dispatcher_factory,
    ) -> None:
        self._thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
        self._clock = clock
        self._supabase_factory = supabase_factory
        self._dispatcher_factory = dispatcher_factory
        # 解析环境变量覆盖
        for key in self._thresholds:
            env_key = f"ANOMALY_{key.upper()}"
            env_val = os.environ.get(env_key)
            if env_val:
                try:
                    self._thresholds[key] = float(env_val)
                except ValueError:
                    pass

    # ---- 访问器 ----
    @property
    def thresholds(self) -> Dict[str, float]:
        return dict(self._thresholds)

    def update_threshold(self, key: str, value: float) -> None:
        if key not in DEFAULT_THRESHOLDS:
            raise KeyError(f"unknown threshold: {key}")
        self._thresholds[key] = float(value)

    # ---- 基础检测器 ----
    def detect_match_rate_drop(
        self, current: float, baseline: float
    ) -> Optional[AnomalyResult]:
        delta_pct = baseline - current  # 正值代表下降
        if delta_pct < self._thresholds["match_rate_drop_pct"]:
            return None
        return AnomalyResult(
            type=AnomalyType.MATCH_RATE_DROP.value,
            severity=_severity_for_anomaly(AnomalyType.MATCH_RATE_DROP.value, delta_pct).value,
            metric="match_rate",
            current=current,
            baseline=baseline,
            delta_pct=delta_pct,
            message=f"匹配率从 {baseline:.1f}% 降至 {current:.1f}% (下降 {delta_pct:.1f} 个百分点)",
            detected_at=self._clock().isoformat(),
        )

    def detect_active_user_drop(
        self, current: int, baseline: int
    ) -> Optional[AnomalyResult]:
        if baseline <= 0:
            return None
        delta_pct = _percent_change(current, baseline)
        if delta_pct > -self._thresholds["active_user_drop_pct"]:
            return None
        return AnomalyResult(
            type=AnomalyType.ACTIVE_USER_DROP.value,
            severity=_severity_for_anomaly(AnomalyType.ACTIVE_USER_DROP.value, delta_pct).value,
            metric="dau",
            current=float(current),
            baseline=float(baseline),
            delta_pct=delta_pct,
            message=f"日活从 {baseline} 降至 {current} (下降 {abs(delta_pct):.1f}%)",
            detected_at=self._clock().isoformat(),
        )

    def detect_ticket_backlog(
        self, open_tickets: int, threshold: Optional[int] = None
    ) -> Optional[AnomalyResult]:
        limit = threshold if threshold is not None else int(self._thresholds["ticket_backlog_count"])
        if open_tickets < limit:
            return None
        delta_pct = _percent_change(open_tickets, limit)
        return AnomalyResult(
            type=AnomalyType.TICKET_BACKLOG.value,
            severity=_severity_for_anomaly(AnomalyType.TICKET_BACKLOG.value, delta_pct).value,
            metric="open_tickets",
            current=float(open_tickets),
            baseline=float(limit),
            delta_pct=delta_pct,
            message=f"工单积压 {open_tickets} 单 (阈值 {limit})",
            detected_at=self._clock().isoformat(),
        )

    def detect_error_rate_spike(
        self, current: float, baseline: float
    ) -> Optional[AnomalyResult]:
        delta = current - baseline  # 百分点差
        if delta < self._thresholds["error_rate_spike_pct"]:
            return None
        return AnomalyResult(
            type=AnomalyType.ERROR_RATE_SPIKE.value,
            severity=_severity_for_anomaly(AnomalyType.ERROR_RATE_SPIKE.value, delta).value,
            metric="error_rate",
            current=current,
            baseline=baseline,
            delta_pct=_percent_change(current, max(baseline, 0.001)),
            message=f"错误率从 {baseline:.2f}% 上升至 {current:.2f}% (+{delta:.2f}pp)",
            detected_at=self._clock().isoformat(),
        )

    def detect_feature_abandoned(
        self, features: Sequence[FeatureUsageRow]
    ) -> List[AnomalyResult]:
        """7 天以上无调用的功能视为被忽略."""
        threshold_days = float(self._thresholds["feature_abandoned_days"])
        now = self._clock()
        results: List[AnomalyResult] = []
        for f in features:
            ts = _parse_iso(f.last_used_at)
            if ts is None:
                continue
            age = (now - ts).total_seconds() / 86400.0
            if age >= threshold_days:
                delta_pct = -100.0
                results.append(
                    AnomalyResult(
                        type=AnomalyType.FEATURE_ABANDONED.value,
                        severity=_severity_for_anomaly(AnomalyType.FEATURE_ABANDONED.value, delta_pct).value,
                        metric=f"feature:{f.feature}",
                        current=0.0,
                        baseline=float(f.invocations),
                        delta_pct=delta_pct,
                        message=f"功能 {f.feature} 已 {age:.0f} 天无调用 (上次 {f.last_used_at})",
                        detected_at=now.isoformat(),
                        metadata={
                            "feature": f.feature,
                            "age_days": round(age, 1),
                            "last_used_at": f.last_used_at,
                        },
                    )
                )
        return results

    # ---- 行为分析 ----
    def analyze_feature_usage(
        self, features: Sequence[FeatureUsageRow]
    ) -> List[BehaviorInsight]:
        """popular / low_usage / abandoned."""
        insights: List[BehaviorInsight] = []
        min_usage = int(self._thresholds["feature_min_usage"])
        abandoned_days = float(self._thresholds["feature_abandoned_days"])
        now = self._clock()
        if not features:
            return insights
        sorted_by_usage = sorted(features, key=lambda f: f.invocations, reverse=True)
        top_n = max(1, len(sorted_by_usage) // 5)
        popular = sorted_by_usage[:top_n]
        low = [f for f in sorted_by_usage if f.invocations < min_usage]
        for f in popular:
            insights.append(
                BehaviorInsight(
                    category="popular",
                    feature=f.feature,
                    invocations=f.invocations,
                    unique_users=f.unique_users,
                    last_used_at=f.last_used_at,
                    note="高使用率, 建议保留并优化",
                )
            )
        for f in low:
            insights.append(
                BehaviorInsight(
                    category="low_usage",
                    feature=f.feature,
                    invocations=f.invocations,
                    unique_users=f.unique_users,
                    last_used_at=f.last_used_at,
                    note=f"使用率低 (< {min_usage} 次/周), 建议 PM 评估",
                )
            )
        for f in features:
            ts = _parse_iso(f.last_used_at)
            if ts is None:
                continue
            age = (now - ts).total_seconds() / 86400.0
            if age >= abandoned_days:
                insights.append(
                    BehaviorInsight(
                        category="abandoned",
                        feature=f.feature,
                        invocations=f.invocations,
                        unique_users=f.unique_users,
                        last_used_at=f.last_used_at,
                        note=f"已 {age:.0f} 天无调用, 建议下架或重设计",
                    )
                )
        return insights

    # ---- 端到端 ----
    def detect_from_metrics(
        self,
        *,
        match_rate_current: float,
        match_rate_baseline: float,
        dau_current: int,
        dau_baseline: int,
        open_tickets: int,
        error_rate_current: float,
        error_rate_baseline: float,
        features: Optional[Sequence[FeatureUsageRow]] = None,
    ) -> List[AnomalyResult]:
        out: List[AnomalyResult] = []
        a1 = self.detect_match_rate_drop(match_rate_current, match_rate_baseline)
        if a1:
            out.append(a1)
        a2 = self.detect_active_user_drop(dau_current, dau_baseline)
        if a2:
            out.append(a2)
        a3 = self.detect_ticket_backlog(open_tickets)
        if a3:
            out.append(a3)
        a4 = self.detect_error_rate_spike(error_rate_current, error_rate_baseline)
        if a4:
            out.append(a4)
        if features:
            out.extend(self.detect_feature_abandoned(features))
        return out

    # ---- z-score 辅助 (用于趋势类) ----
    def z_score_anomaly(
        self, current: float, history: Sequence[float]
    ) -> Optional[AnomalyResult]:
        if len(history) < 3:
            return None
        mu = statistics.fmean(history)
        sd = statistics.pstdev(history)
        if sd == 0:
            return None
        z = (current - mu) / sd
        if abs(z) < float(self._thresholds["z_score_threshold"]):
            return None
        delta_pct = _percent_change(current, mu)
        return AnomalyResult(
            type="z_score_anomaly",
            severity=Severity.WARNING.value if abs(z) < 3 else Severity.CRITICAL.value,
            metric="zscore",
            current=current,
            baseline=mu,
            delta_pct=delta_pct,
            message=f"z={z:.2f} (阈值 {self._thresholds['z_score_threshold']}); mean={mu:.2f} sd={sd:.2f}",
            detected_at=self._clock().isoformat(),
            metadata={"z": z, "history_len": len(history)},
        )

    # ---- 告警 ----
    async def alert(
        self,
        anomalies: Sequence[AnomalyResult],
        *,
        channels: Optional[Iterable[str]] = None,
        recipients: Optional[Iterable[str]] = None,
    ) -> Dict[str, Any]:
        if not anomalies:
            return {"delivered": False, "channels": [], "count": 0}
        dispatcher = self._dispatcher_factory()
        if dispatcher is None:
            logger.info("anomaly_detector: dispatcher unavailable")
            return {"delivered": False, "channels": [], "count": len(anomalies), "skipped": "no_dispatcher"}
        # 构造消息
        critical = [a for a in anomalies if a.severity == Severity.CRITICAL.value]
        warning = [a for a in anomalies if a.severity == Severity.WARNING.value]
        lines = [f"招聘智能体 异常告警 ({len(anomalies)} 条)"]
        if critical:
            lines.append(f"  CRITICAL ({len(critical)}):")
            for a in critical:
                lines.append(f"    - {a.message}")
        if warning:
            lines.append(f"  WARNING ({len(warning)}):")
            for a in warning:
                lines.append(f"    - {a.message}")
        content = "\n".join(lines)
        targets = list(recipients or ["oncall@waibao.example"])
        ch_list = list(channels or ["smtp", "dingtalk", "feishu", "im"])
        delivered: List[str] = []
        for user_id in targets:
            outcome = await dispatcher.dispatch_multi(
                channels=ch_list,
                user_id=user_id,
                title=f"[异常告警] {len(critical)} critical / {len(warning)} warning",
                content=content,
                payload={
                    "anomalies": [a.to_dict() for a in anomalies],
                    "channels": ch_list,
                },
            )
            for r in outcome.results:
                if r.success and r.channel in ch_list:
                    delivered.append(r.channel)
        return {
            "delivered": bool(delivered),
            "channels": list(set(delivered)),
            "count": len(anomalies),
        }

    async def run_cycle(
        self,
        metrics: Optional[Dict[str, Any]] = None,
        *,
        alert_on_warning: bool = True,
    ) -> Dict[str, Any]:
        """单次运行: 拉取 / 计算 / 告警."""
        if metrics is None:
            metrics = self._collect_metrics()
        match_rate_current = float(metrics.get("match_rate_current", 82.0))
        match_rate_baseline = float(metrics.get("match_rate_baseline", 86.0))
        dau_current = int(metrics.get("dau_current", 280))
        dau_baseline = int(metrics.get("dau_baseline", 312))
        open_tickets = int(metrics.get("open_tickets", 18))
        error_rate_current = float(metrics.get("error_rate_current", 1.2))
        error_rate_baseline = float(metrics.get("error_rate_baseline", 0.6))
        features = [
            FeatureUsageRow.from_dict(f)
            for f in metrics.get("features", [])
        ]
        anomalies = self.detect_from_metrics(
            match_rate_current=match_rate_current,
            match_rate_baseline=match_rate_baseline,
            dau_current=dau_current,
            dau_baseline=dau_baseline,
            open_tickets=open_tickets,
            error_rate_current=error_rate_current,
            error_rate_baseline=error_rate_baseline,
            features=features,
        )
        alert_result: Dict[str, Any] = {"delivered": False, "channels": [], "count": len(anomalies)}
        if anomalies and (alert_on_warning or any(a.severity == Severity.CRITICAL.value for a in anomalies)):
            alert_result = await self.alert(anomalies)
        insights = self.analyze_feature_usage(features)
        return {
            "anomalies": [a.to_dict() for a in anomalies],
            "behavior_insights": [i.to_dict() for i in insights],
            "alert": alert_result,
            "metrics_used": {
                "match_rate_current": match_rate_current,
                "match_rate_baseline": match_rate_baseline,
                "dau_current": dau_current,
                "dau_baseline": dau_baseline,
                "open_tickets": open_tickets,
                "error_rate_current": error_rate_current,
                "error_rate_baseline": error_rate_baseline,
                "features_count": len(features),
            },
        }

    def _collect_metrics(self) -> Dict[str, Any]:
        """从 supabase 拉取; 失败使用 mock."""
        supabase = self._supabase_factory()
        if supabase is None:
            return self._mock_metrics()
        out: Dict[str, Any] = {}
        try:
            r1 = (
                supabase.table("metrics_match_rate")
                .select("current,baseline")
                .order("ts", desc=True)
                .limit(1)
                .execute()
            )
            if r1.data:
                out["match_rate_current"] = r1.data[0].get("current", 82.0)
                out["match_rate_baseline"] = r1.data[0].get("baseline", 86.0)
        except Exception:
            pass
        try:
            r2 = (
                supabase.table("dau_daily")
                .select("dau,date")
                .order("date", desc=True)
                .limit(8)
                .execute()
            )
            rows = r2.data or []
            if rows:
                out["dau_current"] = rows[0].get("dau", 280)
                baseline_avg = sum((r.get("dau") or 0) for r in rows[1:]) / max(len(rows) - 1, 1)
                out["dau_baseline"] = baseline_avg
        except Exception:
            pass
        try:
            r3 = (
                supabase.table("tickets")
                .select("id", count="exact")
                .in_("status", ["open", "pending"])
                .execute()
            )
            out["open_tickets"] = getattr(r3, "count", None) or 18
        except Exception:
            pass
        try:
            r4 = (
                supabase.table("error_rate_window")
                .select("current,baseline")
                .order("ts", desc=True)
                .limit(1)
                .execute()
            )
            if r4.data:
                out["error_rate_current"] = r4.data[0].get("current", 1.2)
                out["error_rate_baseline"] = r4.data[0].get("baseline", 0.6)
        except Exception:
            pass
        try:
            r5 = (
                supabase.table("feature_usage_weekly")
                .select("feature,invocations,unique_users,last_used_at")
                .order("invocations", desc=True)
                .limit(20)
                .execute()
            )
            out["features"] = r5.data or []
        except Exception:
            pass
        return out or self._mock_metrics()

    def _mock_metrics(self) -> Dict[str, Any]:
        now = self._clock()
        return {
            "match_rate_current": 82.0,
            "match_rate_baseline": 86.0,
            "dau_current": 280,
            "dau_baseline": 312,
            "open_tickets": 18,
            "error_rate_current": 1.2,
            "error_rate_baseline": 0.6,
            "features": [
                {"feature": "matching", "invocations": 1842, "unique_users": 412,
                 "last_used_at": (now - timedelta(hours=1)).isoformat()},
                {"feature": "profile_card", "invocations": 1311, "unique_users": 287,
                 "last_used_at": (now - timedelta(hours=2)).isoformat()},
                {"feature": "ai_interview", "invocations": 974, "unique_users": 218,
                 "last_used_at": (now - timedelta(hours=3)).isoformat()},
                {"feature": "jd_generate", "invocations": 712, "unique_users": 165,
                 "last_used_at": (now - timedelta(hours=4)).isoformat()},
                {"feature": "salary_benchmark", "invocations": 134, "unique_users": 33,
                 "last_used_at": (now - timedelta(days=10)).isoformat()},
                {"feature": "company_review", "invocations": 96, "unique_users": 21,
                 "last_used_at": (now - timedelta(days=12)).isoformat()},
            ],
        }


# ---------------------------------------------------------------------------
# 单例
# ---------------------------------------------------------------------------


_detector: Optional[AnomalyDetector] = None


def get_anomaly_detector() -> AnomalyDetector:
    global _detector
    if _detector is None:
        _detector = AnomalyDetector()
    return _detector


def reset_anomaly_detector() -> None:
    global _detector
    _detector = None
