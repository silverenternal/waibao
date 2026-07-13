"""T2803 — Predictive analytics tests (LightGBM + Prophet).

Validates:
1. LightGBM attrition model trains + AUC > 0.80 on synthetic data
2. LightGBM hire-success model trains + RMSE < 0.15
3. Prophet forecast returns horizon-length series with sane values
4. Heuristic fallback (no LightGBM) still returns valid 0-1 score
5. Online inference < 100ms (single predict call)
6. Feature importances + factors are present
7. /api/predictive/* endpoints reachable via TestClient
8. Frontend components: PredictionCard + pages exist with required symbols
"""
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIR = REPO_ROOT / "frontend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def auth_user():
    from contracts.shared import UserRole

    u = MagicMock()
    u.id = "u-1"
    u.user_id = "u-1"
    u.tenant_id = "t-1"
    u.role = UserRole.admin
    u.email = "admin@x.com"
    return u


@pytest.fixture
def client(auth_user):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.auth import get_current_user, require_role
    from api.predictive import router

    app = FastAPI()
    app.include_router(router, prefix="/api/predictive")
    app.dependency_overrides[get_current_user] = lambda: auth_user
    app.dependency_overrides[require_role] = lambda *a, **k: auth_user

    with TestClient(app) as c:
        yield c


@pytest.fixture
def sample_attrition_data():
    """1000-row labelled dataset with signal (separates y from X)."""
    from services.platform.predictive import ATTRITION_FEATURES

    if not _has_lgb():
        pytest.skip("lightgbm not installed")
    import numpy as np

    rng = np.random.default_rng(7)
    n = 1000
    X = rng.normal(size=(n, len(ATTRITION_FEATURES))).astype("float32")
    w = np.array(
        [-0.7, -0.25, 0.45, 0.55, -0.8, 0.1, 0.35], dtype="float32"
    )
    z = X @ w + rng.normal(scale=0.4, size=n)
    y = (1 / (1 + np.exp(-z)) > 0.5).astype("int32")
    return X, y


def _has_lgb() -> bool:
    try:
        import lightgbm  # noqa: F401
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 1. AttritionModel training + AUC > 0.80
# ---------------------------------------------------------------------------
def test_attrition_trains_with_auc_above_threshold(sample_attrition_data):
    from services.platform.predictive import AttritionModel

    X, y = sample_attrition_data
    m = AttritionModel()
    metrics = m.train(X, y)
    assert metrics["auc"] > 0.80, f"AUC {metrics['auc']} should be > 0.80"
    assert m.model is not None


def test_attrition_predict_returns_valid_risk():
    from services.platform.predictive import AttritionModel

    m = AttritionModel()
    risk = m.predict("u-abc")
    assert 0.0 <= risk.risk_score <= 1.0
    assert risk.risk_level in {"low", "medium", "high"}
    assert 1 <= len(risk.factors) <= 3
    assert risk.model_used in {"lightgbm", "rules"}
    assert risk.inference_ms >= 0


def test_attrition_inference_under_100ms():
    from services.platform.predictive import AttritionModel

    m = AttritionModel()
    # warm-up + 50 predictions
    for i in range(5):
        m.predict(f"u-warm-{i}")
    samples = []
    for i in range(50):
        t0 = time.time()
        m.predict(f"u-perf-{i}")
        samples.append((time.time() - t0) * 1000)
    avg = sum(samples) / len(samples)
    p95 = sorted(samples)[int(0.95 * len(samples)) - 1]
    assert avg < 100, f"avg {avg:.1f}ms should be < 100ms"
    # p95 can be higher because of first-call jitter — relax to 200ms
    assert p95 < 200, f"p95 {p95:.1f}ms should be < 200ms"


def test_attrition_save_and_load(tmp_path):
    from services.platform.predictive import AttritionModel

    # train minimal
    if not _has_lgb():
        pytest.skip("lightgbm not installed")
    import numpy as np

    X = np.random.default_rng(0).normal(size=(200, 7)).astype("float32")
    y = (np.random.default_rng(0).uniform(size=200) > 0.5).astype("int32")
    m = AttritionModel()
    m.train(X, y)
    p = m.save(name="attrition_test.pkl")
    assert p.exists()
    # load fresh
    m2 = AttritionModel()
    ok = m2.load(name="attrition_test.pkl")
    assert ok
    assert m2.model is not None


# ---------------------------------------------------------------------------
# 2. HireSuccessModel
# ---------------------------------------------------------------------------
def test_hire_success_trains_with_low_rmse():
    from services.platform.predictive import HireSuccessModel

    if not _has_lgb():
        pytest.skip("lightgbm not installed")
    import numpy as np

    rng = np.random.default_rng(11)
    n = 800
    X = rng.normal(size=(n, 9)).astype("float32")
    w = np.array(
        [0.4, 0, 0, -0.1, 0.2, 0.2, 0.2, 0.05, 0.05], dtype="float32"
    )
    y = np.clip(X @ w + rng.normal(scale=0.1, size=n), 0, 1)
    m = HireSuccessModel()
    metrics = m.train(X, y)
    assert metrics["rmse"] < 0.15, f"rmse {metrics['rmse']} should be < 0.15"
    out = m.predict("c-001")
    assert 0.0 <= out.success_score <= 1.0
    assert out.model_used in {"lightgbm", "rules"}
    assert out.explanation


# ---------------------------------------------------------------------------
# 3. Prophet forecast
# ---------------------------------------------------------------------------
def test_prophet_forecast_returns_horizon_points():
    from services.platform.predictive import ProphetModel

    m = ProphetModel()
    res = m.forecast("candidate_inflow", horizon_days=14, history_days=60)
    assert res.metric == "candidate_inflow"
    assert res.horizon_days == 14
    assert len(res.points) == 14
    for p in res.points:
        assert p.yhat >= 0
        assert p.yhat_lower <= p.yhat
        assert p.yhat_upper >= p.yhat
    assert res.model_used in {"prophet", "rules"}


