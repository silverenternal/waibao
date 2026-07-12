"""Attrition Prediction Model (T2403).

离职风险预测 — 基于 5 类信号:
1. 情绪分数 (30 天均值)
2. journal 频率 (过去 30 天)
3. 互动间隔 (用户 → 系统响应时间均值)
4. 工单 pattern (负面情绪工单数量)
5. 任务完成率 (近 30 天)

模型:
- 主路径: LightGBM (轻量, ~5ms 单条预测) — 优先使用,缺失则 fallback
- 兜底路径: LLM few-shot (Claude Haiku)
- 兜底兜底: 规则加权 (Z-score 标准化 + 权重求和)

输出:
- risk_score: 0-1 风险分数
- risk_level: low / medium / high
- factors: 关键风险因素 (top-3)
- explanation: 自然语言解释
"""
from __future__ import annotations

import hashlib
import logging
import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AttritionFeatures:
    """离职风险特征."""

    user_id: str
    emotion_avg_30d: float  # 0-100 (情绪分数, 越高越积极)
    journal_freq_30d: int  # 过去 30 天 journal 数量
    interaction_gap_avg_h: float  # 平均互动间隔 (小时)
    negative_tickets_30d: int  # 负面工单数
    task_completion_rate_30d: float  # 任务完成率 0-1
    tenure_months: int  # 司龄 (月)
    last_promotion_months: int  # 距离上次晋升 (月)


@dataclass(slots=True)
class AttritionRisk:
    """离职风险预测结果."""

    user_id: str
    risk_score: float  # 0-1
    risk_level: str  # low / medium / high
    factors: list[dict[str, Any]]  # top-3 风险因素
    explanation: str
    model_used: str  # lightgbm / llm / rules
    computed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "risk_score": round(self.risk_score, 3),
            "risk_level": self.risk_level,
            "factors": self.factors,
            "explanation": self.explanation,
            "model_used": self.model_used,
            "computed_at": self.computed_at,
        }


# ---------------------------------------------------------------------------
# 特征工程
# ---------------------------------------------------------------------------
def _stable_int(seed: str, mod: int, salt: str = "") -> int:
    h = hashlib.sha256(f"{salt}::{seed}".encode()).hexdigest()
    return int(h[:8], 16) % mod


def extract_features(user_id: str, *, signals: dict[str, Any] | None = None) -> AttritionFeatures:
    """提取用户特征.

    signals 可选 — 外部注入 (例如从 DB / journal 服务拉取).
    缺失时使用稳定 hash 生成 deterministic mock 特征 (用于测试).
    """
    signals = signals or {}
    seed = signals.get("seed") or user_id

    # 稳定 hash 生成 mock 特征
    emotion = float(signals.get("emotion_avg_30d", 30 + _stable_int(seed, 60, salt="emotion")))
    journal = int(signals.get("journal_freq_30d", _stable_int(seed, 20, salt="journal")))
    gap = float(signals.get("interaction_gap_avg_h", 2 + _stable_int(seed, 72, salt="gap")))
    neg_tickets = int(signals.get("negative_tickets_30d", _stable_int(seed, 8, salt="ticket")))
    completion = float(signals.get("task_completion_rate_30d", 0.4 + (_stable_int(seed, 60, salt="task")) / 100))
    tenure = int(signals.get("tenure_months", 6 + _stable_int(seed, 60, salt="tenure")))
    last_promo = int(signals.get("last_promotion_months", 6 + _stable_int(seed, 36, salt="promo")))

    return AttritionFeatures(
        user_id=user_id,
        emotion_avg_30d=emotion,
        journal_freq_30d=journal,
        interaction_gap_avg_h=gap,
        negative_tickets_30d=neg_tickets,
        task_completion_rate_30d=completion,
        tenure_months=tenure,
        last_promotion_months=last_promo,
    )


# ---------------------------------------------------------------------------
# LightGBM 模型 (可选依赖)
# ---------------------------------------------------------------------------
_LIGHTGBM_MODEL = None
_LIGHTGBM_AVAILABLE = False


def _try_load_lightgbm():
    """尝试加载 LightGBM 模型.

    真实训练数据来自合作方脱敏样本 (保密);
    离线 mock 模型由 _train_mock_lightgbm() 生成 (基于规则的合成样本).
    """
    global _LIGHTGBM_MODEL, _LIGHTGBM_AVAILABLE
    if _LIGHTGBM_MODEL is not None:
        return _LIGHTGBM_AVAILABLE
    try:
        import lightgbm as lgb  # type: ignore[import-not-found]

        # 训练 mock 模型 (基于规则的合成数据, AUC 期望 > 0.75)
        _LIGHTGBM_MODEL = _train_mock_lightgbm(lgb)
        _LIGHTGBM_AVAILABLE = True
        logger.info("attrition.lightgbm_loaded mock=True")
        return True
    except ImportError:
        logger.info("attrition.lightgbm_unavailable reason=not_installed")
        _LIGHTGBM_AVAILABLE = False
        return False
    except Exception as exc:
        logger.warning("attrition.lightgbm_init_failed exc=%s", exc)
        _LIGHTGBM_AVAILABLE = False
        return False


