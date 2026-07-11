"""A/B 实验框架 — T805.

提供稳定的哈希分桶、流量分配、指标记录、显著性检验。
"""
from __future__ import annotations

import hashlib
import logging
import math
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

logger = logging.getLogger("recruittech.services.ab_test")

# 内置指标清单 — 业务可扩展 (覆盖匹配、转化、风控、UX).
BUILTIN_METRICS: list[str] = [
    "match.score",          # 匹配总分 (0~1)
    "match.ctr",            # 候选人匹配点击率
    "match.accept_rate",    # 接受率 (handoff)
    "hatch.time_to_match",  # 从 query 到首个 match 的耗时 (秒)
    "quote.conversion",     # quote -> placement 转化
    "policy.compliance",    # 合规分 (0~100)
    "ux.csat",              # 客户满意度 (NPS / 5星)
    "latency.p95",          # P95 接口延迟 (秒)
]

# 哈希 salt 可配置 (AB_HASH_SALT).
_HASH_SALT: str = os.getenv("AB_HASH_SALT", "recruittech-ab-default-salt")


def get_hash_salt() -> str:
    """返回当前生效的哈希 salt (可被测试设置)."""
    return _HASH_SALT


def set_hash_salt(value: str) -> None:
    """运行时覆盖 salt (测试 / 多租户隔离)."""
    global _HASH_SALT
    _HASH_SALT = value


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------
@dataclass
class Variant:
    name: str
    weight: int  # 相对权重, 内部归一化为 0~99 区间
    config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Experiment:
    id: str
    name: str
    description: str
    variants: list[Variant]
    status: str  # "draft" | "running" | "stopped" | "completed"
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    primary_metric: str = "match.score"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["started_at"] = self.started_at.isoformat() if self.started_at else None
        d["ended_at"] = self.ended_at.isoformat() if self.ended_at else None
        d["created_at"] = self.created_at.isoformat()
        d["updated_at"] = self.updated_at.isoformat()
        d["variants"] = [v.to_dict() for v in self.variants]
        return d


# ---------------------------------------------------------------------------
# Stable hash bucketing
# ---------------------------------------------------------------------------
def hash_bucket(user_id: str | int, salt: Optional[str] = None, buckets: int = 100) -> int:
    """把 (user_id, salt) 映射到 0~(buckets-1) 整数,稳定且分布均匀.

    使用 SHA-256 + 取模;同 salt 同 user 永远落同一桶,换 salt 可重新分组。
    """
    if buckets <= 0:
        raise ValueError("buckets must be > 0")
    s = salt if salt is not None else get_hash_salt()
    payload = f"{s}|{user_id}".encode("utf-8")
    digest = hashlib.sha256(payload).digest()
    # 取前 8 字节转成整数再 mod.
    n = int.from_bytes(digest[:8], byteorder="big", signed=False)
    return n % buckets


# ---------------------------------------------------------------------------
# Variant assignment
# ---------------------------------------------------------------------------
def _normalized_weights(variants: list[Variant]) -> list[tuple[str, int]]:
    """把权重归一化到 0~99 的桶区间,按累计分桶确定隶属."""
    if not variants:
        raise ValueError("variants must not be empty")
    if any(v.weight < 0 for v in variants):
        raise ValueError("variant weights must be non-negative")
    total = sum(v.weight for v in variants)
    if total <= 0:
        raise ValueError("sum of variant weights must be > 0")
    out: list[tuple[str, int]] = []
    cum = 0
    for v in variants:
        cum += v.weight
        upper = int(math.floor(cum * 100 / total))
        out.append((v.name, max(upper, 0)))
    # 保证最后一桶覆盖 99.
    if out:
        out[-1] = (out[-1][0], 99)
        # 强制单调递增(避免浮点误差).
        fixed: list[tuple[str, int]] = []
        prev = -1
        for name, hi in out:
            hi = max(hi, prev + 1)
            fixed.append((name, hi))
            prev = hi
        out = fixed
    return out


