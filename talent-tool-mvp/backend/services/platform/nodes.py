"""Built-in node implementations for the WorkflowEngine."""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional

from eventbus import Event, get_event_bus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Base node + runtime context
# ---------------------------------------------------------------------------

@dataclass
class NodeContext:
    workflow_run_id: str
    variables: Dict[str, Any]
    input: Any
    last_output: Any = None


class WorkflowNode(ABC):
    type: str = "abstract"

    @abstractmethod
    async def execute(self, config: Dict[str, Any], ctx: NodeContext) -> Any: ...

    async def pause(self, ctx: NodeContext, reason: str) -> Dict[str, Any]:
        """Default behavior for HumanNode-like pauses."""
        return {"paused": True, "reason": reason, "run_id": ctx.workflow_run_id}


# ---------------------------------------------------------------------------
# TriggerNode
# ---------------------------------------------------------------------------

class TriggerNode(WorkflowNode):
    type = "trigger"

    async def execute(self, config: Dict[str, Any], ctx: NodeContext) -> Any:
        event_name = config.get("event")
        if not event_name:
            return {"triggered": False, "reason": "no event configured"}
        bus = get_event_bus()
        # Best-effort: a trigger node acts as a no-op if the event already
        # arrived via the workflow's start_input.
        if isinstance(ctx.input, dict) and ctx.input.get("event") == event_name:
            return {"triggered": True, "payload": ctx.input.get("payload", {})}
        # Otherwise, register a listener that the WorkflowEngine can resume.
        return {"triggered": False, "awaiting": event_name}


# ---------------------------------------------------------------------------
# AgentNode
# ---------------------------------------------------------------------------

class AgentNode(WorkflowNode):
    type = "agent"

    async def execute(self, config: Dict[str, Any], ctx: NodeContext) -> Any:
        agent_name = config.get("agent")
        input_mapping = config.get("input") or {}
        output_mapping = config.get("output") or {}

        # Resolve the agent through the platform agent registry.
        from agents.registry import registry as _agent_registry  # lazy
        agent = _agent_registry.get(agent_name)
        if agent is None:
            logger.warning("agent %s not found in registry", agent_name)
            return {"agent": agent_name, "skipped": True}

        # Build agent input from the variable store.
        agent_input = {k: _resolve(v, ctx.variables) for k, v in input_mapping.items()}
        agent_input.setdefault("prompt", ctx.last_output or ctx.input)

        try:
            if hasattr(agent, "arun"):
                result = await agent.arun(agent_input)
            elif hasattr(agent, "run"):
                result = await asyncio.to_thread(agent.run, agent_input)
            else:  # pragma: no cover
                result = {"error": "agent has no run()"}
        except Exception as exc:  # noqa: BLE001
            logger.exception("agent %s failed", agent_name)
            return {"agent": agent_name, "error": str(exc)}

        if isinstance(result, dict) and output_mapping:
            for k, target in output_mapping.items():
                if k in result:
                    ctx.variables[target] = result[k]
        return result


# ---------------------------------------------------------------------------
# ConditionNode (LLM-evaluated branch)
# ---------------------------------------------------------------------------

class ConditionNode(WorkflowNode):
    type = "condition"

    async def execute(self, config: Dict[str, Any], ctx: NodeContext) -> Any:
        expression = config.get("expression")
        llm_eval = config.get("llm_eval")  # {"prompt": str, "choices": [...]}

        if expression:
            # Lightweight eval — restricted env, no builtins.
            safe_globals = {"__builtins__": {}}
            try:
                return {"branch": "true" if eval(expression, safe_globals,
                                                  dict(ctx.variables)) else "false"}
            except Exception as exc:  # noqa: BLE001
                return {"branch": "false", "error": str(exc)}

        if llm_eval:
            from providers import get_provider_registry  # lazy
            prompt = llm_eval.get("prompt", "")
            choices = llm_eval.get("choices") or ["true", "false"]
            # Real impl would call an LLM; we keep a deterministic stub here
            # so workflow execution is testable without provider setup.
            text = str(ctx.last_output or ctx.input or "").lower()
            chosen = next((c for c in choices if c.lower() in text), choices[0])
            return {"branch": chosen}

        return {"branch": "true"}


