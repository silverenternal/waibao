"""Agent-side event emit helpers (v6.0).

Reusable wrappers around `emit()` so each agent module gets a one-call,
typed helper rather than open-coding payload dicts. All wrappers are
no-ops if the bus is unavailable (the underlying `emit()` catches and
logs); they're safe to call from agent handlers without try/except.

Usage::

    from eventbus.integration import emit_profile_updated, emit_ticket_escalated

    # in an agent handler:
    emit_profile_updated(user_id=..., candidate_id=..., fields=["..."],
                         completeness=0.7, source="clarifier")
"""

from __future__ import annotations

from typing import Iterable, Optional

from .decorators import emit as _emit


def emit_profile_updated(*, user_id: str, candidate_id: Optional[str] = None,
                          fields: Iterable[str] = (), completeness: float = 0.0,
                          source: str = "app", correlation_id: Optional[str] = None) -> None:
    _emit("profile.updated", {
        "user_id": user_id,
        "candidate_id": candidate_id,
        "fields": list(fields),
        "completeness": completeness,
        "source": source,
    }, source=source, correlation_id=correlation_id)


def emit_profile_enriched(*, user_id: str, candidate_id: Optional[str] = None,
                           new_skills: Iterable[str] = (), source: str = "resume",
                           correlation_id: Optional[str] = None) -> None:
    _emit("profile.enriched", {
        "user_id": user_id,
        "candidate_id": candidate_id,
        "new_skills": list(new_skills)[:10],
        "source": source,
    }, source=source, correlation_id=correlation_id)


def emit_profile_created(*, user_id: str, candidate_id: Optional[str] = None,
                          initial_fields: Iterable[str] = (),
                          source: str = "app",
                          correlation_id: Optional[str] = None) -> None:
    _emit("profile.created", {
        "user_id": user_id,
        "candidate_id": candidate_id,
        "initial_fields": list(initial_fields),
    }, source=source, correlation_id=correlation_id)


def emit_needs_clarified(*, user_id: str, candidate_id: Optional[str] = None,
                          must_haves: Iterable[str] = (),
                          deal_breakers: Iterable[str] = (),
                          confidence: float = 0.0,
                          source: str = "app",
                          correlation_id: Optional[str] = None) -> None:
    _emit("needs.clarified", {
        "user_id": user_id,
        "candidate_id": candidate_id,
        "must_haves": list(must_haves),
        "deal_breakers": list(deal_breakers),
        "confidence": confidence,
    }, source=source, correlation_id=correlation_id)


def emit_emotion_detected(*, user_id: str, primary_emotion: str,
                           intensity: float, sentiment: float = 0.0,
                           evidence: Iterable[str] = (),
                           source: str = "app",
                           correlation_id: Optional[str] = None) -> None:
    _emit("emotion.detected", {
        "user_id": user_id,
        "primary_emotion": primary_emotion,
        "intensity": intensity,
        "sentiment": sentiment,
        "evidence": list(evidence)[:5],
    }, source=source, correlation_id=correlation_id)


def emit_emotion_risk(*, user_id: str, risk_level: str,
                       primary_emotion: str, intensity: float,
                       recommended_action: str = "log",
                       source: str = "app",
                       correlation_id: Optional[str] = None) -> None:
    _emit("emotion.risk", {
        "user_id": user_id,
        "risk_level": risk_level,
        "primary_emotion": primary_emotion,
        "intensity": intensity,
        "recommended_action": recommended_action,
    }, source=source, correlation_id=correlation_id)


def emit_plan_generated(*, user_id: str, plan_id: str,
                          candidate_id: Optional[str] = None,
                          milestones: Iterable[str] = (),
                          horizon_months: int = 12,
                          source: str = "app",
                          correlation_id: Optional[str] = None) -> None:
    _emit("plan.generated", {
        "user_id": user_id,
        "candidate_id": candidate_id,
        "plan_id": plan_id,
        "milestones": list(milestones)[:10],
        "horizon_months": horizon_months,
    }, source=source, correlation_id=correlation_id)


