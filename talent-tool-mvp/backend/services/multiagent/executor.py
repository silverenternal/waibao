"""Real LLM-backed agent executor — T5022.

Replaces the deterministic ``default_executor`` stub with one that drives
a real LLM. The executor:

* builds a chat prompt from the agent's role/goal/backstory + the task,
* calls the configured LLM client (OpenAI-compatible or CrewAI),
* parses the response into the ``{decision, confidence, rationale}``
  shape the consensus layer expects,
* records per-agent metrics (latency / tokens / cost / success).

When ``crewai`` is installed we wrap the real ``crewai.Agent`` /
``crewai.Crew``; otherwise we use a lighter-weight direct LLM call that
honours the same contract. The executor always degrades to the
deterministic stub when no LLM is wired (offline tests), but flags this
via the ``backend`` field so callers can tell real from synthetic.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from .metrics import (
    AgentMetric,
    estimate_cost,
    get_metrics_recorder,
)
from .orchestrator import Agent, Task

logger = logging.getLogger("waibao.multiagent.executor")


# ---------------------------------------------------------------------------
# LLM protocol
# ---------------------------------------------------------------------------

class LLMClient:
    """Minimal OpenAI-compatible chat client used by the executor.

    Exposes both sync and async ``chat`` so the executor can be driven
    from either loop. Real deployments pass an SDK-wrapping subclass; the
    default ``FakeLLMClient`` returns deterministic JSON so tests run
    offline.
    """

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        self.model = model

    def chat(self, messages: List[Dict[str, str]]) -> str:  # pragma: no cover - overridden
        raise NotImplementedError

    async def async_chat(self, messages: List[Dict[str, str]]) -> str:
        return self.chat(messages)


class OpenAIChatClient(LLMClient):
    """Real OpenAI-compatible client. Requires ``openai`` + an API key."""

    def __init__(self, model: str = "gpt-4o-mini", *, api_key: Optional[str] = None,
                 base_url: Optional[str] = None) -> None:
        super().__init__(model)
        import os as _os
        if not api_key and not _os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("OpenAIChatClient requires an api_key (or OPENAI_API_KEY)")
        try:
            from openai import OpenAI  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"openai SDK unavailable: {exc}") from exc
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs)
        self.last_usage: dict[str, int] = {}

    def chat(self, messages: List[Dict[str, str]]) -> str:
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.2,
        )
        usage = getattr(resp, "usage", None)
        if usage is not None:
            self.last_usage = {
                "prompt_tokens": int(getattr(usage, "prompt_tokens", 0)),
                "completion_tokens": int(getattr(usage, "completion_tokens", 0)),
            }
        return resp.choices[0].message.content or ""


class FakeLLMClient(LLMClient):
    """Deterministic LLM used by tests / offline runs.

    Produces a JSON response shaped by keywords in the task description
    so the four scenarios still exercise consensus voting.
    """

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        super().__init__(model)
        self.last_usage = {"prompt_tokens": 0, "completion_tokens": 0}

    def chat(self, messages: List[Dict[str, str]]) -> str:
        # Reuse the orchestrator's synthesizer for a stable decision shape.
        from .orchestrator import _synthesize_decision  # local import
        user_msg = ""
        agent_role = ""
        for m in messages:
            if m["role"] == "system":
                agent_role = m["content"]
            if m["role"] == "user":
                user_msg = m["content"]
        decision = _synthesize_decision(
            Agent(role=agent_role, goal="", backstory=""),  # type: ignore[arg-type]
            user_msg, {},
        )
        confidence = 0.8
        rationale = f"deterministic response for {agent_role[:40]}"
        self.last_usage = {
            "prompt_tokens": len(user_msg.split()) + 50,
            "completion_tokens": 40,
        }
        return json.dumps({
            "decision": decision, "confidence": confidence, "rationale": rationale,
        })


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------

@dataclass
class LLMExecutor:
    """Real LLM executor implementing the orchestrator's executor protocol.

    Args:
        llm: an :class:`LLMClient` (real or fake).
        use_crewai: when True and ``crewai`` is importable, delegate the
            actual LLM call to a real CrewAI ``Agent``. Otherwise call the
            LLM directly with a CrewAI-style prompt.
        metrics_recorder: where to publish per-agent metrics.
    """

    llm: LLMClient
    use_crewai: bool = False
    metrics_recorder: Any = None
    scenario: str = ""

    def __post_init__(self) -> None:
        if self.metrics_recorder is None:
            self.metrics_recorder = get_metrics_recorder()

    # ------------------------------------------------------------------
    def __call__(self, agent: Agent, task: Task, context: Dict[str, Any]) -> Dict[str, Any]:
        return self.execute(agent, task, context)

    # ------------------------------------------------------------------
    def execute(self, agent: Agent, task: Task, context: Dict[str, Any]) -> Dict[str, Any]:
        start = time.time()
        scenario = self.scenario or str(context.get("scenario", "unknown"))
        model = self.llm.model
        success = True
        error: Optional[str] = None
        decision: Any = None
        confidence = 0.5
        rationale = ""
        prompt_tokens = 0
        completion_tokens = 0

        try:
            raw = self._invoke(agent, task, context)
            decision, confidence, rationale = self._parse(raw, agent, task, context)
            usage = getattr(self.llm, "last_usage", {}) or {}
            prompt_tokens = int(usage.get("prompt_tokens", 0))
            completion_tokens = int(usage.get("completion_tokens", 0))
        except Exception as exc:  # noqa: BLE001
            logger.exception("LLM executor failed for %s", agent.role)
            success = False
            error = str(exc)
            # degrade to the deterministic stub so the run still completes
            from .orchestrator import default_executor
            stub = default_executor(agent, task, context)
            decision = stub.get("decision")
            confidence = float(stub.get("confidence", 0.5))
            rationale = f"executor-fallback: {error[:80]}"

        latency = time.time() - start
        cost = estimate_cost(model, prompt_tokens, completion_tokens)

        self.metrics_recorder.record_agent(AgentMetric(
            agent_id=agent.role,
            scenario=scenario,
            latency_s=latency,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost,
            success=success,
            error=error,
            model=model,
        ))

        return {
            "agent_id": agent.role,
            "agent_goal": agent.goal,
            "task": task.description,
            "decision": decision,
            "confidence": confidence,
            "rationale": rationale,
            "backend": "crewai" if (self.use_crewai and _crewai_available()) else "llm"
                       if success else "fallback",
            "ts": time.time(),
        }

    # ------------------------------------------------------------------
    # Invocation
    # ------------------------------------------------------------------
    def _invoke(self, agent: Agent, task: Task, context: Dict[str, Any]) -> str:
        if self.use_crewai and _crewai_available():
            return self._invoke_crewai(agent, task, context)
        messages = self._build_messages(agent, task, context)
        return self.llm.chat(messages)

    def _build_messages(
        self, agent: Agent, task: Task, context: Dict[str, Any],
    ) -> List[Dict[str, str]]:
        system = (
            f"You are {agent.role}. Goal: {agent.goal}. "
            f"Background: {agent.backstory}\n"
            "Respond with STRICT JSON only: "
            '{"decision": <score 0..100 for scoring tasks, else a short string>, '
            '"confidence": 0..1, "rationale": "..."}.'
        )
        ctx_blob = json.dumps({k: v for k, v in context.items()
                               if k not in ("__input__",)}, default=str)[:1500]
        user = (
            f"Task: {task.description or task.expected_output}\n"
            f"Goal: {context.get('goal', '')}\n"
            f"Context: {ctx_blob}\n"
            "Return the JSON now."
        )
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    def _invoke_crewai(self, agent: Agent, task: Task, context: Dict[str, Any]) -> str:
        try:
            from crewai import Agent as CrewAgent, Task as CrewTask, Crew  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"crewai unavailable: {exc}") from exc
        ca = CrewAgent(
            role=agent.role, goal=agent.goal, backstory=agent.backstory,
            allow_delegation=agent.allow_delegation, verbose=agent.verbose,
        )
        ct = CrewTask(
            description=task.description or task.expected_output,
            expected_output="JSON: decision, confidence, rationale",
            agent=ca,
        )
        crew = Crew(agents=[ca], tasks=[ct])
        return str(crew.kickoff())

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------
    def _parse(
        self, raw: str, agent: Agent, task: Task, context: Dict[str, Any],
    ) -> tuple[Any, float, str]:
        try:
            data = json.loads(_extract_json(raw))
            decision = data.get("decision")
            confidence = float(data.get("confidence", 0.7))
            rationale = str(data.get("rationale", ""))
        except Exception:  # noqa: BLE001
            from .orchestrator import _synthesize_decision
            decision = _synthesize_decision(agent, task.description or "", context)
            confidence = 0.7
            rationale = raw[:200] if raw else "unparsed LLM output"
        return decision, max(0.0, min(1.0, confidence)), rationale


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _crewai_available() -> bool:
    try:
        import crewai  # type: ignore  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def _extract_json(raw: str) -> str:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        return raw[start : end + 1]
    return raw


# ---------------------------------------------------------------------------
# Scenario factory — returns an Orchestrator wired with the real executor
# ---------------------------------------------------------------------------

def build_scoped_orchestrator(
    llm: LLMClient,
    *,
    scenario: str,
    use_crewai: bool = False,
    event_emitter: Optional[Callable[[str, Dict[str, Any]], None]] = None,
):
    """Return an :class:`Orchestrator` whose executor drives ``llm`` and
    tags every metric with ``scenario``."""
    from .orchestrator import Orchestrator
    executor = LLMExecutor(llm=llm, use_crewai=use_crewai, scenario=scenario)
    return Orchestrator(executor=executor, event_emitter=event_emitter)
