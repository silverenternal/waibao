"""Example plugin — custom resume scorer.

Demonstrates the agent surface. The plugin takes a resume payload and
returns a structured score using weighted skill / experience / education
signals. The score is then emitted on the event bus for downstream
listeners.

Permissions used:
  - db:read
  - llm:call
  - events:emit
  - metrics:emit
"""

from __future__ import annotations

from typing import Any, Dict, List

from plugins.sdk.base import Plugin, PluginContext, PluginState


class _ResumeAgent:
    """Lightweight agent that scores resumes with weighted signals."""

    def __init__(self, plugin: "ResumeScorerPlugin", ctx: PluginContext) -> None:
        self.plugin = plugin
        self.ctx = ctx

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        resume = payload.get("resume") or {}
        skills: List[str] = resume.get("skills") or []
        experience_years = float(resume.get("experience_years", 0) or 0)
        education = resume.get("education_level", "bachelor")

        weights = self.plugin.config_schema  # resolved config schema
        sw = float(weights.get("skill_weight", 0.5))
        ew = float(weights.get("experience_weight", 0.3))
        eduw = float(weights.get("education_weight", 0.2))
        min_years = float(weights.get("min_experience_years", 0))

        skill_score = min(1.0, len(skills) / 10.0)
        exp_score = min(1.0, max(0.0, experience_years - min_years) / 10.0)
        edu_score = {"highschool": 0.4, "bachelor": 0.7,
                     "master": 0.85, "phd": 1.0}.get(education, 0.5)

        total = sw * skill_score + ew * exp_score + eduw * edu_score
        total = round(min(1.0, max(0.0, total)), 3)

        # Demonstrate permission-gated operations.
        self.ctx.require_permission("events:emit")
        self.ctx.event_bus_emit("resume.scored", {
            "score": total,
            "components": {"skill": skill_score, "experience": exp_score,
                           "education": edu_score},
        })

        return {
            "score": total,
            "components": {"skill": skill_score, "experience": exp_score,
                           "education": edu_score},
            "weights": {"skill": sw, "experience": ew, "education": eduw},
        }


class ResumeScorerPlugin(Plugin):
    name = "resume-scorer"
    version = "1.0.0"
    author = "waibao-labs"
    description = "Weighted resume scorer agent"
    permissions = ["db:read", "llm:call", "events:emit", "metrics:emit"]
    config_schema = {
        "skill_weight": 0.5,
        "experience_weight": 0.3,
        "education_weight": 0.2,
        "min_experience_years": 0,
    }
    state = PluginState.INSTALLED

    def install(self, ctx: PluginContext) -> None:
        ctx.logger.info("installing resume-scorer v%s", self.version)
        self.state = PluginState.INSTALLED

    def enable(self, ctx: PluginContext) -> None:
        ctx.require_permission("events:emit")
        ctx.event_bus_emit("plugin.enabled", {"plugin": self.name})
        self.state = PluginState.ENABLED

    def disable(self, ctx: PluginContext) -> None:
        self.state = PluginState.DISABLED

    def get_agent(self) -> Any:
        # Return None here — the agent is built per-invocation with a ctx so
        # it can call require_permission(). Plugins that don't need ctx can
        # return a singleton agent.
        return _AgentFactory(self)

    def get_service(self): return None
    def get_provider(self): return None
    def get_widget(self): return None


class _AgentFactory:
    """Adapter so the registry can call ``.run(payload)`` on the agent."""

    def __init__(self, plugin: ResumeScorerPlugin) -> None:
        self.plugin = plugin

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # In real usage the registry would pass a real PluginContext; here we
        # build a minimal one that satisfies the demo. Tests bypass this.
        ctx = PluginContext(
            plugin_name=self.plugin.name,
            db=None,
            event_bus=None,
            logger=_NullLogger(),
            config=self.plugin.config_schema,
            permissions=self.plugin.permissions,
        )
        return _ResumeAgent(self.plugin, ctx).run(payload)


class _NullLogger:
    def info(self, *args, **kwargs): pass
    def warning(self, *args, **kwargs): pass
    def error(self, *args, **kwargs): pass
    def exception(self, *args, **kwargs): pass
    def debug(self, *args, **kwargs): pass