def emit_market_updated(*, region: str, jobs_count: int = 0,
                         delta_pct: float = 0.0,
                         top_skills: Iterable[str] = (),
                         source: str = "app",
                         correlation_id: Optional[str] = None) -> None:
    _emit("market.updated", {
        "region": region,
        "jobs_count": jobs_count,
        "delta_pct": delta_pct,
        "top_skills": list(top_skills)[:10],
    }, source=source, correlation_id=correlation_id)


def emit_journal_submitted(*, user_id: str, journal_id: str,
                            mood: Optional[float] = None, summary: str = "",
                            ts: Optional[str] = None,
                            source: str = "app",
                            correlation_id: Optional[str] = None) -> None:
    _emit("journal.submitted", {
        "user_id": user_id,
        "journal_id": journal_id,
        "mood": mood,
        "summary": summary,
        "ts": ts,
    }, source=source, correlation_id=correlation_id)


def emit_role_image_updated(*, employer_id: str, role_id: Optional[str] = None,
                             traits: Iterable[str] = (),
                             must_haves: Iterable[str] = (),
                             source: str = "app",
                             correlation_id: Optional[str] = None) -> None:
    _emit("role.image.updated", {
        "employer_id": employer_id,
        "role_id": role_id,
        "traits": list(traits)[:10],
        "must_haves": list(must_haves)[:10],
    }, source=source, correlation_id=correlation_id)


def emit_strategy_updated(*, employer_id: str, vision_id: Optional[str] = None,
                           themes: Iterable[str] = (),
                           horizon_months: int = 12,
                           source: str = "app",
                           correlation_id: Optional[str] = None) -> None:
    _emit("strategy.updated", {
        "employer_id": employer_id,
        "vision_id": vision_id,
        "themes": list(themes)[:10],
        "horizon_months": horizon_months,
    }, source=source, correlation_id=correlation_id)


def emit_ticket_created(*, ticket_id: str, employer_id: str,
                         severity: str = "normal", category: str = "general",
                         summary: str = "",
                         source: str = "app",
                         correlation_id: Optional[str] = None) -> None:
    _emit("ticket.created", {
        "ticket_id": ticket_id,
        "employer_id": employer_id,
        "severity": severity,
        "category": category,
        "summary": summary[:300],
    }, source=source, correlation_id=correlation_id)


def emit_ticket_escalated(*, ticket_id: Optional[str], from_level: str,
                           to_level: str, reason: str = "",
                           source: str = "app",
                           correlation_id: Optional[str] = None) -> None:
    _emit("ticket.escalated", {
        "ticket_id": ticket_id,
        "from_level": from_level,
        "to_level": to_level,
        "reason": reason,
    }, source=source, correlation_id=correlation_id)


def emit_agent_started(*, agent_name: str, user_id: str,
                        run_id: Optional[str] = None,
                        input_keys: Iterable[str] = (),
                        source: Optional[str] = None) -> None:
    _emit("agent.started", {
        "agent_name": agent_name,
        "user_id": user_id,
        "run_id": run_id,
        "input_keys": list(input_keys),
    }, source=source or f"agent.{agent_name}")


def emit_agent_completed(*, agent_name: str, user_id: str,
                          run_id: Optional[str] = None,
                          latency_ms: Optional[float] = None,
                          artifacts_count: int = 0,
                          correlation_id: Optional[str] = None,
                          source: Optional[str] = None) -> None:
    _emit("agent.completed", {
        "agent_name": agent_name,
        "user_id": user_id,
        "run_id": run_id,
        "latency_ms": latency_ms,
        "artifacts_count": artifacts_count,
    }, source=source or f"agent.{agent_name}", correlation_id=correlation_id)


def emit_agent_failed(*, agent_name: str, user_id: str, error: str,
                       recoverable: bool = True,
                       run_id: Optional[str] = None,
                       source: Optional[str] = None) -> None:
    _emit("agent.failed", {
        "agent_name": agent_name,
        "user_id": user_id,
        "run_id": run_id,
        "error": error,
        "recoverable": recoverable,
    }, source=source or f"agent.{agent_name}")


__all__ = [name for name in dir() if name.startswith("emit_")]