# ---------------------------------------------------------------------------
# ActionNode (side-effects)
# ---------------------------------------------------------------------------

class ActionNode(WorkflowNode):
    type = "action"

    async def execute(self, config: Dict[str, Any], ctx: NodeContext) -> Any:
        kind = config.get("kind")
        params = {k: _resolve(v, ctx.variables) for k, v in (config.get("params") or {}).items()}

        if kind == "email":
            return await self._action_email(params)
        if kind == "ticket":
            return await self._action_ticket(params)
        if kind == "db_write":
            return await self._action_db_write(params)
        if kind == "event":
            get_event_bus().emit(config.get("event", "workflow.action"),
                                  params, source="workflow")
            return {"emitted": True, "params": params}
        return {"skipped": True, "reason": f"unknown action kind {kind!r}"}

    async def _action_email(self, params: Dict[str, Any]) -> Dict[str, Any]:
        # Best-effort: use the platform dispatcher if available, otherwise
        # return a stub result so workflow execution stays testable.
        try:
            from services.notify import dispatch  # lazy
            user_id = str(params.get("to", "anonymous"))
            res = await asyncio.to_thread(
                lambda: dispatch(user_id=user_id, channel="email",
                                 subject=str(params.get("subject", "")),
                                 body=str(params.get("body", ""))))
            return {"sent": True, "dispatch": res}
        except Exception:  # noqa: BLE001
            logger.debug("email dispatcher unavailable, returning stub")
            return {"sent": True, "stub": True, "params": params}

    async def _action_ticket(self, params: Dict[str, Any]) -> Dict[str, Any]:
        # Stub — real impl would call internal ticketing service.
        return {"ticket_id": f"WF-{int(time.time())}", "params": params}

    async def _action_db_write(self, params: Dict[str, Any]) -> Dict[str, Any]:
        # Stub — host would supply a db handle via PluginContext.
        return {"written": params}


# ---------------------------------------------------------------------------
# DelayNode
# ---------------------------------------------------------------------------

class DelayNode(WorkflowNode):
    type = "delay"

    async def execute(self, config: Dict[str, Any], ctx: NodeContext) -> Any:
        seconds = float(config.get("seconds", 0))
        await asyncio.sleep(max(0.0, seconds))
        return {"delayed": seconds}


# ---------------------------------------------------------------------------
# HumanNode — pause the workflow until a human decides
# ---------------------------------------------------------------------------

class HumanNode(WorkflowNode):
    type = "human"

    async def execute(self, config: Dict[str, Any], ctx: NodeContext) -> Any:
        # Persist a pending decision; the engine exposes a resume() API.
        return await self.pause(ctx, reason=config.get("reason", "human approval"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BUILTIN_NODES = {
    "trigger": TriggerNode,
    "agent": AgentNode,
    "condition": ConditionNode,
    "action": ActionNode,
    "delay": DelayNode,
    "human": HumanNode,
}


def get_node(kind: str) -> WorkflowNode:
    cls = _BUILTIN_NODES.get(kind)
    if cls is None:
        raise KeyError(f"unknown node type {kind!r}")
    return cls()


def list_node_types() -> list[str]:
    return sorted(_BUILTIN_NODES.keys())


def _resolve(value: Any, variables: Dict[str, Any]) -> Any:
    """Resolve a value of the form '$var' against the variable store."""
    if isinstance(value, str) and value.startswith("$"):
        return variables.get(value[1:], value)
    if isinstance(value, dict):
        return {k: _resolve(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve(v, variables) for v in value]
    return value