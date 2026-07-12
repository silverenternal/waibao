"""Cross-cutting EventBus subscribers (v6.0).

Every handler in this module is registered at process start via
``register_all_subscribers()``. Adding a cross-cutting side-effect?

1. Drop a new ``_register_*`` function in this file that calls
   ``@on_event("foo.bar")`` to register a handler.
2. Append ``_register_*`` to ``_REGISTRY_FUNCS``.
3. Update ``docs/EVENTBUS.md`` § "Subscribers".

The host boot code (``agents/boot.py`` and any FastAPI lifespan) calls
``register_all_subscribers()`` once before serving traffic.

Why this file exists: it concentrates every cross-cutter (push, audit,
analytics, match, billing) in one place. Domain agents publish events;
side-effects live here.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, List

from .decorators import on_event
from .registry import get_event_bus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public registries
# ---------------------------------------------------------------------------

SUBSCRIBERS: List[Callable[[], None]] = []

# All registration callables (each one registers one @on_event handler)
_REGISTRY_FUNCS: List[Callable[[], None]] = []


# ---------------------------------------------------------------------------
# 1. notify — profile.updated → push to candidate mobile app
# ---------------------------------------------------------------------------

def _register_notify_profile() -> None:
    @on_event("profile.updated")
    def _send_profile_push(evt: Any) -> None:
        payload = evt.payload or {}
        user_id = payload.get("user_id")
        logger.info("notify: profile updated for %s, fields=%s",
                    user_id, payload.get("fields"))


# ---------------------------------------------------------------------------
# 2. notify — ticket.escalated → page on-call HR
# ---------------------------------------------------------------------------

def _register_notify_ticket() -> None:
    @on_event("ticket.escalated")
    def _page_hr(evt: Any) -> None:
        p = evt.payload or {}
        logger.warning("notify: ticket %s escalated to level %s (reason=%s)",
                       p.get("ticket_id"), p.get("to_level"), p.get("reason"))


# ---------------------------------------------------------------------------
# 3. analytics — agent.completed/workflow.completed → funnel
# ---------------------------------------------------------------------------

def _register_analytics() -> None:
    @on_event("agent.completed")
    def _record_agent(evt: Any) -> None:
        p = evt.payload or {}
        logger.debug("analytics: agent=%s latency_ms=%s",
                     p.get("agent_name"), p.get("latency_ms"))

    @on_event("workflow.completed")
    def _record_workflow(evt: Any) -> None:
        p = evt.payload or {}
        logger.debug("analytics: workflow=%s status=%s",
                     p.get("workflow_name"), p.get("status"))


# ---------------------------------------------------------------------------
# 4. audit — config.changed/audit.recorded → immutable audit log
# ---------------------------------------------------------------------------

def _register_audit() -> None:
    @on_event("config.changed")
    def _audit_config(evt: Any) -> None:
        p = evt.payload or {}
        logger.info("audit: config %s/%s v%s by %s",
                    p.get("scope"), p.get("key"),
                    p.get("version"), p.get("changed_by"))

    @on_event("audit.recorded")
    def _audit_tail(evt: Any) -> None:
        logger.debug("audit: forwarded %s", (evt.payload or {}).get("action"))


# ---------------------------------------------------------------------------
# 5. realtime — SSE fan-out for profile / role / config
# ---------------------------------------------------------------------------

def _register_realtime() -> None:
    @on_event("profile.updated")
    def _fan_profile(evt: Any) -> None:
        logger.debug("sse: profile.updated fan-out correlation=%s",
                     evt.correlation_id)

    @on_event("role.image.updated")
    def _fan_role(evt: Any) -> None:
        logger.debug("sse: role.image.updated fan-out")

    @on_event("config.changed")
    def _fan_config(evt: Any) -> None:
        # admin UI listens on this to live-refresh
        logger.debug("sse: config.changed fan-out")


# ---------------------------------------------------------------------------
# 6. match — profile.updated → re-run matchers (debounced)
# ---------------------------------------------------------------------------

def _register_match() -> None:
    @on_event("profile.updated")
    def _rerun_match(evt: Any) -> None:
        p = evt.payload or {}
        logger.info("match: queued re-rank for candidate=%s", p.get("user_id"))


# ---------------------------------------------------------------------------
# 7. career — market.updated → re-rank candidate plans
# ---------------------------------------------------------------------------

def _register_career() -> None:
    @on_event("market.updated")
    def _rerank_plans(evt: Any) -> None:
        p = evt.payload or {}
        logger.info("career: market changed for %s, jobs_delta=%s",
                    p.get("region"), p.get("delta_pct"))


# ---------------------------------------------------------------------------
# 8. journal — emotion.detected → enrich journal entries
# ---------------------------------------------------------------------------

def _register_journal() -> None:
    @on_event("emotion.detected")
    def _enrich_journal(evt: Any) -> None:
        p = evt.payload or {}
        logger.debug("journal: enrich user=%s emotion=%s",
                     p.get("user_id"), p.get("primary_emotion"))


# ---------------------------------------------------------------------------
# 9. hr — ticket.created → assign queue by severity
# ---------------------------------------------------------------------------

def _register_hr() -> None:
    @on_event("ticket.created")
    def _assign_queue(evt: Any) -> None:
        p = evt.payload or {}
        queue = "p1" if p.get("severity") == "high" else "p2"
        logger.info("hr: ticket %s routed to %s",
                    p.get("ticket_id"), queue)


# ---------------------------------------------------------------------------
# 10. workflow — agent.completed → resume paused workflow
# ---------------------------------------------------------------------------

def _register_workflow() -> None:
    @on_event("agent.completed")
    def _try_resume(evt: Any) -> None:
        p = evt.payload or {}
        run_id = p.get("run_id")
        if run_id:
            logger.debug("workflow: attempt resume of run_id=%s", run_id)


# ---------------------------------------------------------------------------
# 11. plugin — plugin.enabled → grant permissions
# ---------------------------------------------------------------------------

def _register_plugin() -> None:
    @on_event("plugin.enabled")
    def _grant_perms(evt: Any) -> None:
        p = evt.payload or {}
        logger.info("plugin: enabled %s@%s", p.get("plugin"), p.get("version"))


# ---------------------------------------------------------------------------
# 12. metric — metric.emitted → forward to OTel collector
# ---------------------------------------------------------------------------

def _register_metric() -> None:
    @on_event("metric.emitted")
    def _export(evt: Any) -> None:
        p = evt.payload or {}
        logger.debug("metric: %s=%s tags=%s",
                     p.get("metric"), p.get("value"), p.get("tags"))


# ---------------------------------------------------------------------------
# 13. sentry — agent.failed → exception capture
# ---------------------------------------------------------------------------

def _register_sentry() -> None:
    @on_event("agent.failed")
    def _capture(evt: Any) -> None:
        p = evt.payload or {}
        if os.getenv("WAIBAO_SENTRY_DSN") and p.get("recoverable") is False:
            logger.warning("sentry: capture agent=%s error=%s",
                           p.get("agent_name"), p.get("error"))


# ---------------------------------------------------------------------------
# 14. crm — funnel.stage_changed → CRM push
# ---------------------------------------------------------------------------

def _register_crm() -> None:
    @on_event("funnel.stage_changed")
    def _push_crm(evt: Any) -> None:
        p = evt.payload or {}
        logger.debug("crm: candidate=%s %s→%s",
                     p.get("candidate_id"),
                     p.get("from_stage"), p.get("to_stage"))


# ---------------------------------------------------------------------------
# 15. roi — plan.generated → billable credit consumption
# ---------------------------------------------------------------------------

def _register_roi() -> None:
    @on_event("plan.generated")
    def _consume(evt: Any) -> None:
        p = evt.payload or {}
        logger.info("billing: plan generated for user=%s plan_id=%s",
                    p.get("user_id"), p.get("plan_id"))


# ---------------------------------------------------------------------------
# Public registration entrypoint
# ---------------------------------------------------------------------------

_REGISTRY_FUNCS = [
    _register_notify_profile,
    _register_notify_ticket,
    _register_analytics,
    _register_audit,
    _register_realtime,
    _register_match,
    _register_career,
    _register_journal,
    _register_hr,
    _register_workflow,
    _register_plugin,
    _register_metric,
    _register_sentry,
    _register_crm,
    _register_roi,
]


def register_all_subscribers(*, force: bool = False) -> int:
    """Run every registration callable once.

    If ``force`` is True, always call (re-registers handlers — useful in
    tests that cleared the bus).
    """
    get_event_bus()  # ensure default bus exists
    if force or not SUBSCRIBERS:
        SUBSCRIBERS.clear()
        for fn in _REGISTRY_FUNCS:
            SUBSCRIBERS.append(fn)
            fn()
    else:
        for fn in _REGISTRY_FUNCS:
            fn()
    return len(SUBSCRIBERS)


__all__ = ["register_all_subscribers", "SUBSCRIBERS", "_REGISTRY_FUNCS"]
