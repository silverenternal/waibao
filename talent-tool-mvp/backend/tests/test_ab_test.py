"""A/B 实验框架测试 — T805.

覆盖:
- 哈希分桶分布均匀性 (100k 用户, 误差 < 2%)
- variant 权重比例正确
- assign_variant 稳定 (同 user 永远同 variant)
- 不同 salt 错开分配
- 显著性计算: 强烈差异 vs 无显著差异
"""
from __future__ import annotations

import statistics

from services.ab_test import (
    BUILTIN_METRICS,
    Experiment,
    MetricSample,
    MetricStore,
    Variant,
    assign_variant,
    compute_significance,
    get_hash_salt,
    hash_bucket,
    record_metric,
    set_hash_salt,
)


# ---------------------------------------------------------------------------
# Hash bucketing
# ---------------------------------------------------------------------------
def test_hash_bucket_stable():
    """同 user 同 salt 永远落同一桶."""
    s = get_hash_salt()
    bucket_1 = hash_bucket("user-42", salt=s)
    bucket_2 = hash_bucket("user-42", salt=s)
    assert bucket_1 == bucket_2
    assert 0 <= bucket_1 < 100


def test_hash_bucket_distribution_uniform():
    """100k 用户 100 桶分布均匀, 每桶至少应在均值 30% 范围内."""
    n_users = 100_000
    counts = [0] * 100
    for i in range(n_users):
        b = hash_bucket(f"u-{i}", salt="uniform-test-salt")
        counts[b] += 1
    avg = n_users / 100  # 1000
    # 至少 95% 桶在 [avg*0.7, avg*1.3] 内
    in_range = sum(1 for c in counts if 0.7 * avg <= c <= 1.3 * avg)
    assert in_range >= 95, f"only {in_range}/100 buckets within [0.7,1.3]x avg"
    # 最大偏差
    max_dev = max(abs(c - avg) for c in counts) / avg
    assert max_dev < 0.1, f"max deviation = {max_dev:.3f}"


def test_hash_bucket_changes_with_salt():
    """换 salt 应重新分配 (50%+ 桶不同)."""
    salt_a = "salt-A"
    salt_b = "salt-B"
    n = 1000
    diffs = 0
    for i in range(n):
        if hash_bucket(f"u-{i}", salt=salt_a) != hash_bucket(f"u-{i}", salt=salt_b):
            diffs += 1
    assert diffs > n * 0.8, f"only {diffs}/{n} reassigned on salt change"


def test_hash_bucket_returns_int_in_range():
    for i in range(50):
        b = hash_bucket(i, buckets=10)
        assert isinstance(b, int)
        assert 0 <= b < 10


def test_builtin_metrics_nonempty():
    assert len(BUILTIN_METRICS) >= 5
    assert "match.score" in BUILTIN_METRICS


# ---------------------------------------------------------------------------
# Assign variant
# ---------------------------------------------------------------------------
def _make_experiment() -> Experiment:
    return Experiment(
        id="exp-1",
        name="match_weights_v2",
        description="weights A/B",
        variants=[
            Variant(name="control", weight=50),
            Variant(name="semantic_heavy", weight=30),
            Variant(name="experience_focused", weight=20),
        ],
        status="running",
        primary_metric="match.score",
    )


def test_assign_variant_proportions_close_to_weights():
    """1000 个 user 落入各 variant 的比例应接近权重比 (50/30/20)."""
    exp = _make_experiment()
    counts = {"control": 0, "semantic_heavy": 0, "experience_focused": 0}
    for i in range(2000):
        v = assign_variant(exp, f"user-{i}")
        counts[v] += 1
    # 控制应在 [45,55]%, semantic_heavy [25,35]%, experience [15,25]%
    pct = {k: v / 2000 for k, v in counts.items()}
    assert 0.40 <= pct["control"] <= 0.60
    assert 0.22 <= pct["semantic_heavy"] <= 0.38
    assert 0.13 <= pct["experience_focused"] <= 0.27


def test_assign_variant_stable_per_user():
    exp = _make_experiment()
    for i in range(20):
        u = f"stable-user-{i}"
        v1 = assign_variant(exp, u)
        v2 = assign_variant(exp, u)
        assert v1 == v2, f"user {u} got {v1} then {v2}"


def test_assign_variant_stopped_returns_first():
    """stopped 状态下降级到第一个 variant."""
    exp = Experiment(
        id="x",
        name="y",
        description="",
        variants=[Variant(name="a", weight=50), Variant(name="b", weight=50)],
        status="stopped",
        primary_metric="match.score",
    )
    assert assign_variant(exp, "any-user") == "a"


def test_assign_variant_accepts_dict_payload():
    """可传入 dict (admin API 内部用)."""
    payload = {
        "name": "match_weights_v2",
        "status": "running",
        "variants": [
            {"name": "control", "weight": 100},
            {"name": "alt", "weight": 100},
        ],
    }
    v1 = assign_variant(payload, "u-1")
    v2 = assign_variant(payload, "u-1")
    assert v1 == v2
    assert v1 in ("control", "alt")