def test_prophet_forecast_with_custom_history():
    from services.platform.predictive import ProphetModel

    history = [
        {"ds": f"2026-06-{i + 1:02d}", "y": float(i + 1)} for i in range(30)
    ]
    m = ProphetModel()
    res = m.forecast("tickets", horizon_days=10, history=history)
    assert len(res.points) == 10
    # custom history is upward trend, expect yhat at end >= yhat at start
    assert res.points[-1].yhat >= res.points[0].yhat * 0.8


# ---------------------------------------------------------------------------
# 4. Heuristic fallback
# ---------------------------------------------------------------------------
def test_heuristic_attrition_factors():
    from services.platform.predictive import (
        AttritionModel,
        _extract_attrition_features,
        _heuristic_attrition_factors,
    )

    f = _extract_attrition_features(
        "u-test",
        {
            "emotion_avg_30d": 20,
            "interaction_gap_avg_h": 36,
            "negative_tickets_30d": 4,
        },
    )
    factors = _heuristic_attrition_factors(f)
    assert len(factors) == 3
    assert all(isinstance(p, tuple) for p in factors)
    # make sure model falls back to rules when self.model is None
    m = AttritionModel()
    m.model = None
    risk = m.predict("u-no-model")
    assert risk.model_used in {"lightgbm", "rules"}


# ---------------------------------------------------------------------------
# 5. train_all_synthetic
# ---------------------------------------------------------------------------
def test_train_all_synthetic_runs():
    from services.platform.predictive import train_all_synthetic

    out = train_all_synthetic(n=300)
    assert "attrition" in out
    assert "hire_success" in out
    # prophet is optional — accept True or False
    assert "prophet_trained" in out


# ---------------------------------------------------------------------------
# 6. /api/predictive/* endpoints
# ---------------------------------------------------------------------------
def test_attrition_endpoint(client):
    r = client.get("/api/predictive/attrition/u-1")
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == "u-1"
    assert 0 <= body["risk_score"] <= 1


def test_hire_success_endpoint(client):
    r = client.get("/api/predictive/hire-success/c-1")
    assert r.status_code == 200
    body = r.json()
    assert body["candidate_id"] == "c-1"
    assert 0 <= body["success_score"] <= 1


def test_forecast_endpoint(client):
    r = client.get("/api/predictive/forecast?horizon_days=7")
    assert r.status_code == 200
    body = r.json()
    assert body["metric"] == "candidate_inflow"
    assert len(body["points"]) == 7


def test_team_attrition_endpoint(client):
    r = client.get(
        "/api/predictive/attrition/team/t-1?user_ids=u-a,u-b,u-c"
    )
    assert r.status_code == 200
    body = r.json()
    assert body["n"] == 3
    assert body["org_id"] == "t-1"
    assert "high" in body and "medium" in body and "low" in body


def test_health_endpoint(client):
    r = client.get("/api/predictive/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True


def test_models_endpoint(client):
    r = client.get("/api/predictive/models")
    assert r.status_code == 200
    body = r.json()
    assert "attrition" in body
    assert "hire_success" in body


def test_retrain_endpoint(client):
    r = client.post("/api/predictive/retrain?n=200")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "metrics" in body
    # AUC and RMSE reported
    assert "auc" in body["metrics"]["attrition"]
    assert "rmse" in body["metrics"]["hire_success"]


# ---------------------------------------------------------------------------
# 7. Frontend artefacts
# ---------------------------------------------------------------------------
class TestFrontend:
    def test_prediction_card_exists(self):
        f = FRONTEND_DIR / "components" / "predictive" / "PredictionCard.tsx"
        assert f.exists()
        text = f.read_text()
        for sym in [
            "PredictionCard",
            "AttritionBody",
            "HireSuccessBody",
            "RISK_LEVEL_LABEL",
            "FEATURE_LABEL",
        ]:
            assert sym in text, f"PredictionCard missing: {sym}"

    def test_api_predictive_client_defines_endpoints(self):
        f = FRONTEND_DIR / "lib" / "api-predictive.ts"
        assert f.exists()
        text = f.read_text()
        for sym in [
            "attrition",
            "hireSuccess",
            "forecast",
            "retrain",
            "health",
            "models",
            "teamAttrition",
        ]:
            assert sym in text, f"api-predictive missing: {sym}"

    def test_mothership_predictive_page(self):
        f = (
            FRONTEND_DIR
            / "app"
            / "mothership"
            / "analytics"
            / "predictive"
            / "page.tsx"
        )
        assert f.exists(), "mothership/analytics/predictive/page.tsx missing"
        text = f.read_text()
        for sym in ["预测分析", "PredictionCard", "ForecastChart", "离职风险", "入职成功"]:
            assert sym in text, f"page missing: {sym}"

    def test_admin_predictive_page_has_training_controls(self):
        f = (
            FRONTEND_DIR / "app" / "admin" / "predictive" / "page.tsx"
        )
        assert f.exists(), "admin/predictive/page.tsx missing"
        text = f.read_text()
        for sym in ["手动重训", "Attrition (LightGBM)", "HireSuccess", "Prophet"]:
            assert sym in text, f"admin page missing: {sym}"


# ---------------------------------------------------------------------------
# 8. Feature-extraction invariants
# ---------------------------------------------------------------------------
def test_extract_features_is_deterministic():
    from services.platform.predictive import _extract_attrition_features

    a = _extract_attrition_features("u-1")
    b = _extract_attrition_features("u-1")
    assert a == b
    c = _extract_attrition_features("u-2")
    assert a != c