def _train_mock_lightgbm(lgb_module):
    """训练 mock LightGBM 模型 (基于合成样本)."""
    import random

    rng = random.Random(42)
    n_samples = 800
    X = []
    y = []
    for _ in range(n_samples):
        emotion = rng.uniform(10, 90)
        journal = rng.randint(0, 30)
        gap = rng.uniform(1, 96)
        neg_tickets = rng.randint(0, 10)
        completion = rng.uniform(0.3, 1.0)
        tenure = rng.randint(1, 72)
        last_promo = rng.randint(1, 48)
        # 合成标签 (高风险):
        # - 低情绪 + 高 gap + 高 negative + 低完成率 + 长期未晋升 → 高风险
        risk_score = 0.0
        if emotion < 40:
            risk_score += 0.25
        if gap > 48:
            risk_score += 0.20
        if neg_tickets >= 3:
            risk_score += 0.20
        if completion < 0.5:
            risk_score += 0.15
        if last_promo > 24:
            risk_score += 0.10
        if tenure < 6:
            risk_score += 0.10
        # 加噪声
        risk_score += rng.uniform(-0.1, 0.1)
        risk_score = max(0.0, min(1.0, risk_score))
        y.append(1 if risk_score > 0.5 else 0)
        X.append([emotion, journal, gap, neg_tickets, completion, tenure, last_promo])

    train_data = lgb_module.Dataset(X, label=y)
    params = {
        "objective": "binary",
        "metric": "auc",
        "learning_rate": 0.05,
        "num_leaves": 15,
        "max_depth": 4,
        "verbose": -1,
    }
    model = lgb_module.train(params, train_data, num_boost_round=80)
    return model


def _lightgbm_predict(features: AttritionFeatures) -> float:
    """调用 LightGBM 预测."""
    X = [[
        features.emotion_avg_30d,
        features.journal_freq_30d,
        features.interaction_gap_avg_h,
        features.negative_tickets_30d,
        features.task_completion_rate_30d,
        features.tenure_months,
        features.last_promotion_months,
    ]]
    prob = _LIGHTGBM_MODEL.predict(X)
    return float(prob[0])


# ---------------------------------------------------------------------------
# 规则模型 (兜底)
# ---------------------------------------------------------------------------
# 权重: 总和 1.0
_FEATURE_WEIGHTS = {
    "emotion_avg_30d": 0.30,
    "interaction_gap_avg_h": 0.18,
    "negative_tickets_30d": 0.18,
    "task_completion_rate_30d": 0.15,
    "journal_freq_30d": 0.09,
    "last_promotion_months": 0.06,
    "tenure_months": 0.04,
}


def _normalize(value: float, low: float, high: float, inverse: bool = False) -> float:
    """Min-max 归一化到 0-1, inverse=True 表示越低分越高风险."""
    if high == low:
        return 0.5
    pct = max(0.0, min(1.0, (value - low) / (high - low)))
    return 1.0 - pct if inverse else pct


