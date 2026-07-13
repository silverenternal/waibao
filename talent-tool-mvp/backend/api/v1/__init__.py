"""API v1 canonical router — T2904.

Exposes the same endpoints that exist under ``api/*.py`` today but
mounted under ``/api/v1/*``.  We collect the routers lazily so that a
single ``import`` of this package picks up everything in the original
`api/` namespace without duplication.

Each entry is added in the order it historically landed; the
deprecated middleware (set up by ``api.versioning``) will add the
RFC 8594 Sunset + Deprecation headers automatically.
"""
from __future__ import annotations

from fastapi import APIRouter

# Order matters: keep names stable so the OpenAPI tag order is
# reproducible across builds.
from api.candidates import router as candidates_router
from api.roles import router as roles_router
from api.matches import router as matches_router
from api.collections import router as collections_router
from api.handoffs import router as handoffs_router
from api.quotes import router as quotes_router
from api.copilot import router as copilot_router
from api.signals import router as signals_router
from api.admin import router as admin_router
from api.realtime import router as realtime_router
from api.two_way_match import router as two_way_match_router
from api.evaluation import router as evaluation_router
from api.gdpr import router as gdpr_router
from api.journal import router as journal_router
from api.emotion import router as emotion_router
from api.vision import router as vision_router
from api.talent_brief import router as talent_brief_router
from api.job_spec import router as job_spec_router
from api.policy_api import router as policy_api_router
from api.jd_templates import router as jd_templates_router
from api.action_items import router as action_items_router
from api.multiparty import router as multiparty_router
from api.compliance_api import router as compliance_api_router
from api.compliance import router as compliance_router
from api.analytics.cross_platform import router as analytics_router
from api.events_stream import router as events_stream_router
from api.workflows import router as workflows_router
from api.legal import router as legal_router
from api.tickets import router as tickets_router
from api.notification_prefs import router as notifications_router  # T2304 prefs
from api.push import router as push_router
from api.feedback import router as feedback_router
from api.webhooks import router as webhooks_router
from api.search import router as search_router
from api.exports import router as exports_router
from api.batch import router as batch_router
from api.ai_interview import router as ai_interview_router

# v8.1: WeChat mini-program + SSO auth — must be exposed under /api/v1 so
# the legacy /api/auth/* -> /api/v1/auth/* redirect can find a handler.
from api.miniprogram_auth import router as miniprogram_auth_router
from api.auth_sso import router as auth_sso_router
from api.developer_portal import router as developer_portal_router

# Synthetic v1 router that re-exports everything with the ``/api/v1`` prefix
# applied by ``api.versioning.install_versioning``.
router: list[APIRouter] = [
    candidates_router,
    roles_router,
    matches_router,
    collections_router,
    handoffs_router,
    quotes_router,
    copilot_router,
    signals_router,
    admin_router,
    realtime_router,
    two_way_match_router,
    evaluation_router,
    gdpr_router,
    journal_router,
    emotion_router,
    vision_router,
    talent_brief_router,
    job_spec_router,
    policy_api_router,
    jd_templates_router,
    action_items_router,
    multiparty_router,
    compliance_api_router,
    compliance_router,
    analytics_router,
    events_stream_router,
    workflows_router,
    legal_router,
    tickets_router,
    notifications_router,
    push_router,
    feedback_router,
    webhooks_router,
    search_router,
    exports_router,
    batch_router,
    ai_interview_router,
    miniprogram_auth_router,
    auth_sso_router,
    developer_portal_router,
]

__all__ = ["router"]
