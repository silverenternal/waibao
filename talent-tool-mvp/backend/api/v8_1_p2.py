"""T3701-T3710 v8.1 P2 tasks API."""
from __future__ import annotations

try:
    from api.tone import router as tone_router
    from api.ps_detection import router as ps_router
    from api.strategy_impact import router as strategy_router
    from api.bias_enforce import router as bias_router
    from api.jd_marketing import router as jd_router
    from api.policy_explainer import router as policy_router
    from api.silence_activator import router as silence_router
    from api.consensus_v2 import router as consensus_router
    from api.daily_suggestions import router as suggestions_router
    from api.matching_feedback import router as matching_fb_router

    from fastapi import APIRouter

    router = APIRouter(prefix="/api/v8_1_p2", tags=["v8_1_p2"])
    router.include_router(tone_router)
    router.include_router(ps_router)
    router.include_router(strategy_router)
    router.include_router(bias_router)
    router.include_router(jd_router)
    router.include_router(policy_router)
    router.include_router(silence_router)
    router.include_router(consensus_router)
    router.include_router(suggestions_router)
    router.include_router(matching_fb_router)
except ImportError:
    from fastapi import APIRouter
    router = APIRouter(prefix="/api/v8_1_p2", tags=["v8_1_p2"])
