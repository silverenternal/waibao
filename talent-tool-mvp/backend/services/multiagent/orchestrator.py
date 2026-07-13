"""Orchestrator — the CrewAI-style Crew runner.

This module is the workhorse: given a goal + a plan, it walks each step,
collects outputs, and produces an ``OrchestrationResult``. The four
core scenarios (resume_scoring, bias_review, offer_negotiation,
strategy_decode) are exercised via the public ``orchestrate`` entry.

We vendor CrewAI semantics (Agent / Task / Crew) but ship a
deterministic in-memory backend so the test suite has zero external
dependencies. The orchestrator also emits `multiagent.task.completed`
events and writes a shared context chunk to the MemoryStore so
downstream agents / human reviewers can resume.

Public API:
  * Orchestrator                     - the runner
  * OrchestrationTask / OrchestrationResult
  * get_orchestrator / reset_orchestrator
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from .consensus import (
    ConsensusResult,
    ConsensusStrategy,
    ConsensusVote,
    aggregate,
)
from .patterns import (
    CollaborationPattern,
    PatternPlan,
    ScenarioKind,
    StepPlan,
    build_pattern,
)
from .roles import AgentRoleRegistry, Role, RoleKind, register_default_roles

logger = logging.getLogger("waibao.multiagent.orchestrator")


# ----------------------------------------------------------------------
# CrewAI vendor-in: Agent / Task / Crew shims
# ----------------------------------------------------------------------
# These classes are intentionally minimal — they model the contract
# used by CrewAI (Agent has role/goal/backstory; Task has agent/description/
# expected_output; Crew has agents/tasks/process) without dragging in the
# full dependency surface. A future PR can re-export `crewai.Agent` here.

class CrewProcess(str, Enum):
    SEQUENTIAL = "sequential"
    HIERARCHICAL = "hierarchical"


@dataclass
class Agent:
    """A CrewAI-style agent."""

    role: str
    goal: str
    backstory: str
    tools: List[str] = field(default_factory=list)
    allow_delegation: bool = False
    verbose: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "goal": self.goal,
            "backstory": self.backstory,
            "tools": list(self.tools),
            "allow_delegation": self.allow_delegation,
            "verbose": self.verbose,
        }


@dataclass
class Task:
    """A CrewAI-style task: a unit of work tied to an agent."""

    description: str
    agent: Agent
    expected_output: str = ""
    context: List["Task"] = field(default_factory=list)
    output: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "agent": self.agent.to_dict(),
            "expected_output": self.expected_output,
            "has_context": bool(self.context),
            "output": self.output,
        }


@dataclass
class Crew:
    """A CrewAI-style crew: agents + tasks + process."""

    agents: List[Agent]
    tasks: List[Task]
    process: CrewProcess = CrewProcess.SEQUENTIAL

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agents": [a.to_dict() for a in self.agents],
            "tasks": [t.to_dict() for t in self.tasks],
            "process": self.process.value,
        }


# ----------------------------------------------------------------------
# Public types
# ----------------------------------------------------------------------

@dataclass
class OrchestrationTask:
    """The request to run a multi-agent scenario."""

    scenario: ScenarioKind
    goal: str
    context: Dict[str, Any] = field(default_factory=dict)
    pattern: Optional[CollaborationPattern] = None
    consensus: Optional[ConsensusStrategy] = None
    max_rounds: int = 3
    tenant_id: Optional[str] = None
    correlation_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario": self.scenario.value,
            "goal": self.goal,
            "context": dict(self.context),
            "pattern": self.pattern.value if self.pattern else None,
            "consensus": self.consensus.value if self.consensus else None,
            "max_rounds": self.max_rounds,
            "tenant_id": self.tenant_id,
            "correlation_id": self.correlation_id,
        }


@dataclass
class OrchestrationResult:
    """The output of an orchestration."""

    run_id: str
    task: OrchestrationTask
    crew: Crew
    pattern: PatternPlan
    consensus: ConsensusResult
    rounds: int
    status: str   # 'completed' | 'failed' | 'no_consensus'
    outputs: Dict[str, Any] = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task": self.task.to_dict(),
            "crew": self.crew.to_dict(),
            "pattern": self.pattern.to_dict(),
            "consensus": self.consensus.to_dict(),
            "rounds": self.rounds,
            "status": self.status,
            "outputs": dict(self.outputs),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
        }


# ----------------------------------------------------------------------
# Executor protocol (the LLM/tool backend behind each Agent)
# ----------------------------------------------------------------------

AgentExecutor = Callable[[Agent, Task, Dict[str, Any]], Any]


def default_executor(agent: Agent, task: Task, context: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic stub executor used when no LLM backend is wired.

    It produces a small JSON dict that:
      * names the agent (so tests can verify which agent ran which task),
      * echoes the goal + context (so we can assert on content),
      * includes a synthetic score/rationale so consensus can vote.

    Real deployments will swap this for a CrewAI-compatible executor
    that calls the platform's LLM provider.
    """
    description = task.description or task.expected_output or ""
    decision = _synthesize_decision(agent, description, context)
    return {
        "agent_id": agent.role,
        "agent_goal": agent.goal,
        "task": description,
        "decision": decision,
        "confidence": 0.85,
        "rationale": (
            f"Synthesized response from {agent.role} for: "
            f"{description[:60]}"
        ),
        "ts": time.time(),
    }