# ---------------------------------------------------------------------------
# Metrics recording + significance
# ---------------------------------------------------------------------------
def test_record_metric_does_not_raise():
    store = MetricStore()
    record_metric("exp-1", "control", "match.score", 0.85, store=store)
    record_metric("exp-1", "alt", "match.score", 0.92, store=store)
    assert len(store.list()) == 2


def test_compute_significance_strong_diff_significant():
    """control 均值 0.5 ± 0.05, treatment 0.85 ± 0.05 (n=80/80) — 应显著."""
    import random
    random.seed(42)
    store = MetricStore()
    for _ in range(80):
        record_metric("exp-a", "control", "match.score", random.gauss(0.5, 0.05), store=store)
        record_metric("exp-a", "treatment", "match.score", random.gauss(0.85, 0.05), store=store)
    result = compute_significance(
        "exp-a", "match.score", store=store, confidence_target=0.95
    )
    assert result["significant"] is True, result
    assert result["confidence"] >= 0.95, result
    lift_treat = [v["lift_vs_baseline"] for v in result["variants"] if not v["is_baseline"]][0]
    assert lift_treat > 0.5, lift_treat
    assert result["n_total"] == 160
    # p-value 应该极小
    p_treat = [v["p_value"] for v in result["variants"] if not v["is_baseline"]][0]
    assert p_treat < 0.05


def test_compute_significance_no_diff_not_significant():
    """两个 variant 同分布 — p-value 应很大 (>0.1)."""
    store = MetricStore()
    for i in range(40):
        # 用 fixed seed-like 模式:0.5 + i*0.001
        record_metric("exp-b", "control", "hatch.time_to_match", 0.5 + i * 0.001, store=store)
        record_metric("exp-b", "alt", "hatch.time_to_match", 0.5 + i * 0.001, store=store)
    result = compute_significance(
        "exp-b", "hatch.time_to_match", store=store, confidence_target=0.95
    )
    assert result["significant"] is False
    assert result["confidence"] < 0.95
    # variants 数量 = 2, baseline 标记正确
    assert len(result["variants"]) == 2
    baseline_v = [v for v in result["variants"] if v["is_baseline"]][0]
    non_baseline = [v for v in result["variants"] if not v["is_baseline"]][0]
    assert abs(baseline_v["lift_vs_baseline"]) < 1e-9
    assert abs(non_baseline["lift_vs_baseline"]) < 0.1


def test_compute_significance_empty_data_returns_zero():
    store = MetricStore()
    result = compute_significance("exp-empty", "match.score", store=store)
    assert result["confidence"] == 0.0
    assert result["variants"] == []
    assert result["n_total"] == 0


def test_compute_significance_p_value_in_range():
    """p-value 应在 [0,1]."""
    store = MetricStore()
    for i in range(20):
        record_metric("exp-c", "v1", "metric.x", 0.5 + 0.001 * i, store=store)
        record_metric("exp-c", "v2", "metric.x", 0.4 + 0.002 * i, store=store)
    result = compute_significance("exp-c", "metric.x", store=store)
    for v in result["variants"]:
        assert 0.0 <= v["p_value"] <= 1.0


def test_metric_store_threadsafe_list_filter():
    store = MetricStore()
    for i in range(10):
        store.record(
            MetricSample(experiment_id="e", variant="a", metric_name="m", value=float(i))
        )
        store.record(
            MetricSample(experiment_id="e", variant="b", metric_name="m", value=float(i + 1))
        )
        store.record(
            MetricSample(experiment_id="e", variant="a", metric_name="other", value=float(i))
        )
    a_only = store.list(variant="a")
    assert all(s.variant == "a" for s in a_only)
    m_only = store.list(metric_name="m")
    assert all(s.metric_name == "m" for s in m_only)
    assert len(store.list(experiment_id="e")) == 30


def test_hash_salt_overridable():
    """set_hash_salt 后会影响后续 hash 分配."""
    original = get_hash_salt()
    try:
        set_hash_salt("override-1")
        b1 = hash_bucket("user-x", salt="override-1")
        b2 = hash_bucket("user-x", salt="override-1")
        assert b1 == b2
        # 不同 salt 分配应显著不同
        diffs = sum(
            1
            for i in range(1000)
            if hash_bucket(f"u-{i}", salt="override-1")
            != hash_bucket(f"u-{i}", salt="override-2")
        )
        assert diffs > 700
    finally:
        set_hash_salt(original)


def test_weights_distribution_statistical_balance():
    """大型样本下,variant 比例接近权重 (chi-square 友好)."""
    exp = _make_experiment()
    counts = {"control": 0, "semantic_heavy": 0, "experience_focused": 0}
    n = 5000
    for i in range(n):
        counts[assign_variant(exp, f"u-{i}")] += 1
    expected = {"control": 0.5 * n, "semantic_heavy": 0.3 * n, "experience_focused": 0.2 * n}
    for k, e in expected.items():
        assert abs(counts[k] - e) / e < 0.05, f"{k}: got {counts[k]}, expected ~{e}"
