"""v8.0 T3501 — Service Registry: auto-discover + bulk register.

Scans the workspace directories listed below for any sub-package that
represents an addressable capability (an agent, an API router, a service
module, a frontend page). For each one we synthesize a Service record and
register it through ``service_toggle``.

The registry is deliberately *declarative* — every entry is a single dict
that names the service, its display text, category, default plan and the
set of roles permitted to invoke it. Keep this file in sync with the
catalog whenever a new capability ships.

Coverage (target: 50+ services):
    * 16 agents
    *  5 frontend surfaces
    *  7 business modules
    * 22+ platform / API / integration / analytics services
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .service_catalog import (
    PlanTier,
    Service,
    ServiceCategory,
    ServiceStatus,
)
from .service_toggle import service_toggle

logger = logging.getLogger("recruittech.platform.service_registry")


# ---------------------------------------------------------------------------
# v11.4 R3 — Deployment profile gating (service-catalog hygiene)
# ---------------------------------------------------------------------------
# The full catalog intentionally advertises the SaaS product surface (BI,
# data warehouse, multi-agent crews, LiveKit realtime voice, RAG, LoRA
# fine-tuning, AI sourcing, developer portal, ...). None of those are part
# of the on-prem / local deliverable, and the local stack ships NO backing
# services for them (no ClickHouse / Cube / LiveKit / Qdrant / LLaMA-Factory).
#
# Leaving them registered as ``enabled`` pollutes the admin service catalog
# and the public ``/api/public/services`` listing the customer sees during
# acceptance, and makes it look like the platform depends on infra that is
# not actually present. We therefore default them to ``disabled`` whenever
# the process is running under a *local* deployment profile, while keeping
# every service record in place (so counts / categories / the 16 agents all
# stay intact and the existing catalog tests are unaffected).
#
# A profile is considered "local" when ANY of:
#   * ``LOCAL_PROFILE`` env var is set to a truthy value (explicit opt-in)
#   * ``SUPABASE_URL`` is empty / unset (the local stack ships with it empty)
#   * ``SUPABASE_URL`` points at localhost / ``.localhost``
# Operators that want the full SaaS surface back can set ``LOCAL_PROFILE=0``.

_OVERENGINEERED_LOCAL_DISABLED = frozenset(
    {
        # Analytics / BI / warehouse — depend on ClickHouse + Cube + Airbyte
        "analytics.warehouse",
        "analytics.bi",
        "analytics.predictive",
        "analytics.sla",
        # RAG / memory / multi-agent — depend on Qdrant + Mem0 + CrewAI
        "rag.pipeline",
        "memory.unified",
        "multiagent.crew",
        # Training / sourcing — depend on LLaMA-Factory + external sourcing
        "training.lora",
        "sourcing.outbound",
        # AI interview / realtime voice — depend on LiveKit + external RT
        "api.ai_interview",
        "api.realtime",
        # ATS / SSO / external integrations — out of local scope
        "integration.ats",
        "integration.sso",
        # Developer portal / plugin SDK visualization / workflow orchestration
        "platform.developer_portal",
        "platform.plugins",
        "platform.workflows",
    }
)


def _is_local_profile() -> bool:
    """Return True when the process runs under a local / on-prem profile.

    Honors an explicit ``LOCAL_PROFILE`` override first, then falls back to
    inferring from ``SUPABASE_URL`` (empty or localhost => local stack).
    """
    explicit = (os.environ.get("LOCAL_PROFILE") or "").strip().lower()
    if explicit:
        return explicit not in {"0", "false", "no", "off", ""}
    url = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
    if not url:
        return True
    return url == "http://localhost" or url == "https://localhost" or url.endswith(".localhost")


# ---------------------------------------------------------------------------
# Declarative catalog (>=50 entries)
# Categories:
#   * agent         16  (jobseeker + employer + evaluator)
#   * frontend       5  (admin, employer, jobseeker, candidate, public)
#   * business       7  (matching, billing, rag, memory, multiagent, training, sourcing)
#   * integration    6  (ats, sso, sso/whitelabel, payment, analytics, sla)
#   * platform      10  (feature flags, configs, plugins, workflows, audit,
#                        gdpr, service_toggle, marketplace, dev_portal, ab_test)
#   * api            8  (api_v1, api_v2, webhooks, sdk, realtime, batch,
#                        events, etc.)
# ---------------------------------------------------------------------------

_CATALOG: List[Dict[str, Any]] = [
    # ----------------------- Agents (16) -----------------------------------
    {
        "name": "agent.profile",
        "display_name": "Profile Agent",
        "category": "agent",
        "plan_required": "free",
        "roles_allowed": ["jobseeker", "admin"],
        "dependencies": ["agent.intake"],
    },
    {
        "name": "agent.intake",
        "display_name": "Intake Agent",
        "category": "agent",
        "plan_required": "free",
        "roles_allowed": ["jobseeker", "admin"],
    },
    {
        "name": "agent.clarifier",
        "display_name": "Clarifier Agent",
        "category": "agent",
        "plan_required": "free",
        "roles_allowed": ["jobseeker", "employer", "admin"],
    },
    {
        "name": "agent.career_planner",
        "display_name": "Career Planner Agent",
        "category": "agent",
        "plan_required": "pro",
        "roles_allowed": ["jobseeker", "admin"],
        "dependencies": ["agent.profile"],
    },
    {
        "name": "agent.daily_journal",
        "display_name": "Daily Journal Agent",
        "category": "agent",
        "plan_required": "free",
        "roles_allowed": ["jobseeker", "admin"],
    },
    {
        "name": "agent.emotion",
        "display_name": "Emotion Agent",
        "category": "agent",
        "plan_required": "free",
        "roles_allowed": ["jobseeker", "admin"],
    },
    {
        "name": "agent.vision",
        "display_name": "Vision Agent",
        "category": "agent",
        "plan_required": "pro",
        "roles_allowed": ["employer", "admin"],
    },
    {
        "name": "agent.talent_brief",
        "display_name": "Talent Brief Agent",
        "category": "agent",
        "plan_required": "pro",
        "roles_allowed": ["employer", "admin"],
    },
    {
        "name": "agent.job_spec",
        "display_name": "Job Spec Agent",
        "category": "agent",
        "plan_required": "free",
        "roles_allowed": ["employer", "admin"],
    },
    {
        "name": "agent.policy",
        "display_name": "Policy Agent",
        "category": "agent",
        "plan_required": "enterprise",
        "roles_allowed": ["employer", "admin"],
    },
    {
        "name": "agent.persona",
        "display_name": "Persona Agent",
        "category": "agent",
        "plan_required": "pro",
        "roles_allowed": ["employer", "admin"],
    },
    {
        "name": "agent.multi_party",
        "display_name": "Multi-Party Agent",
        "category": "agent",
        "plan_required": "enterprise",
        "roles_allowed": ["employer", "admin"],
    },
    {
        "name": "agent.compliance",
        "display_name": "Compliance Agent",
        "category": "agent",
        "plan_required": "enterprise",
        "roles_allowed": ["admin", "compliance"],
    },
    {
        "name": "agent.hr_service",
        "display_name": "HR Service Agent",
        "category": "agent",
        "plan_required": "pro",
        "roles_allowed": ["employer", "admin"],
    },
    {
        "name": "agent.employer_clarifier",
        "display_name": "Employer Clarifier Agent",
        "category": "agent",
        "plan_required": "free",
        "roles_allowed": ["employer", "admin"],
    },
    {
        "name": "agent.mutual_evaluator",
        "display_name": "Mutual Evaluator",
        "category": "agent",
        "plan_required": "pro",
        "roles_allowed": ["employer", "jobseeker", "admin"],
    },
    # ----------------------- Frontend surfaces (5) -------------------------
    {
        "name": "frontend.admin",
        "display_name": "Admin Console",
        "category": "frontend",
        "plan_required": "internal",
        "roles_allowed": ["admin"],
    },
    {
        "name": "frontend.employer",
        "display_name": "Employer Dashboard",
        "category": "frontend",
        "plan_required": "free",
        "roles_allowed": ["employer", "admin"],
    },
    {
        "name": "frontend.jobseeker",
        "display_name": "Jobseeker Console",
        "category": "frontend",
        "plan_required": "free",
        "roles_allowed": ["jobseeker", "admin"],
    },
    {
        "name": "frontend.candidate_portal",
        "display_name": "Candidate Portal",
        "category": "frontend",
        "plan_required": "free",
        "roles_allowed": ["jobseeker", "admin"],
    },
    {
        "name": "frontend.public",
        "display_name": "Public Pages",
        "category": "frontend",
        "plan_required": "free",
        "roles_allowed": [],  # anonymous
    },
    # ----------------------- Business modules (7) --------------------------
    {
        "name": "matching.engine",
        "display_name": "Matching Engine",
        "category": "business",
        "plan_required": "free",
        "roles_allowed": ["employer", "jobseeker", "admin"],
    },
    {
        "name": "billing.subscription",
        "display_name": "Subscription Billing",
        "category": "business",
        "plan_required": "free",
        "roles_allowed": ["employer", "admin"],
    },
    {
        "name": "rag.pipeline",
        "display_name": "RAG Pipeline (LlamaIndex)",
        "category": "business",
        "plan_required": "pro",
        "roles_allowed": ["employer", "jobseeker", "admin"],
        "dependencies": ["platform.feature_flags"],
    },
    {
        "name": "memory.unified",
        "display_name": "Unified Memory (Mem0)",
        "category": "business",
        "plan_required": "pro",
        "roles_allowed": ["jobseeker", "admin"],
    },
    {
        "name": "multiagent.crew",
        "display_name": "Multi-Agent Crew (CrewAI)",
        "category": "business",
        "plan_required": "enterprise",
        "roles_allowed": ["employer", "admin"],
    },
    {
        "name": "training.lora",
        "display_name": "LoRA Fine-tuning",
        "category": "business",
        "plan_required": "internal",
        "roles_allowed": ["admin"],
    },
    {
        "name": "sourcing.outbound",
        "display_name": "AI Sourcing",
        "category": "business",
        "plan_required": "pro",
        "roles_allowed": ["employer", "admin"],
    },
    # ----------------------- Integrations (6) ------------------------------
    {
        "name": "integration.ats",
        "display_name": "ATS Integrations",
        "category": "integration",
        "plan_required": "pro",
        "roles_allowed": ["employer", "admin"],
    },
    {
        "name": "integration.sso",
        "display_name": "SSO / SAML",
        "category": "integration",
        "plan_required": "enterprise",
        "roles_allowed": ["admin"],
    },
    {
        "name": "integration.background_check",
        "display_name": "Background Checks (Checkr)",
        "category": "integration",
        "plan_required": "enterprise",
        "roles_allowed": ["employer", "admin"],
    },
    {
        "name": "integration.assessment",
        "display_name": "Assessments (Beisen)",
        "category": "integration",
        "plan_required": "pro",
        "roles_allowed": ["employer", "admin"],
    },
    {
        "name": "integration.video_meetings",
        "display_name": "Video Meetings (Zoom/Tencent)",
        "category": "integration",
        "plan_required": "pro",
        "roles_allowed": ["employer", "jobseeker", "admin"],
    },
    {
        "name": "integration.marketplace",
        "display_name": "Marketplace (Strapi)",
        "category": "integration",
        "plan_required": "free",
        "roles_allowed": ["admin", "partner"],
    },
    # ----------------------- Platform infra (10) ---------------------------
    {
        "name": "platform.feature_flags",
        "display_name": "Feature Flags",
        "category": "platform",
        "plan_required": "internal",
        "roles_allowed": ["admin"],
    },
    {
        "name": "platform.config_center",
        "display_name": "Config Center",
        "category": "platform",
        "plan_required": "internal",
        "roles_allowed": ["admin"],
    },
    {
        "name": "platform.plugins",
        "display_name": "Plugin SDK",
        "category": "platform",
        "plan_required": "enterprise",
        "roles_allowed": ["admin"],
    },
    {
        "name": "platform.workflows",
        "display_name": "Workflow Engine",
        "category": "platform",
        "plan_required": "enterprise",
        "roles_allowed": ["admin", "employer"],
    },
    {
        "name": "platform.audit_v2",
        "display_name": "Audit Log v2",
        "category": "platform",
        "plan_required": "internal",
        "roles_allowed": ["admin"],
    },
    {
        "name": "platform.gdpr",
        "display_name": "GDPR Center",
        "category": "platform",
        "plan_required": "internal",
        "roles_allowed": ["admin"],
    },
    {
        "name": "platform.service_toggle",
        "display_name": "Service Toggle",
        "category": "platform",
        "plan_required": "internal",
        "roles_allowed": ["admin"],
    },
    {
        "name": "platform.developer_portal",
        "display_name": "Developer Portal",
        "category": "platform",
        "plan_required": "enterprise",
        "roles_allowed": ["admin", "partner"],
    },
    {
        "name": "platform.ab_test",
        "display_name": "A/B Test Framework",
        "category": "platform",
        "plan_required": "pro",
        "roles_allowed": ["admin"],
    },
    {
        "name": "platform.service_catalog",
        "display_name": "Service Catalog (this)",
        "category": "platform",
        "plan_required": "internal",
        "roles_allowed": ["admin"],
    },
    # ----------------------- Analytics (6) ---------------------------------
    {
        "name": "analytics.funnel",
        "display_name": "Funnel Analytics",
        "category": "analytics",
        "plan_required": "pro",
        "roles_allowed": ["employer", "admin"],
    },
    {
        "name": "analytics.bi",
        "display_name": "BI (Cube.js)",
        "category": "analytics",
        "plan_required": "enterprise",
        "roles_allowed": ["employer", "admin"],
    },
    {
        "name": "analytics.predictive",
        "display_name": "Predictive Analytics",
        "category": "analytics",
        "plan_required": "enterprise",
        "roles_allowed": ["employer", "admin"],
    },
    {
        "name": "analytics.warehouse",
        "display_name": "Data Warehouse",
        "category": "analytics",
        "plan_required": "internal",
        "roles_allowed": ["admin"],
    },
    {
        "name": "analytics.sla",
        "display_name": "SLA Monitor",
        "category": "analytics",
        "plan_required": "enterprise",
        "roles_allowed": ["admin"],
    },
    {
        "name": "analytics.daily_active",
        "display_name": "Daily Active Users",
        "category": "analytics",
        "plan_required": "internal",
        "roles_allowed": ["admin"],
    },
    # ----------------------- API surface (8) -------------------------------
    {
        "name": "api.v1",
        "display_name": "Public API v1",
        "category": "api",
        "plan_required": "free",
        "roles_allowed": [],
    },
    {
        "name": "api.v2",
        "display_name": "Public API v2",
        "category": "api",
        "plan_required": "free",
        "roles_allowed": [],
    },
    {
        "name": "api.realtime",
        "display_name": "Realtime Channel",
        "category": "api",
        "plan_required": "free",
        "roles_allowed": [],
    },
    {
        "name": "api.batch",
        "display_name": "Batch Operations",
        "category": "api",
        "plan_required": "pro",
        "roles_allowed": ["employer", "admin"],
    },
    {
        "name": "api.webhooks",
        "display_name": "Outbound Webhooks",
        "category": "api",
        "plan_required": "pro",
        "roles_allowed": ["employer", "admin"],
    },
    {
        "name": "api.events",
        "display_name": "EventBus SDK",
        "category": "api",
        "plan_required": "free",
        "roles_allowed": [],
    },
    {
        "name": "api.ai_interview",
        "display_name": "AI Interview API",
        "category": "api",
        "plan_required": "pro",
        "roles_allowed": ["employer", "jobseeker", "admin"],
    },
    {
        "name": "api.copilot",
        "display_name": "Copilot API",
        "category": "api",
        "plan_required": "pro",
        "roles_allowed": ["employer", "jobseeker", "admin"],
    },
]


# ---------------------------------------------------------------------------
# Auto-discovery helpers
# ---------------------------------------------------------------------------
def _workspace_root() -> Path:
    """Best effort resolution of the monorepo root.

    Walks upward until it finds both ``backend`` and ``frontend`` dirs.
    Falls back to the import parent.
    """
    here = Path(__file__).resolve()
    cur: Optional[Path] = here
    for _ in range(8):
        cur = cur.parent if cur else None
        if cur and (cur / "backend").is_dir() and (cur / "frontend").is_dir():
            return cur
    return here.parent.parent.parent


def _scan_for_services(roots: Iterable[Path]) -> List[str]:
    """Auto-discover candidate service names by walking well-known dirs.

    We deliberately keep this shallow: any Python module under
    ``backend/agents/<name>/`` or any ``app/<name>/page.tsx`` indicates a
    capability whose name is rooted at the directory.
    """
    names: List[str] = []
    for root in roots:
        if not root.exists():
            continue
        # agent packages
        agents_dir = root / "backend" / "agents"
        if agents_dir.exists():
            for sub in sorted(agents_dir.iterdir()):
                if sub.is_dir() and sub.name not in {"tests", "__pycache__"}:
                    if any(sub.glob("*_agent.py")) or any(sub.glob("*.py")):
                        names.append(f"agent.{sub.name}")
        # api routers — one router file => one api.<name>
        api_dir = root / "backend" / "api"
        if api_dir.exists():
            for sub in sorted(api_dir.glob("*.py")):
                if sub.stem not in {"__init__", "deps", "auth"}:
                    names.append(f"api.{sub.stem}")
        # business services
        services_dir = root / "backend" / "services"
        if services_dir.exists():
            for sub in sorted(services_dir.iterdir()):
                if sub.is_dir() and sub.name not in {"__pycache__", "tests"}:
                    names.append(f"service.{sub.name}")
        # frontend top-level routes
        fe_dir = root / "frontend" / "app"
        if fe_dir.exists():
            for sub in sorted(fe_dir.iterdir()):
                if sub.is_dir() and sub.name not in {
                    "api", "login", "(employer)", "(jobseeker)", "(public)",
                    "offline",
                }:
                    names.append(f"frontend.{sub.name}")
    # dedupe preserving order
    seen = set()
    out = []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


# ---------------------------------------------------------------------------
# Public registry API
# ---------------------------------------------------------------------------
def register_all(*, persist: bool = False) -> List[str]:
    """Register every service declared in ``_CATALOG``.

    Returns the list of names that were registered (or already present).
    Set ``persist=True`` in production to write to Supabase.

    v11.4 R3: when running under a local deployment profile (see
    :func:`_is_local_profile`) the over-engineered SaaS-only services in
    :data:`_OVERENGINEERED_LOCAL_DISABLED` are registered as ``disabled``
    instead of ``enabled`` so the admin / public catalog the customer sees
    is not polluted with capabilities whose backing infra is absent.
    """
    discovered = _scan_for_services([_workspace_root()])
    discovered_set = set(discovered)

    local_profile = _is_local_profile()

    registered: List[str] = []
    for entry in _CATALOG:
        try:
            # v11.4 R3: default-disable SaaS-only services on the local stack.
            status_value = entry.get("status", "enabled")
            if (
                local_profile
                and status_value == "enabled"
                and entry["name"] in _OVERENGINEERED_LOCAL_DISABLED
            ):
                status_value = "disabled"
            svc = Service(
                name=entry["name"],
                display_name=entry["display_name"],
                description=entry.get("description", ""),
                category=ServiceCategory(entry.get("category", "misc")),
                status=ServiceStatus(status_value),
                plan_required=PlanTier(entry.get("plan_required", "free")),
                roles_allowed=list(entry.get("roles_allowed", [])),
                dependencies=list(entry.get("dependencies", [])),
            )
            service_toggle.register_service(svc, persist=persist)
            registered.append(svc.name)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("register_all %s failed: %s", entry.get("name"), exc)

    # Light discovery beyond the catalog: any agent/api/service/frontend
    # directory that we discovered but didn't list gets a placeholder row.
    declared_names = {e["name"] for e in _CATALOG}
    for name in discovered_set:
        if name in declared_names:
            continue
        category = "misc"
        if name.startswith("agent."):
            category = "agent"
        elif name.startswith("api."):
            category = "api"
        elif name.startswith("service."):
            category = "platform"
        elif name.startswith("frontend."):
            category = "frontend"
        try:
            svc = Service(
                name=name,
                display_name=name.split(".", 1)[-1].replace("_", " ").title(),
                category=ServiceCategory(category),
                status=ServiceStatus.ENABLED,
                plan_required=PlanTier.FREE,
                roles_allowed=[],
            )
            service_toggle.register_service(svc, persist=persist)
            registered.append(svc.name)
        except Exception as exc:  # pragma: no cover
            logger.warning("auto-register %s failed: %s", name, exc)

    logger.info(
        "service_registry.register_all: %d services (%d discovered, %d declared)",
        len(registered),
        len(discovered_set),
        len(_CATALOG),
    )
    return registered


def catalog_snapshot() -> List[Dict[str, Any]]:
    """Return the in-memory snapshot of declared catalog entries.

    v11.4 R3: under a local deployment profile the over-engineered SaaS-only
    services report ``status="disabled"`` here so the admin / public catalog
    reflects what is actually reachable on the local stack. The underlying
    ``_CATALOG`` rows are untouched (counts / categories unchanged).
    """
    local_profile = _is_local_profile()
    out: List[Dict[str, Any]] = []
    for e in _CATALOG:
        d = dict(e)
        d["category"] = e.get("category", "misc")
        d["plan_required"] = e.get("plan_required", "free")
        d["roles_allowed"] = list(e.get("roles_allowed", []))
        d["dependencies"] = list(e.get("dependencies", []))
        status_value = e.get("status", "enabled")
        if (
            local_profile
            and status_value == "enabled"
            and e["name"] in _OVERENGINEERED_LOCAL_DISABLED
        ):
            status_value = "disabled"
        d["status"] = status_value
        out.append(d)
    return out


def get_dependencies_for(name: str) -> List[str]:
    """Look up the declared dependencies for a service name."""
    for e in _CATALOG:
        if e["name"] == name:
            return list(e.get("dependencies", []))
    return []