def _synthesize_decision(agent: Agent, description: str, context: Dict[str, Any]) -> Any:
    """Pick a decision shaped for the scenario.

    The decision is a *string* for non-scoring scenarios, and a *float
    score* for scoring scenarios. This lets the consensus aggregator
    vote on numeric scores without losing the rationale trail.
    """
    text = (description + " " + agent.role).lower()
    if any(k in text for k in ("score", "rating", "fit")):
        # base 70, +/- 15 depending on context keywords
        base = 70.0
        for boost in ("strong", "expert", "lead", "principal", "senior"):
            if boost in (description + " " + str(context)).lower():
                base += 7.5
        for drop in ("weak", "junior", "intern", "gap"):
            if drop in (description + " " + str(context)).lower():
                base -= 7.5
        return max(0.0, min(100.0, base))
    return f"response::{agent.role}::{description[:40]}"


# ----------------------------------------------------------------------
# Orchestrator
# ----------------------------------------------------------------------

class Orchestrator:
    """Runs ``OrchestrationTask`` instances against a role registry."""

    def __init__(
        self,
        registry: Optional[AgentRoleRegistry] = None,
        *,
        executor: Optional[AgentExecutor] = None,
        event_emitter: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        memory_writer: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        self.registry = registry or register_default_roles()
        self.executor = executor or default_executor
        self._emit = event_emitter
        self._write_memory = memory_writer

    # ---- introspection -----------------------------------------------

    def list_scenarios(self) -> List[ScenarioKind]:
        return list(ScenarioKind)

    # ---- main entry point --------------------------------------------

    def orchestrate(self, task: OrchestrationTask) -> OrchestrationResult:
        plan = build_pattern(
            task.scenario,
            consensus=task.consensus,
            max_rounds=task.max_rounds,
        )
        if task.pattern is not None:
            plan.pattern = task.pattern

        run_id = str(uuid.uuid4())
        crew = self._build_crew(plan)

        rounds = 0
        outputs: Dict[str, Any] = {}
        consensus: Optional[ConsensusResult] = None
        status = "completed"
        error: Optional[str] = None

        try:
            for round_idx in range(1, plan.max_rounds + 1):
                rounds = round_idx
                outputs = self._run_pattern(plan, crew, task, round_idx)

                if plan.pattern == CollaborationPattern.SEQUENTIAL:
                    # Sequential: last task's output is the answer.
                    final_step_kind = plan.steps[-1].role.kind.value
                    final_slot = outputs.get(final_step_kind)
                    final_value = final_slot.get("decision") if isinstance(final_slot, dict) else None
                    consensus = ConsensusResult(
                        strategy=plan.consensus,
                        decision=final_value,
                        confidence=0.9 if final_value is not None else 0.0,
                        reached=final_value is not None,
                        notes="sequential-final-task",
                    )
                    break

                # Parallel / hierarchical / debate: aggregate votes
                votes = self._collect_votes(plan, outputs)
                consensus = aggregate(plan.consensus, votes)

                if plan.pattern == CollaborationPattern.DEBATE:
                    if consensus.decision == "approved" or consensus.reached:
                        break
                    # else: loop one more round so writer can revise
                    if round_idx == plan.max_rounds:
                        status = "no_consensus"
                    continue

                # parallel / hierarchical
                if consensus.reached:
                    break
                if round_idx == plan.max_rounds:
                    status = "no_consensus"

        except Exception as exc:  # noqa: BLE001
            status = "failed"
            error = str(exc)
            logger.exception("orchestrator.failed run_id=%s", run_id)

        if consensus is None:
            consensus = ConsensusResult(
                strategy=plan.consensus,
                decision=None,
                confidence=0.0,
                reached=False,
                notes="no-outputs",
            )

        result = OrchestrationResult(
            run_id=run_id,
            task=task,
            crew=crew,
            pattern=plan,
            consensus=consensus,
            rounds=rounds,
            status=status,
            outputs=outputs,
            finished_at=time.time(),
            error=error,
        )

        self._post_run(result)
        return result

    # ---- async wrapper ------------------------------------------------

    async def aorchestrate(self, task: OrchestrationTask) -> OrchestrationResult:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.orchestrate, task)

    # ---- internals ----------------------------------------------------

    def _build_crew(self, plan: PatternPlan) -> Crew:
        agents: List[Agent] = []
        for step in plan.steps:
            agents.append(
                Agent(
                    role=step.role.title,
                    goal=step.role.goal,
                    backstory=step.role.backstory,
                    tools=list(step.role.tools),
                    allow_delegation=step.role.allow_delegation,
                    verbose=step.role.verbose,
                )
            )
        tasks: List[Task] = []
        for step, agent in zip(plan.steps, agents):
            tasks.append(
                Task(
                    description=step.description,
                    agent=agent,
                    expected_output=",".join(step.expected_output_keys),
                )
            )
        process_map = {
            CollaborationPattern.SEQUENTIAL: CrewProcess.SEQUENTIAL,
            CollaborationPattern.HIERARCHICAL: CrewProcess.HIERARCHICAL,
            # parallel / debate still run sequentially here, but each
            # task is logically independent — consensus drives the merge.
            CollaborationPattern.PARALLEL: CrewProcess.SEQUENTIAL,
            CollaborationPattern.DEBATE: CrewProcess.SEQUENTIAL,
        }
        return Crew(agents=agents, tasks=tasks, process=process_map[plan.pattern])

    def _run_pattern(
        self, plan: PatternPlan, crew: Crew,
        task: OrchestrationTask, round_idx: int,
    ) -> Dict[str, Any]:
        ctx = {**task.context, "round": round_idx, "goal": task.goal}
        outputs: Dict[str, Any] = {}

        if plan.pattern == CollaborationPattern.HIERARCHICAL:
            # First step = PM decomposition. Sub-tasks flow into the rest.
            pm_step = plan.steps[0]
            pm_out = self.executor(crew.agents[0], crew.tasks[0], ctx)
            outputs[pm_step.role.kind.value] = pm_out
            sub_tasks = pm_out.get("decision") or []
            if isinstance(sub_tasks, str):
                sub_tasks = [sub_tasks]
            ctx["sub_tasks"] = sub_tasks if isinstance(sub_tasks, list) else [sub_tasks]

            for step, agent, t in zip(plan.steps[1:], crew.agents[1:], crew.tasks[1:]):
                out = self.executor(agent, t, ctx)
                outputs[step.role.kind.value] = out
                ctx[step.role.kind.value] = out
            return outputs

        # sequential / parallel / debate
        for step, agent, t in zip(plan.steps, crew.agents, crew.tasks):
            out = self.executor(agent, t, ctx)
            outputs[step.role.kind.value] = out
            ctx[step.role.kind.value] = out

        # debate: if reviewer verdict is not "approved", mark outputs for revise
        if plan.pattern == CollaborationPattern.DEBATE and "bias_reviewer" in outputs:
            verdict = outputs["bias_reviewer"].get("decision")
            if verdict != "approved":
                outputs["_needs_revise"] = True
            else:
                outputs["_needs_revise"] = False
        return outputs

    def _collect_votes(self, plan: PatternPlan, outputs: Dict[str, Any]) -> List[ConsensusVote]:
        votes: List[ConsensusVote] = []
        for step in plan.steps:
            slot = outputs.get(step.role.kind.value)
            if not isinstance(slot, dict):
                continue
            votes.append(
                ConsensusVote(
                    agent_id=step.role.title,
                    decision=slot.get("decision"),
                    confidence=float(slot.get("confidence", 0.0)),
                    weight=step.weight,
                    rationale=str(slot.get("rationale", "")),
                )
            )
        return votes

    # ---- post-run side-effects ---------------------------------------

    def _post_run(self, result: OrchestrationResult) -> None:
        payload = {
            "run_id": result.run_id,
            "scenario": result.task.scenario.value,
            "status": result.status,
            "rounds": result.rounds,
            "decision": result.consensus.decision,
            "confidence": result.consensus.confidence,
            "tenant_id": result.task.tenant_id,
            "correlation_id": result.task.correlation_id,
        }
        if self._emit is not None:
            try:
                self._emit("multiagent.task.completed", payload)
            except Exception:  # noqa: BLE001
                logger.exception("orchestrator.emit_failed")
        else:
            self._safe_emit_bus(payload)

        if self._write_memory is not None:
            try:
                self._write_memory(payload)
            except Exception:  # noqa: BLE001
                logger.exception("orchestrator.memory_write_failed")
        else:
            self._safe_write_memory(payload)

    def _safe_emit_bus(self, payload: Dict[str, Any]) -> None:
        try:
            from eventbus.decorators import emit  # type: ignore
        except Exception:  # pragma: no cover
            return
        try:
            emit("multiagent.task.completed", payload, source="multiagent",
                 correlation_id=payload.get("correlation_id"))
        except Exception:  # noqa: BLE001
            logger.exception("orchestrator.emit_bus_failed")

    def _safe_write_memory(self, payload: Dict[str, Any]) -> None:
        try:
            from services.memory import get_memory_store  # type: ignore
        except Exception:  # pragma: no cover
            return
        try:
            store = get_memory_store()
            tenant_id = payload.get("tenant_id") or "00000000-0000-0000-0000-000000000000"
            user_id = payload.get("correlation_id") or payload.get("run_id")
            store.add(
                user_id=user_id,
                content=f"multiagent::{payload['scenario']}::{payload['status']}::{payload['decision']}",
                source_agent="multiagent.orchestrator",
                type="summary",
                tenant_id=tenant_id,
            )
        except Exception:  # noqa: BLE001
            logger.exception("orchestrator.memory_write_failed")


# ----------------------------------------------------------------------
# Singleton
# ----------------------------------------------------------------------

_ORCHESTRATOR: Optional[Orchestrator] = None


def get_orchestrator() -> Orchestrator:
    global _ORCHESTRATOR
    if _ORCHESTRATOR is None:
        _ORCHESTRATOR = Orchestrator()
    return _ORCHESTRATOR


def reset_orchestrator() -> None:
    global _ORCHESTRATOR
    _ORCHESTRATOR = None