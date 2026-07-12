"""Example plugin — conversational interview bot.

Demonstrates the service surface. The plugin accepts an interview
session payload, returns the next question (templated), and emits
`interview.question_asked` / `interview.session_completed` events on
the host's event bus.

This is a *reference* implementation: the real version would call an
LLM provider through the host's LLM gateway.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

from plugins.sdk.base import Plugin, PluginContext, PluginState


_QUESTION_LIBRARY: Dict[str, str] = {
    "tell_me_about_yourself": "Can you walk me through your background?",
    "why_this_role": "What attracted you to this role?",
    "biggest_achievement": "What's the biggest professional achievement you're proud of?",
    "conflict_resolution": "Tell me about a time you disagreed with a coworker. How did you handle it?",
    "system_design_basics": "How would you design a URL shortener?",
}


class _InterviewService:
    def __init__(self, plugin: "InterviewBotPlugin", ctx: PluginContext) -> None:
        self.plugin = plugin
        self.ctx = ctx

    def handle(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        action = payload.get("action", "next_question")
        session_id = payload.get("session_id")
        asked: List[str] = list(payload.get("asked") or [])

        if action == "start":
            asked = []
        elif action == "complete":
            self.ctx.require_permission("events:emit")
            self.ctx.event_bus_emit("interview.session_completed", {
                "session_id": session_id,
                "questions_asked": asked,
                "duration_s": payload.get("duration_s", 0),
            })
            return {"completed": True, "session_id": session_id,
                    "questions_asked": asked}

        # Determine the next question.
        pool = self.plugin.config_schema.get("question_pool", [])
        max_q = int(self.plugin.config_schema.get("max_questions", 5))
        next_q = None
        for q in pool:
            if q not in asked:
                next_q = q
                break

        if next_q is None or len(asked) >= max_q:
            return {"completed": True, "session_id": session_id,
                    "questions_asked": asked}

        asked.append(next_q)
        question_text = _QUESTION_LIBRARY.get(next_q, next_q)
        self.ctx.require_permission("events:emit")
        self.ctx.event_bus_emit("interview.question_asked", {
            "session_id": session_id,
            "question_id": next_q,
            "question_text": question_text,
            "index": len(asked),
        })
        return {
            "completed": False,
            "session_id": session_id,
            "question": {"id": next_q, "text": question_text},
            "asked": asked,
        }


class InterviewBotPlugin(Plugin):
    name = "interview-bot"
    version = "1.2.0"
    author = "waibao-labs"
    description = "Conversational interview bot"
    permissions = ["llm:call", "events:emit", "metrics:emit"]
    config_schema = {
        "max_questions": 5,
        "difficulty": "medium",
        "question_pool": [
            "tell_me_about_yourself", "why_this_role", "biggest_achievement",
            "conflict_resolution", "system_design_basics",
        ],
    }
    state = PluginState.INSTALLED

    def install(self, ctx: PluginContext) -> None:
        ctx.logger.info("interview-bot installing")
        self.state = PluginState.INSTALLED

    def enable(self, ctx: PluginContext) -> None:
        ctx.require_permission("events:emit")
        ctx.event_bus_emit("plugin.enabled", {"plugin": self.name})
        self.state = PluginState.ENABLED

    def disable(self, ctx: PluginContext) -> None:
        self.state = PluginState.DISABLED

    def get_service(self) -> Any:
        return _ServiceAdapter(self)

    def get_agent(self): return None
    def get_provider(self): return None
    def get_widget(self): return None


class _ServiceAdapter:
    """Adapter so the registry can call ``.handle(payload)``."""

    def __init__(self, plugin: InterviewBotPlugin) -> None:
        self.plugin = plugin

    def handle(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        ctx = PluginContext(
            plugin_name=self.plugin.name,
            db=None,
            event_bus=None,
            logger=_NullLogger(),
            config=self.plugin.config_schema,
            permissions=self.plugin.permissions,
        )
        return _InterviewService(self.plugin, ctx).handle(payload)


class _NullLogger:
    def info(self, *args, **kwargs): pass
    def warning(self, *args, **kwargs): pass
    def error(self, *args, **kwargs): pass
    def exception(self, *args, **kwargs): pass
    def debug(self, *args, **kwargs): pass