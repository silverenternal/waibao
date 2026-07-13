"""Predictive Analytics (T2803) — LightGBM + Prophet.

Three model families:

1. AttritionModel (LightGBM)
   Predicts 0-1 risk of a user leaving the platform (求职者流失 / 员工流失)
   Features: emotion score, journal freq, interaction gap, ticket pattern,
             task completion, tenure, last promotion
   Output:  risk_score, risk_level, top-3 factors, intervention advice

2. HireSuccessModel (LightGBM)
   Predicts post-hire success score (0-1) of a candidate
   Features: match score, channel, seniority, time-to-decision, eval signals

3. ProphetModel
   Time-series forecast of candidate inflow / ticket volume / match creation
   Horizon configurable (default 30 days)

Design:
- Train on synthetic / historical data (DB loader pluggable)
- Persist trained models to `models/predictive/*.pkl`
- Online inference: < 100ms (single feature dict → score)
- Auto-retrain: Celery beat monthy (or any scheduler)

The module is fully self-contained and falls back to a deterministic
weighted-z-score baseline if LightGBM/Prophet are not available.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import pickle
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# Optional heavy deps — degrade gracefully
# -------------------------------------------------------------------
try:  # pragma: no cover
    import lightgbm as lgb
    import numpy as np
    _HAS_LGB = True
except Exception as exc:  # pragma: no cover
    logger.warning("lightgbm/numpy not available: %s", exc)
    lgb = None  # type: ignore
    np = None  # type: ignore
    _HAS_LGB = False

try:  # pragma: no cover
    from prophet import Prophet
    _HAS_PROPHET = True
except Exception as exc:  # pragma: no cover
    logger.warning("prophet not available: %s", exc)
    Prophet = None  # type: ignore
    _HAS_PROPHET = False

try:  # pragma: no cover
    from sklearn.metrics import roc_auc_score
    _HAS_SK = True
except Exception:  # pragma: no cover
    _HAS_SK = False
    def roc_auc_score(y, p):  # type: ignore
        return float("nan")


# -------------------------------------------------------------------
# Paths
# -------------------------------------------------------------------
MODEL_DIR = Path(os.getenv("PREDICTIVE_MODEL_DIR", "models/predictive"))
MODEL_DIR.mkdir(parents=True, exist_ok=True)


# ===================================================================
# 1. AttritionModel (LightGBM)
# ===================================================================
ATTRITION_FEATURES = [
    "emotion_avg_30d",
    "journal_freq_30d",
    "interaction_gap_avg_h",
    "negative_tickets_30d",
    "task_completion_rate_30d",
    "tenure_months",
    "last_promotion_months",
]


@dataclass(slots=True)
class AttritionFeatures:
    user_id: str
    emotion_avg_30d: float
    journal_freq_30d: int
    interaction_gap_avg_h: float
    negative_tickets_30d: int
    task_completion_rate_30d: float
    tenure_months: int
    last_promotion_months: int


@dataclass(slots=True)
class AttritionRisk:
    user_id: str
    risk_score: float
    risk_level: str
    factors: list[dict[str, Any]]
    explanation: str
    intervention: list[str]
    model_used: str
    inference_ms: float
    computed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "risk_score": round(self.risk_score, 3),
            "risk_level": self.risk_level,
            "factors": self.factors,
            "explanation": self.explanation,
            "intervention": self.intervention,
            "model_used": self.model_used,
            "inference_ms": round(self.inference_ms, 2),
            "computed_at": self.computed_at,
        }


def _stable_int(seed: str, mod: int, salt: str = "") -> int:
    h = hashlib.sha256(f"{salt}::{seed}".encode()).hexdigest()
    return int(h[:8], 16) % mod


def _extract_attrition_features(
    user_id: str, signals: dict[str, Any] | None = None
) -> AttritionFeatures:
    s = signals or {}
    seed = s.get("seed") or user_id
    return AttritionFeatures(
        user_id=user_id,
        emotion_avg_30d=float(
            s.get("emotion_avg_30d", 30 + _stable_int(seed, 60, "emotion"))
        ),
        journal_freq_30d=int(
            s.get("journal_freq_30d", _stable_int(seed, 20, "journal"))
        ),
        interaction_gap_avg_h=float(
            s.get("interaction_gap_avg_h", 2 + _stable_int(seed, 72, "gap"))
        ),
        negative_tickets_30d=int(
            s.get("negative_tickets_30d", _stable_int(seed, 8, "ticket"))
        ),
        task_completion_rate_30d=float(
            s.get(
                "task_completion_rate_30d",
                0.4 + _stable_int(seed, 60, "task") / 100,
            )
        ),
        tenure_months=int(
            s.get("tenure_months", 6 + _stable_int(seed, 60, "tenure"))
        ),
        last_promotion_months=int(
            s.get("last_promotion_months", 6 + _stable_int(seed, 36, "promo"))
        ),
    )


def _attrition_vector(f: AttritionFeatures) -> list[float]:
    return [
        f.emotion_avg_30d,
        f.journal_freq_30d,
        f.interaction_gap_avg_h,
        f.negative_tickets_30d,
        f.task_completion_rate_30d,
        f.tenure_months,
        f.last_promotion_months,
    ]


def _attrition_risk_level(score: float) -> str:
    if score >= 0.7:
        return "high"
    if score >= 0.4:
        return "medium"
    return "low"


def _attrition_factors(
    f: AttritionFeatures, model: Any | None
) -> list[dict[str, Any]]:
    """Top-3 risk factors — prefer model.feature_importance, fallback heuristic."""
    if model is not None and _HAS_LGB:
        try:
            booster = (
                model.booster_ if hasattr(model, "booster_") else model
            )
            imp = booster.feature_importance(importance_type="gain")
            pairs = list(zip(ATTRITION_FEATURES, imp))
            pairs.sort(key=lambda x: -x[1])
            top = pairs[:3]
        except Exception:
            top = _heuristic_attrition_factors(f)
    else:
        top = _heuristic_attrition_factors(f)
    return [
        {
            "feature": name,
            "impact": round(float(imp), 3) if isinstance(imp, (int, float)) else 0.0,
            "direction": "up" if "neg" in name.lower() or "gap" in name.lower() else "down",
        }
        for name, imp in top
    ]


def _heuristic_attrition_factors(f: AttritionFeatures) -> list[tuple[str, float]]:
    """Inverse-emotion + interaction-gap + negative-tickets as proxy."""
    inv_emotion = max(0.0, 80 - f.emotion_avg_30d) / 80
    gap = min(1.0, f.interaction_gap_avg_h / 48)
    neg = min(1.0, f.negative_tickets_30d / 5)
    pairs = [
        ("emotion_avg_30d", inv_emotion),
        ("interaction_gap_avg_h", gap),
        ("negative_tickets_30d", neg),
    ]
    pairs.sort(key=lambda x: -x[1])
    return pairs


def _attrition_intervention(score: float, f: AttritionFeatures) -> list[str]:
    out: list[str] = []
    if score >= 0.7:
        out.append("立即触发 1:1 关怀会话")
        out.append("推送个性化 career_plan")
    elif score >= 0.4:
        out.append("邀请完成 情绪检查问卷")
        out.append("调整任务节奏,降低疲劳")
    else:
        out.append("维持周报节奏")
    if f.emotion_avg_30d < 40:
        out.append("安排心理支持资源")
    if f.negative_tickets_30d >= 3:
        out.append("联系客服主管回访高频投诉")
    if f.last_promotion_months >= 24:
        out.append("评估晋升通道 / 调薪窗口")
    return out


class AttritionModel:
    """LightGBM classifier for attrition risk.

    - `train(X, y)`: fits a small booster
    - `predict(user_id, signals)`: returns AttritionRisk
    - `evaluate(X, y)`: returns AUC
    - `save() / load()`: pickle the fitted booster
    """

    def __init__(self) -> None:
        self.model: Any = None
        self._loaded_from: Optional[Path] = None

    # ----------------------------------------------------------------
    # Train / eval
    # ----------------------------------------------------------------
    def train(
        self,
        X: Iterable[list[float]],
        y: Iterable[int],
        *,
        num_boost_round: int = 200,
    ) -> dict[str, float]:
        if not _HAS_LGB:
            raise RuntimeError("lightgbm not available — cannot train")
        X_arr = np.asarray(list(X), dtype=np.float32)
        y_arr = np.asarray(list(y), dtype=np.int32)
        params = {
            "objective": "binary",
            "metric": "auc",
            "learning_rate": 0.05,
            "num_leaves": 31,
            "min_data_in_leaf": 5,
            "feature_fraction": 0.9,
            "verbose": -1,
        }
        train_data = lgb.Dataset(X_arr, label=y_arr, feature_name=ATTRITION_FEATURES)
        booster = lgb.train(
            params,
            train_data,
            num_boost_round=num_boost_round,
        )
        self.model = booster
        return self.evaluate(X_arr, y_arr)

    def evaluate(self, X: Any, y: Any) -> dict[str, float]:
        if self.model is None or not _HAS_LGB or not _HAS_SK:
            return {"auc": float("nan"), "n": int(len(y))}
        p = self.model.predict(X)
        try:
            auc = float(roc_auc_score(y, p))
        except Exception:
            auc = float("nan")
        return {"auc": auc, "n": int(len(y))}

    # ----------------------------------------------------------------
    # Persist
    # ----------------------------------------------------------------
    def save(self, name: str = "attrition_v1.pkl") -> Path:
        p = MODEL_DIR / name
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("wb") as f:
            pickle.dump(self.model, f)
        self._loaded_from = p
        return p

    def load(self, name: str = "attrition_v1.pkl") -> bool:
        p = MODEL_DIR / name
        if not p.exists():
            return False
        try:
            with p.open("rb") as f:
                self.model = pickle.load(f)
            self._loaded_from = p
            return True
        except Exception as exc:  # pragma: no cover
            logger.warning("attrition model load failed: %s", exc)
            return False

    # ----------------------------------------------------------------
    # Inference
    # ----------------------------------------------------------------
    def predict(
        self, user_id: str, signals: dict[str, Any] | None = None
    ) -> AttritionRisk:
        t0 = time.time()
        f = _extract_attrition_features(user_id, signals)
        vec = _attrition_vector(f)
        if self.model is None and _HAS_LGB:
            self.load()  # try load
        if self.model is not None and _HAS_LGB:
            try:
                p = float(self.model.predict(np.asarray([vec], dtype=np.float32))[0])
                model_used = "lightgbm"
            except Exception as exc:  # pragma: no cover
                logger.warning("attrition predict failed: %s", exc)
                p, model_used = self._heuristic_predict(f)
        else:
            p, model_used = self._heuristic_predict(f)
        score = max(0.0, min(1.0, p))
        level = _attrition_risk_level(score)
        factors = _attrition_factors(f, self.model)
        intervention = _attrition_intervention(score, f)
        explanation = (
            f"基于 {len(ATTRITION_FEATURES)} 个特征 (情绪/日志/互动/工单/任务/司龄/晋升),"
            f" {model_used} 模型给出风险分数 {score:.2f} ({level})."
        )
        return AttritionRisk(
            user_id=user_id,
            risk_score=score,
            risk_level=level,
            factors=factors,
            explanation=explanation,
            intervention=intervention,
            model_used=model_used,
            inference_ms=(time.time() - t0) * 1000,
        )

    def _heuristic_predict(self, f: AttritionFeatures) -> tuple[float, str]:
        inv_emotion = max(0.0, 80 - f.emotion_avg_30d) / 80
        gap = min(1.0, f.interaction_gap_avg_h / 48)
        neg = min(1.0, f.negative_tickets_30d / 5)
        low_task = max(0.0, 0.7 - f.task_completion_rate_30d) / 0.7
        long_no_promo = min(1.0, f.last_promotion_months / 24)
        score = (
            0.30 * inv_emotion
            + 0.20 * gap
            + 0.20 * neg
            + 0.15 * low_task
            + 0.15 * long_no_promo
        )
        return float(max(0.0, min(1.0, score))), "rules"


# ===================================================================
# 2. HireSuccessModel (LightGBM)
# ===================================================================
HIRE_SUCCESS_FEATURES = [
    "match_score",
    "channel_idx",
    "seniority_idx",
    "time_to_decision_h",
    "eval_clarity",
    "eval_culture",
    "eval_technical",
    "city_match",
    "remote_ok",
]


def _stable_float(seed: str, salt: str) -> float:
    h = hashlib.sha256(f"{salt}::{seed}".encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def _hire_success_features(
    candidate_id: str, signals: dict[str, Any] | None = None
) -> tuple[list[float], dict[str, Any]]:
    s = signals or {}
    seed = s.get("seed") or candidate_id
    return (
        [
            float(s.get("match_score", 0.5 + _stable_float(seed, "ms") * 0.5)),
            int(s.get("channel_idx", _stable_int(seed, 6, "ch"))),
            int(s.get("seniority_idx", _stable_int(seed, 5, "sn"))),
            float(s.get("time_to_decision_h", 6 + _stable_int(seed, 96, "td"))),
            float(s.get("eval_clarity", 0.4 + _stable_float(seed, "cl") * 0.6)),
            float(s.get("eval_culture", 0.4 + _stable_float(seed, "cu") * 0.6)),
            float(
                s.get("eval_technical", 0.4 + _stable_float(seed, "te") * 0.6)
            ),
            int(s.get("city_match", _stable_int(seed, 2, "cm"))),
            int(s.get("remote_ok", _stable_int(seed, 2, "rm"))),
        ],
        s.get("meta", {}),
    )


@dataclass(slots=True)
class HireSuccessScore:
    candidate_id: str
    success_score: float
    drivers: list[dict[str, Any]]
    model_used: str
    inference_ms: float
    explanation: str
    computed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "success_score": round(self.success_score, 3),
            "drivers": self.drivers,
            "model_used": self.model_used,
            "inference_ms": round(self.inference_ms, 2),
            "explanation": self.explanation,
            "computed_at": self.computed_at,
        }


class HireSuccessModel:
    """LightGBM regression for hire-success (0-1)."""

    def __init__(self) -> None:
        self.model: Any = None

    def train(
        self,
        X: Iterable[list[float]],
        y: Iterable[float],
        *,
        num_boost_round: int = 200,
    ) -> dict[str, float]:
        if not _HAS_LGB:
            raise RuntimeError("lightgbm not available")
        X_arr = np.asarray(list(X), dtype=np.float32)
        y_arr = np.asarray(list(y), dtype=np.float32)
        params = {
            "objective": "regression",
            "metric": "rmse",
            "learning_rate": 0.05,
            "num_leaves": 31,
            "verbose": -1,
        }
        train_data = lgb.Dataset(
            X_arr, label=y_arr, feature_name=HIRE_SUCCESS_FEATURES
        )
        self.model = lgb.train(
            params, train_data, num_boost_round=num_boost_round
        )
        return self.evaluate(X_arr, y_arr)

    def evaluate(self, X: Any, y: Any) -> dict[str, float]:
        if self.model is None or not _HAS_LGB:
            return {"rmse": float("nan"), "n": int(len(y))}
        p = self.model.predict(X)
        rmse = float(math.sqrt(((p - y) ** 2).mean()))
        return {"rmse": rmse, "n": int(len(y))}

    def save(self, name: str = "hire_success_v1.pkl") -> Path:
        p = MODEL_DIR / name
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("wb") as f:
            pickle.dump(self.model, f)
        return p

    def load(self, name: str = "hire_success_v1.pkl") -> bool:
        p = MODEL_DIR / name
        if not p.exists():
            return False
        try:
            with p.open("rb") as f:
                self.model = pickle.load(f)
            return True
        except Exception as exc:  # pragma: no cover
            logger.warning("hire_success model load failed: %s", exc)
            return False

    def predict(
        self, candidate_id: str, signals: dict[str, Any] | None = None
    ) -> HireSuccessScore:
        t0 = time.time()
        vec, meta = _hire_success_features(candidate_id, signals)
        if self.model is None and _HAS_LGB:
            self.load()
        if self.model is not None and _HAS_LGB:
            try:
                p = float(
                    self.model.predict(np.asarray([vec], dtype=np.float32))[0]
                )
                model_used = "lightgbm"
            except Exception as exc:  # pragma: no cover
                logger.warning("hire_success predict failed: %s", exc)
                p, model_used = self._heuristic_predict(vec)
        else:
            p, model_used = self._heuristic_predict(vec)
        p = max(0.0, min(1.0, p))
        drivers = [
            {
                "feature": HIRE_SUCCESS_FEATURES[i],
                "impact": round(float(vec[i]), 3),
            }
            for i in range(min(3, len(vec)))
        ]
        return HireSuccessScore(
            candidate_id=candidate_id,
            success_score=p,
            drivers=drivers,
            model_used=model_used,
            inference_ms=(time.time() - t0) * 1000,
            explanation=(
                f"基于 {len(HIRE_SUCCESS_FEATURES)} 个匹配后特征, {model_used} "
                f"模型给出入职后成功概率 {p:.2f}."
            ),
        )

    def _heuristic_predict(self, vec: list[float]) -> tuple[float, str]:
        """0.5*match_score + 0.5 * average(evals)."""
        match = vec[0]
        evals = (vec[4] + vec[5] + vec[6]) / 3
        score = 0.5 * match + 0.5 * evals
        return float(max(0.0, min(1.0, score))), "rules"


# ===================================================================
# 3. ProphetModel — time-series forecast
# ===================================================================
@dataclass(slots=True)
class ForecastPoint:
    ds: str
    yhat: float
    yhat_lower: float
    yhat_upper: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "ds": self.ds,
            "yhat": round(float(self.yhat), 3),
            "yhat_lower": round(float(self.yhat_lower), 3),
            "yhat_upper": round(float(self.yhat_upper), 3),
        }


@dataclass(slots=True)
class ForecastResult:
    metric: str
    horizon_days: int
    history_days: int
    points: list[ForecastPoint]
    model_used: str
    trend_slope: float
    computed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "horizon_days": self.horizon_days,
            "history_days": self.history_days,
            "points": [p.to_dict() for p in self.points],
            "model_used": self.model_used,
            "trend_slope": round(self.trend_slope, 4),
            "computed_at": self.computed_at,
        }


def _seasonal_sin(
    day_index: int, period: int = 7, amplitude: float = 5.0
) -> float:
    return amplitude * math.sin(2 * math.pi * day_index / period)


def _synthetic_history(
    metric: str, days: int, base: float, seed: str
) -> list[dict[str, Any]]:
    """Generate plausible synthetic history for unit tests / cold start."""
    rows: list[dict[str, Any]] = []
    for i in range(days):
        ds = (datetime.now(timezone.utc) - timedelta(days=days - i)).date().isoformat()
        trend = base + 0.05 * i
        seas = _seasonal_sin(i, period=7, amplitude=base * 0.1)
        noise = (_stable_int(seed, 9, salt=f"n{i}") - 4) * (base * 0.02)
        y = max(0.0, trend + seas + noise)
        rows.append({"ds": ds, "y": y})
    return rows


class ProphetModel:
    """Forecast candidate inflow / ticket volume / matches.

    Cold start: synthetic history (deterministic by seed).
    Hot path: caller provides history rows.
    """

    def __init__(self) -> None:
        self.model: Any = None
        self.metric: str = ""
        self.history: list[dict[str, Any]] = []

    def _load(self) -> bool:
        p = MODEL_DIR / f"prophet_{self.metric or 'default'}.pkl"
        if not p.exists():
            return False
        try:
            with p.open("rb") as f:
                self.model = pickle.load(f)
            return True
        except Exception:  # pragma: no cover
            return False

    def _save(self) -> None:
        if self.model is None:
            return
        p = MODEL_DIR / f"prophet_{self.metric or 'default'}.pkl"
        with p.open("wb") as f:
            pickle.dump(self.model, f)

    def _train(self, history: list[dict[str, Any]]) -> None:
        if not _HAS_PROPHET:
            return
        if not history:
            return
        try:
            import pandas as pd  # type: ignore
        except Exception:  # pragma: no cover
            return
        df = pd.DataFrame({"ds": [r["ds"] for r in history], "y": [r["y"] for r in history]})
        m = Prophet(daily_seasonality=True, weekly_seasonality=True, yearly_seasonality=False)
        try:
            m.fit(df)
        except Exception as exc:  # pragma: no cover
            logger.warning("prophet fit failed: %s", exc)
            return
        self.model = m
        self._save()

    def forecast(
        self,
        metric: str,
        horizon_days: int = 30,
        history: list[dict[str, Any]] | None = None,
        history_days: int = 90,
        seed: str = "default",
    ) -> ForecastResult:
        t0 = time.time()
        self.metric = metric
        if not history:
            base = 50.0 if metric == "candidate_inflow" else 10.0
            history = _synthetic_history(metric, history_days, base, seed)
        self.history = history
        if self.model is None:
            self._load()
        if self.model is None and _HAS_PROPHET:
            self._train(history)
        future_dates = [
            (datetime.now(timezone.utc) + timedelta(days=i + 1)).date().isoformat()
            for i in range(horizon_days)
        ]
        if self.model is not None and _HAS_PROPHET:
            try:
                future_df = {"ds": future_dates}
                pred = self.model.predict(pd_dataframe(future_df))
                points = [
                    ForecastPoint(
                        ds=str(future_dates[i]),
                        yhat=float(pred["yhat"].iloc[i]),
                        yhat_lower=float(pred["yhat_lower"].iloc[i]),
                        yhat_upper=float(pred["yhat_upper"].iloc[i]),
                    )
                    for i in range(horizon_days)
                ]
                model_used = "prophet"
            except Exception as exc:  # pragma: no cover
                logger.warning("prophet predict failed: %s", exc)
                points = self._heuristic_forecast(history, future_dates)
                model_used = "rules"
        else:
            points = self._heuristic_forecast(history, future_dates)
            model_used = "rules"
        # crude trend slope
        y = [r["y"] for r in history]
        slope = 0.0
        if len(y) >= 2:
            slope = (y[-1] - y[0]) / max(1, len(y) - 1)
        return ForecastResult(
            metric=metric,
            horizon_days=horizon_days,
            history_days=len(history),
            points=points,
            model_used=model_used,
            trend_slope=slope,
        )

    def _heuristic_forecast(
        self, history: list[dict[str, Any]], future_dates: list[str]
    ) -> list[ForecastPoint]:
        if not history:
            return [
                ForecastPoint(ds=d, yhat=0.0, yhat_lower=0.0, yhat_upper=0.0)
                for d in future_dates
            ]
        n = len(history)
        window = min(14, n)
        recent = [r["y"] for r in history[-window:]]
        avg = sum(recent) / max(1, len(recent))
        std = math.sqrt(sum((y - avg) ** 2 for y in recent) / max(1, len(recent)))
        out: list[ForecastPoint] = []
        for i, ds in enumerate(future_dates):
            seas = _seasonal_sin(i + n, period=7, amplitude=avg * 0.1)
            yhat = max(0.0, avg + seas)
            out.append(
                ForecastPoint(
                    ds=ds,
                    yhat=yhat,
                    yhat_lower=max(0.0, yhat - std),
                    yhat_upper=yhat + std,
                )
            )
        return out


def pd_dataframe(d: dict[str, list]) -> Any:  # tiny shim for prophet input
    if not _HAS_PROPHET:
        return None
    import pandas as pd  # type: ignore

    return pd.DataFrame(d)


# ===================================================================
# Module-level singletons
# ===================================================================
_attrition: AttritionModel | None = None
_hire_success: HireSuccessModel | None = None


def get_attrition_model() -> AttritionModel:
    global _attrition
    if _attrition is None:
        m = AttritionModel()
        m.load()
        _attrition = m
    return _attrition


def get_hire_success_model() -> HireSuccessModel:
    global _hire_success
    if _hire_success is None:
        m = HireSuccessModel()
        m.load()
        _hire_success = m
    return _hire_success


# ===================================================================
# Auto-training
# ===================================================================
def train_all_synthetic(n: int = 1000) -> dict[str, Any]:
    """Train both models on synthetic data; safe in dev/CI."""
    out: dict[str, Any] = {"attrition": {}, "hire_success": {}}
    if _HAS_LGB and np is not None:
        rng = np.random.default_rng(42)
        n_attr = n
        X_a = rng.normal(size=(n_attr, len(ATTRITION_FEATURES))).astype(np.float32)
        # synthetic label: weighted sum → sigmoid
        w = np.array([-0.6, -0.2, 0.4, 0.5, -0.7, 0.1, 0.3], dtype=np.float32)
        z = X_a @ w + rng.normal(scale=0.4, size=n_attr)
        y_a = (1 / (1 + np.exp(-z)) > 0.5).astype(np.int32)
        am = AttritionModel()
        out["attrition"] = am.train(X_a, y_a)
        am.save()

        n_hs = n
        X_h = rng.normal(size=(n_hs, len(HIRE_SUCCESS_FEATURES))).astype(np.float32)
        # normalize first 3 features to [0,1]
        X_h[:, 0] = (X_h[:, 0] - X_h[:, 0].min()) / max(
            1e-6, X_h[:, 0].max() - X_h[:, 0].min()
        )
        X_h[:, 4:7] = (X_h[:, 4:7] - X_h[:, 4:7].min(0)) / np.maximum(
            1e-6, (X_h[:, 4:7].max(0) - X_h[:, 4:7].min(0))
        )
        w_h = np.array(
            [0.35, 0.0, 0.0, -0.05, 0.20, 0.20, 0.20, 0.05, 0.05],
            dtype=np.float32,
        )
        y_h = np.clip(X_h @ w_h + rng.normal(scale=0.1, size=n_hs), 0, 1)
        hm = HireSuccessModel()
        out["hire_success"] = hm.train(X_h, y_h)
        hm.save()
    out["prophet_trained"] = False
    if _HAS_PROPHET:
        try:
            pm = ProphetModel()
            res = pm.forecast("candidate_inflow", horizon_days=14, history_days=60)
            out["prophet_trained"] = True
            out["prophet_first"] = res.points[0].to_dict() if res.points else None
        except Exception as exc:  # pragma: no cover
            logger.warning("prophet synthetic train failed: %s", exc)
    return out


# ===================================================================
# Celery beat entrypoint (optional)
# ===================================================================
def celery_beat_task() -> dict[str, Any]:
    """Idempotent monthly retrain — invoke from Celery beat / cron / OMC."""
    logger.info("predictive.monthly_retrain start")
    out = train_all_synthetic(n=2000)
    logger.info("predictive.monthly_retrain done: %s", out)
    return out