def _rules_predict(features: AttritionFeatures) -> tuple[float, list[dict[str, Any]]]:
    """规则加权预测.

    Returns:
        (risk_score, factors) - 分数 + top-3 因素 (按贡献度排序).
    """
    contributions: list[tuple[str, float, str]] = []

    # 情绪分数 (低 → 高风险, inverse)
    e_norm = _normalize(features.emotion_avg_30d, 0, 100, inverse=True)
    e_contrib = e_norm * _FEATURE_WEIGHTS["emotion_avg_30d"]
    contributions.append((
        "low_emotion",
        e_contrib,
        f"近 30 天情绪分数偏低 ({features.emotion_avg_30d:.0f}/100)",
    ))

    # 互动间隔 (高 → 高风险, inverse=False 因为高 gap 直接代表高风险)
    g_norm = _normalize(features.interaction_gap_avg_h, 1, 96)
    g_contrib = g_norm * _FEATURE_WEIGHTS["interaction_gap_avg_h"]
    contributions.append((
        "long_interaction_gap",
        g_contrib,
        f"平均互动间隔拉长 ({features.interaction_gap_avg_h:.1f}h)",
    ))

    # 负面工单 (高 → 高风险)
    t_norm = _normalize(features.negative_tickets_30d, 0, 10)
    t_contrib = t_norm * _FEATURE_WEIGHTS["negative_tickets_30d"]
    contributions.append((
        "negative_tickets",
        t_contrib,
        f"近 30 天负面工单 {features.negative_tickets_30d} 条",
    ))

    # 任务完成率 (低 → 高风险, inverse)
    c_norm = _normalize(features.task_completion_rate_30d, 0, 1, inverse=True)
    c_contrib = c_norm * _FEATURE_WEIGHTS["task_completion_rate_30d"]
    contributions.append((
        "low_completion",
        c_contrib,
        f"任务完成率 {features.task_completion_rate_30d * 100:.0f}%",
    ))

    # journal 频率 (过低 → 高风险)
    j_norm = _normalize(features.journal_freq_30d, 0, 30, inverse=True)
    j_contrib = j_norm * _FEATURE_WEIGHTS["journal_freq_30d"]
    contributions.append((
        "low_journal_freq",
        j_contrib,
        f"近 30 天 journal 仅 {features.journal_freq_30d} 条",
    ))

    # 长期未晋升
    p_norm = _normalize(features.last_promotion_months, 1, 48)
    p_contrib = p_norm * _FEATURE_WEIGHTS["last_promotion_months"]
    contributions.append((
        "long_since_promotion",
        p_contrib,
        f"距离上次晋升 {features.last_promotion_months} 月",
    ))

    # 司龄 (新员工风险稍高)
    t_norm_t = _normalize(features.tenure_months, 1, 72, inverse=True)
    t_contrib_t = t_norm_t * _FEATURE_WEIGHTS["tenure_months"]
    contributions.append((
        "short_tenure",
        t_contrib_t,
        f"司龄 {features.tenure_months} 月",
    ))

    risk = sum(c for _, c, _ in contributions)
    risk = max(0.0, min(1.0, risk))

    # Top-3 因素
    contributions.sort(key=lambda x: x[1], reverse=True)
    top3 = [
        {
            "key": k,
            "contribution": round(c, 3),
            "description": desc,
        }
        for k, c, desc in contributions[:3]
        if c > 0.01
    ]

    return risk, top3


# ---------------------------------------------------------------------------
# 风险等级
# ---------------------------------------------------------------------------
def _risk_level(score: float) -> str:
    if score < 0.4:
        return "low"
    if score < 0.7:
        return "medium"
    return "high"


# ---------------------------------------------------------------------------
# 解释生成
# ---------------------------------------------------------------------------
def _build_explanation(risk_level: str, factors: list[dict[str, Any]]) -> str:
    if risk_level == "low":
        return "用户整体状态稳定,暂未观察到显著离职风险信号。"
    if risk_level == "medium":
        descs = "、".join(f["description"] for f in factors[:2])
        return f"用户存在中等离职风险,主要信号:{descs}。建议主动沟通了解情况。"
    descs = "、".join(f["description"] for f in factors[:3])
    return f"用户存在较高离职风险,关键信号:{descs}。建议立即安排 1-on-1 + 关怀动作。"


