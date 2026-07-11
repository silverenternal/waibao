from contextlib import asynccontextmanager
import logging
import time
import uuid

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("recruittech")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("RecruitTech API starting up")
    from adapters.registry import init_adapters
    init_adapters()

    # 注册所有 16 个 Agent (P0 基础设施)
    from api.deps import get_supabase_admin
    from agents.boot import init_all_agents
    try:
        init_all_agents(supabase=get_supabase_admin())
    except Exception as e:
        logger.warning(f"init_all_agents failed: {e}")

    yield
    logger.info("RecruitTech API shutting down")


# T1001/T1003: 初始化 OpenTelemetry 与 Sentry (在 app 构造前)
try:
    from services.telemetry import init_telemetry

    init_telemetry(service_name="waibao-backend")
except Exception as e:  # noqa: BLE001
    logger.warning(f"init_telemetry skipped: {e}")

try:
    from services.sentry import init_sentry

    init_sentry()
except Exception as e:  # noqa: BLE001
    logger.warning(f"init_sentry skipped: {e}")


app = FastAPI(
    title="RecruitTech API",
    description="Recruitment platform backend — Mothership engine",
    version="0.1.0",
    lifespan=lifespan,
)

# T1001: 挂载 OTel FastAPI instrumentation (依赖缺失则静默跳过)
try:
    from services.telemetry import instrument_app as _otel_instrument_app

    _otel_instrument_app(app)
except Exception as e:  # noqa: BLE001
    logger.warning(f"otel instrument_app skipped: {e}")

# T1002: Prometheus /metrics 端点
try:
    from services.metrics import metrics_asgi_app

    _metrics_app = metrics_asgi_app()
    if _metrics_app is not None:
        app.mount("/metrics", _metrics_app)
        logger.info("metrics endpoint mounted at /metrics")
except Exception as e:  # noqa: BLE001
    logger.warning(f"metrics mount skipped: {e}")

# CORS — allow frontend origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- Request Logging Middleware ----

@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    logger.info(
        f"[{request_id}] {request.method} {request.url.path} started"
    )

    response = await call_next(request)

    duration_ms = (time.time() - start_time) * 1000
    logger.info(
        f"[{request_id}] {request.method} {request.url.path} "
        f"completed {response.status_code} in {duration_ms:.1f}ms"
    )

    response.headers["X-Request-ID"] = request_id
    return response


# ---- Global Exception Handlers ----