def assign_variant(
    experiment: Experiment | dict[str, Any],
    user_id: str | int,
    salt: Optional[str] = None,
) -> str:
    """根据 user_id 哈希分桶,落入某 variant;返回 variant name."""
    if isinstance(experiment, dict):
        variants_raw = experiment.get("variants", [])
        variants = [Variant(**v) if not isinstance(v, Variant) else v for v in variants_raw]
        status = experiment.get("status", "running")
        experiment_name = experiment.get("name", "")
    else:
        variants = experiment.variants
        status = experiment.status
        experiment_name = experiment.name

    if status not in ("running", "draft"):
        # 停止的实验返回首个 variant 作为保底,避免 None.
        return variants[0].name if variants else experiment_name

    bucket = hash_bucket(
        f"{experiment_name}|{user_id}" if experiment_name else user_id,
        salt=salt,
        buckets=100,
    )
    bands = _normalized_weights(variants)
    for name, hi in bands:
        if bucket <= hi:
            return name
    return bands[-1][0]


# ---------------------------------------------------------------------------
# Metric recording (in-process;可被 SupabaseRepository 替换).
# ---------------------------------------------------------------------------
@dataclass
class MetricSample:
    experiment_id: str
    variant: str
    metric_name: str
    value: float
    recorded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class MetricStore:
    """线程安全的指标缓冲;生产可替换为 Supabase / 时序库。"""

    def __init__(self) -> None:
        self._samples: list[MetricSample] = []
        self._lock = threading.Lock()

    def record(self, sample: MetricSample) -> None:
        with self._lock:
            self._samples.append(sample)

    def list(
        self,
        experiment_id: Optional[str] = None,
        variant: Optional[str] = None,
        metric_name: Optional[str] = None,
    ) -> list[MetricSample]:
        with self._lock:
            out = list(self._samples)
        if experiment_id:
            out = [s for s in out if s.experiment_id == experiment_id]
        if variant:
            out = [s for s in out if s.variant == variant]
        if metric_name:
            out = [s for s in out if s.metric_name == metric_name]
        return out

    def clear(self) -> None:
        with self._lock:
            self._samples.clear()


_METRIC_STORE = MetricStore()


def get_metric_store() -> MetricStore:
    return _METRIC_STORE


def record_metric(
    experiment_id: str,
    variant: str,
    metric_name: str,
    value: float,
    store: Optional[MetricStore] = None,
) -> None:
    """记录一条指标样本;写失败只记日志,不影响业务调用方。"""
    try:
        s = store or get_metric_store()
        s.record(
            MetricSample(
                experiment_id=experiment_id,
                variant=variant,
                metric_name=metric_name,
                value=float(value),
            )
        )
    except Exception:  # noqa: BLE001 - 性能关键路径
        logger.exception(
            "ab_test.record_metric_failed experiment=%s metric=%s",
            experiment_id,
            metric_name,
        )