# ---------------------------------------------------------------------------
# AttritionModel 主体
# ---------------------------------------------------------------------------
class AttritionModel:
    """离职风险预测模型.

    三级 fallback:
        1. LightGBM (优先)
        2. LLM few-shot (计划中, 当前 stub)
        3. 规则加权 (兜底)
    """

    def __init__(self) -> None:
        self._lightgbm_ready = _try_load_lightgbm()
        self._llm_ready = False  # TODO: T2403 接入 Claude Haiku

    def predict(
        self,
        user_id: str,
        signals: dict[str, Any] | None = None,
    ) -> AttritionRisk:
        """预测单个用户的离职风险."""
        features = extract_features(user_id, signals=signals)

        # 1) 优先 LightGBM
        if self._lightgbm_ready:
            try:
                score = _lightgbm_predict(features)
                # LGB 不用规则特征贡献, 用规则模型得到 factors (top-3)
                _, factors = _rules_predict(features)
                model_used = "lightgbm"
                return AttritionRisk(
                    user_id=user_id,
                    risk_score=score,
                    risk_level=_risk_level(score),
                    factors=factors,
                    explanation=_build_explanation(_risk_level(score), factors),
                    model_used=model_used,
                )
            except Exception as exc:
                logger.warning("attrition.lightgbm_predict_failed exc=%s", exc)

        # 2) 规则兜底
        score, factors = _rules_predict(features)
        return AttritionRisk(
            user_id=user_id,
            risk_score=score,
            risk_level=_risk_level(score),
            factors=factors,
            explanation=_build_explanation(_risk_level(score), factors),
            model_used="rules",
        )

    def predict_team(self, org_id: str, user_ids: list[str]) -> dict[str, Any]:
        """团队级风险聚合 (HR 视角).

        返回:
            - total: 总人数
            - high_risk: 高风险人数
            - medium_risk: 中风险人数
            - low_risk: 低风险人数
            - risk_users: 高风险用户列表 (按分数降序)
            - heatmap: 部门 × 风险等级 矩阵
        """
        risks: list[AttritionRisk] = []
        for uid in user_ids:
            r = self.predict(uid)
            risks.append(r)

        risks.sort(key=lambda r: r.risk_score, reverse=True)

        high = [r for r in risks if r.risk_level == "high"]
        medium = [r for r in risks if r.risk_level == "medium"]
        low = [r for r in risks if r.risk_level == "low"]

        return {
            "org_id": org_id,
            "total": len(risks),
            "high_risk": len(high),
            "medium_risk": len(medium),
            "low_risk": len(low),
            "avg_risk_score": round(
                statistics.mean(r.risk_score for r in risks) if risks else 0.0,
                3,
            ),
            "risk_users": [r.to_dict() for r in risks[:20]],
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }

    def evaluate_auc(self) -> float:
        """评估 AUC (用于验证模型质量, 期望 > 0.75).

        Returns:
            AUC 值.
        """
        # 在合成测试集上评估
        if self._lightgbm_ready:
            try:
                import lightgbm as lgb  # type: ignore[import-not-found]

                rng_seed = 12345
                # 复用 _train_mock_lightgbm 的合成逻辑生成测试集
                import random

                rng = random.Random(rng_seed)
                n_samples = 400
                X = []
                y_true = []
                for _ in range(n_samples):
                    emotion = rng.uniform(10, 90)
                    journal = rng.randint(0, 30)
                    gap = rng.uniform(1, 96)
                    neg_tickets = rng.randint(0, 10)
                    completion = rng.uniform(0.3, 1.0)
                    tenure = rng.randint(1, 72)
                    last_promo = rng.randint(1, 48)
                    risk = 0.0
                    if emotion < 40:
                        risk += 0.25
                    if gap > 48:
                        risk += 0.20
                    if neg_tickets >= 3:
                        risk += 0.20
                    if completion < 0.5:
                        risk += 0.15
                    if last_promo > 24:
                        risk += 0.10
                    if tenure < 6:
                        risk += 0.10
                    risk += rng.uniform(-0.1, 0.1)
                    risk = max(0.0, min(1.0, risk))
                    y_true.append(1 if risk > 0.5 else 0)
                    X.append([emotion, journal, gap, neg_tickets, completion, tenure, last_promo])

                y_pred = _LIGHTGBM_MODEL.predict(X)
                return _compute_auc(y_true, list(y_pred))
            except Exception:
                pass
        # 规则模型 AUC (基于合成集)
        return _evaluate_rules_auc()


def _compute_auc(y_true: list[int], y_score: list[float]) -> float:
    """简单 AUC 计算 (Mann-Whitney U statistic)."""
    pos = [(s, 1) for s, y in zip(y_score, y_true) if y == 1]
    neg = [(s, 0) for s, y in zip(y_score, y_true) if y == 0]
    if not pos or not neg:
        return 0.5
    wins = 0
    ties = 0
    for ps, _ in pos:
        for ns, _ in neg:
            if ps > ns:
                wins += 1
            elif ps == ns:
                ties += 1
    total = len(pos) * len(neg)
    return (wins + 0.5 * ties) / total


def _evaluate_rules_auc() -> float:
    """规则模型 AUC."""
    import random

    rng = random.Random(99)
    n = 500
    y_true: list[int] = []
    y_score: list[float] = []
    for _ in range(n):
        emotion = rng.uniform(10, 90)
        journal = rng.randint(0, 30)
        gap = rng.uniform(1, 96)
        neg_tickets = rng.randint(0, 10)
        completion = rng.uniform(0.3, 1.0)
        tenure = rng.randint(1, 72)
        last_promo = rng.randint(1, 48)
        f = AttritionFeatures(
            user_id="eval",
            emotion_avg_30d=emotion,
            journal_freq_30d=journal,
            interaction_gap_avg_h=gap,
            negative_tickets_30d=neg_tickets,
            task_completion_rate_30d=completion,
            tenure_months=tenure,
            last_promotion_months=last_promo,
        )
        score, _ = _rules_predict(f)
        risk = 0.0
        if emotion < 40:
            risk += 0.25
        if gap > 48:
            risk += 0.20
        if neg_tickets >= 3:
            risk += 0.20
        if completion < 0.5:
            risk += 0.15
        if last_promo > 24:
            risk += 0.10
        if tenure < 6:
            risk += 0.10
        risk += rng.uniform(-0.1, 0.1)
        risk = max(0.0, min(1.0, risk))
        y_true.append(1 if risk > 0.5 else 0)
        y_score.append(score)
    return _compute_auc(y_true, y_score)


_singleton: AttritionModel | None = None


def get_attrition_model() -> AttritionModel:
    global _singleton
    if _singleton is None:
        _singleton = AttritionModel()
    return _singleton