@app.exception_handler(422)
async def validation_error_handler(request: Request, exc):
    return JSONResponse(
        status_code=422,
        content={"detail": "Validation error", "path": request.url.path},
    )


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return JSONResponse(
        status_code=404,
        content={"detail": "Resource not found", "path": request.url.path},
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    logger.error(f"Internal error on {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# ---- Health Check ----

@app.get("/health", tags=["system"])
@app.get("/api/health", tags=["system"], include_in_schema=False)
async def health_check():
    """Health check endpoint. Returns 200 if API is running."""
    return {
        "status": "healthy",
        "service": "recruittech-api",
        "version": "0.1.0",
    }



# ---- Users/Me ----

from api.auth import get_current_user as _get_current_user
from api.auth import CurrentUser as _CurrentUser


@app.get("/api/users/me", tags=["users"])
async def get_me(user: _CurrentUser = Depends(_get_current_user)):
    """Get the current authenticated user's profile."""
    try:
        from api.deps import get_supabase_admin
        supabase = get_supabase_admin()
        result = supabase.table("users").select("*").eq("id", str(user.id)).single().execute()
        if result.data:
            return result.data
    except Exception:
        pass
    # Fallback: return what we know from the JWT
    return {
        "id": str(user.id),
        "email": user.email,
        "first_name": user.email.split("@")[0].split(".")[0].title(),
        "last_name": "",
        "role": user.role.value,
        "organisation_id": None,
        "is_active": True,
    }


# ---- Router Includes ----

from api.candidates import router as candidates_router
from api.roles import router as roles_router
from api.matches import router as matches_router
from api.collections import router as collections_router
from api.handoffs import router as handoffs_router
from api.quotes import router as quotes_router
from api.copilot import router as copilot_router
from api.signals import router as signals_router
from api.admin import router as admin_router

# === 招聘智能体扩展 API (todo.json P0-P3) ===
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
from api.career_plan import router as career_plan_router
from api.clarification import router as clarification_router
from api.uploads import get_current_user as uploads_get_current_user  # noqa: F401
from api.uploads import router as uploads_router  # noqa: F401  (OCR 文件上传)

app.include_router(candidates_router, prefix="/api/candidates", tags=["candidates"])
app.include_router(roles_router, prefix="/api/roles", tags=["roles"])
app.include_router(matches_router, prefix="/api/matches", tags=["matches"])
app.include_router(collections_router, prefix="/api/collections", tags=["collections"])
app.include_router(handoffs_router, prefix="/api/handoffs", tags=["handoffs"])
app.include_router(quotes_router, prefix="/api/quotes", tags=["quotes"])
app.include_router(copilot_router, prefix="/api/copilot", tags=["copilot"])
app.include_router(signals_router, prefix="/api/signals", tags=["signals"])
app.include_router(admin_router, prefix="/api/admin", tags=["admin"])

# 智能体扩展路由
app.include_router(realtime_router, prefix="/api/realtime", tags=["agents-realtime"])
app.include_router(journal_router, prefix="/api/journal", tags=["agents-journal"])
app.include_router(emotion_router, prefix="/api/emotion", tags=["agents-emotion"])
app.include_router(vision_router, prefix="/api/vision", tags=["agents-vision"])
app.include_router(talent_brief_router, prefix="/api/talent-brief", tags=["agents-brief"])
app.include_router(job_spec_router, prefix="/api/job-spec", tags=["agents-spec"])
app.include_router(policy_api_router, prefix="/api/policy", tags=["agents-policy"])
app.include_router(jd_templates_router, prefix="/api/jd-templates", tags=["agents-jd-templates"])
app.include_router(action_items_router, prefix="/api/action-items", tags=["agents-action-items"])
app.include_router(multiparty_router, prefix="/api/multiparty", tags=["agents-multi"])
app.include_router(compliance_api_router, prefix="/api/compliance", tags=["agents-compliance"])
# T103: compliance enhancement (expiry alerts + quick assess)
app.include_router(compliance_router, prefix="/api/compliance", tags=["agents-compliance"])
app.include_router(career_plan_router, prefix="/api/career-plan", tags=["agents-plan"])
# T607: learning resources + plan tracker
from api.learning import router as learning_router
from api.plan_tracker import router as plan_tracker_router
app.include_router(learning_router, prefix="/api/learning", tags=["agents-learning"])
app.include_router(plan_tracker_router, prefix="/api/plan", tags=["agents-plan-tracker"])
app.include_router(clarification_router, prefix="/api/clarification", tags=["agents-clarify"])
app.include_router(uploads_router, prefix="/api/uploads", tags=["uploads"])

# Production wiring: replace uploads' placeholder auth dep with the real one
from api.auth import get_current_user as _auth_get_current_user

app.dependency_overrides[uploads_get_current_user] = _auth_get_current_user
app.include_router(two_way_match_router, prefix="/api/two-way-match", tags=["matching"])
app.include_router(evaluation_router, prefix="/api/evaluation", tags=["matching"])

# T901: matching 2.0 — explainability (reasons / weak_points / counterfactual)
from api.match_explain import router as match_explain_router
app.include_router(match_explain_router, prefix="/api/match", tags=["matching-explain"])

# T902: matching 2.0 — mutual evaluation comparison view
from api.match_eval import router as match_eval_router
app.include_router(match_eval_router, prefix="/api/match/eval", tags=["matching-eval"])

# T903: matching 2.0 — admin weight tuning + matching quality dashboard
from api.admin_weights import router as admin_weights_router
from api.admin_matching_quality import router as admin_matching_quality_router
app.include_router(admin_weights_router, prefix="/api/admin/weights", tags=["admin-weights"])
app.include_router(
    admin_matching_quality_router,
    prefix="/api/admin/matching-quality",
    tags=["admin-matching-quality"],
)
app.include_router(gdpr_router, prefix="/api/gdpr", tags=["compliance"])

# T104: admin notify (channel configuration + user prefs)
from api.admin_notify import router as admin_notify_router
app.include_router(admin_notify_router, prefix="/api/admin/notify", tags=["admin-notify"])

# T207: HR ticket system
from api.tickets import router as tickets_router
app.include_router(tickets_router, prefix="/api/tickets", tags=["tickets"])

# T608: Multi-party collaboration rooms (5 方实时协同)
from api.rooms import router as rooms_router
app.include_router(rooms_router, prefix="/api/rooms", tags=["rooms"])

# T701: Voice journal (Whisper STT)
from api.voice import router as voice_router
app.include_router(voice_router, prefix="/api/voice", tags=["agents-voice"])

# T704: Escalation API
from api.escalation import router as escalation_router
app.include_router(escalation_router, prefix="/api/escalation", tags=["agents-escalation"])

# T802: Webhook subscription + dispatch
from api.webhooks import router as webhooks_router
app.include_router(webhooks_router, prefix="", tags=["webhooks"])

# T803: API Key admin (mothership 内部) + Public API (第三方)
from api.admin_api_keys import router as admin_api_keys_router
from api.public import router as public_router

app.include_router(admin_api_keys_router, prefix="", tags=["admin-api-keys"])
app.include_router(public_router, prefix="", tags=["public-api"])

# T804: Rule engine CRUD + tester
from api.rules import router as rules_router

app.include_router(rules_router, prefix="", tags=["rules"])

# T805: A/B experiment management + results + significance
from api.admin_ab import router as admin_ab_router

app.include_router(admin_ab_router, prefix="/api/admin/ab", tags=["admin-ab"])

# T806: Cost dashboard + cache stats
from api.admin_cost import router as admin_cost_router

app.include_router(admin_cost_router, prefix="/api/admin/cost", tags=["admin-cost"])

# T1004: Audit log (admin-only)
from api.admin_audit import router as admin_audit_router

app.include_router(admin_audit_router, prefix="/api/admin/audit", tags=["admin-audit"])