# ---------------------------------------------------------------------------
# Significance testing (Welch's t-test approximation;两 variant 对比).
# ---------------------------------------------------------------------------
def _norm_sf(z: float) -> float:
    """标准正态 SF(z) = 1 - Phi(z). 不依赖 scipy,精度足够 4 位小数用于 dashboard.

    z 很大时直接返回 0.0 避免下溢.
    """
    # 极端值短路
    if z > 8.0:
        return 0.0
    if z < -8.0:
        return 1.0
    # 利用对称: SF(z) + SF(-z) = 1, 只计算非负 z 再镜像.
    # complement of CDF via erfc: SF(z) = 0.5 * erfc(z / sqrt(2))
    # 用 Abramowitz & Stegun 7.1.26 的 erfc 近似,对大 z 仍然稳定.
    x = z / math.sqrt(2.0)
    abs_x = abs(x)
    a1 = 0.254829592
    a2 = -0.284496736
    a3 = 1.421413741
    a4 = -1.453152027
    a5 = 1.061405429
    p_coef = 0.3275911
    t = 1.0 / (1.0 + p_coef * abs_x)
    erfc_abs = (
        (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * math.exp(-abs_x * abs_x)
    )
    # erfc(x) for x>=0 是 erfc_abs; erfc(-x) = 2 - erfc(x).
    if x >= 0:
        erfc = erfc_abs
    else:
        erfc = 2.0 - erfc_abs
    sf = 0.5 * erfc
    return max(min(sf, 1.0), 0.0)


def _welch_t_pvalue(mean_a: float, var_a: float, n_a: int, mean_b: float, var_b: float, n_b: int) -> float:
    """Welch's t-test 双侧 p-value (正态近似, n>=10 适用;小样本也合理)."""
    if n_a < 2 or n_b < 2:
        return 1.0
    se2 = (var_a / n_a) + (var_b / n_b)
    if se2 <= 0:
        return 1.0
    t_abs = abs(mean_b - mean_a) / math.sqrt(se2)
    if t_abs == 0.0:
        return 1.0
    # 双侧 p = 2 * SF(|t|)
    two_sided = 2.0 * _norm_sf(t_abs)
    return max(0.0, min(two_sided, 1.0))


def _summarize(values: Iterable[float]) -> tuple[float, float, int]:
    arr = [v for v in values if v is not None]
    n = len(arr)
    if n == 0:
        return 0.0, 0.0, 0
    mean = sum(arr) / n
    if n < 2:
        return mean, 0.0, n
    var = sum((x - mean) ** 2 for x in arr) / (n - 1)
    return mean, var, n


def compute_significance(
    experiment_id: str,
    metric_name: str,
    baseline_variant: Optional[str] = None,
    store: Optional[MetricStore] = None,
    confidence_target: float = 0.95,
) -> dict[str, Any]:
    """对某实验的某指标做 Welch's t-test,返回 lift / p-value / confidence 字典.

    baseline_variant: 默认为 variants 中按字典序第一个 (与 UI 保持一致).
    返回结构:
        {
            experiment_id, metric_name, baseline,
            variants: [{name, mean, stddev, n, lift_vs_baseline, p_value}],
            confidence: float (1-p_value 取较大 variant),
            significant: bool (confidence >= confidence_target),
        }
    """
    s = store or get_metric_store()
    samples = s.list(experiment_id=experiment_id, metric_name=metric_name)
    if not samples:
        return {
            "experiment_id": experiment_id,
            "metric_name": metric_name,
            "baseline": baseline_variant,
            "variants": [],
            "confidence": 0.0,
            "significant": False,
            "n_total": 0,
        }
    # 按 variant 聚合
    by_variant: dict[str, list[float]] = {}
    for sample in samples:
        by_variant.setdefault(sample.variant, []).append(sample.value)
    if baseline_variant is None:
        baseline_variant = sorted(by_variant.keys())[0]
    if baseline_variant not in by_variant:
        baseline_variant = sorted(by_variant.keys())[0]

    base_mean, base_var, base_n = _summarize(by_variant[baseline_variant])

    results: list[dict[str, Any]] = []
    best_p = 1.0
    n_total = sum(len(v) for v in by_variant.values())
    for variant, values in sorted(by_variant.items()):
        mean, var, n = _summarize(values)
        if variant == baseline_variant:
            lift = 0.0
            p_value = 1.0
        else:
            lift = (mean - base_mean) / base_mean if base_mean else 0.0
            p_value = _welch_t_pvalue(base_mean, base_var, base_n, mean, var, n)
        stddev = math.sqrt(var) if var > 0 else 0.0
        results.append(
            {
                "name": variant,
                "mean": mean,
                "stddev": stddev,
                "n": n,
                "lift_vs_baseline": lift,
                "p_value": p_value,
                "is_baseline": variant == baseline_variant,
            }
        )
        if variant != baseline_variant and p_value < best_p:
            best_p = p_value

    confidence = max(0.0, 1.0 - best_p)
    return {
        "experiment_id": experiment_id,
        "metric_name": metric_name,
        "baseline": baseline_variant,
        "variants": results,
        "confidence": confidence,
        "significant": confidence >= confidence_target,
        "n_total": n_total,
    }


# ---------------------------------------------------------------------------
# High-level facade — 实现 record_metric 与 assign_variant 的统一入口
# (兼容数据源未注入时的内存 fallback).
# ---------------------------------------------------------------------------
def create_experiment(
    name: str,
    variants: list[dict[str, Any]] | list[Variant],
    description: str = "",
    primary_metric: str = "match.score",
) -> Experiment:
    """构造 Experiment 对象 (内存),生成 id."""
    if isinstance(variants[0], dict):
        vs = [Variant(**v) for v in variants]
    else:
        vs = list(variants)
    exp = Experiment(
        id=str(uuid.uuid4()),
        name=name,
        description=description,
        variants=vs,
        status="draft",
        primary_metric=primary_metric,
    )
    return exp
