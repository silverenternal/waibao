"""Role catalogue + agent role registry (CrewAI vendor-in).

CrewAI's "Agent" has a ``role``, ``goal`` and ``backstory``. We mirror
those concepts but factor the *role* out as a first-class object so we
can re-use it across orchestrations and tests.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger("waibao.multiagent.roles")


# ----------------------------------------------------------------------
# Role primitives
# ----------------------------------------------------------------------

class RoleKind(str, Enum):
    """Built-in role kinds shipped by the platform."""

    PM = "pm"
    RESEARCHER = "researcher"
    WRITER = "writer"
    REVIEWER = "reviewer"
    EXECUTOR = "executor"
    TECH_SCORER = "tech_scorer"
    CULTURE_SCORER = "culture_scorer"
    DOMAIN_SCORER = "domain_scorer"
    BIAS_REVIEWER = "bias_reviewer"


@dataclass
class Role:
    """A CrewAI-style role descriptor."""

    kind: RoleKind
    title: str
    goal: str
    backstory: str
    tools: List[str] = field(default_factory=list)
    allow_delegation: bool = False
    verbose: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind.value,
            "title": self.title,
            "goal": self.goal,
            "backstory": self.backstory,
            "tools": list(self.tools),
            "allow_delegation": self.allow_delegation,
            "verbose": self.verbose,
        }


# ----------------------------------------------------------------------
# Default role presets
# ----------------------------------------------------------------------

ROLE_PRESETS: Dict[RoleKind, Role] = {
    RoleKind.PM: Role(
        kind=RoleKind.PM,
        title="Product Manager",
        goal="Break the high-level goal into atomic, well-scoped sub-tasks "
             "and route each sub-task to the right specialist agent.",
        backstory="A senior PM who has shipped dozens of recruiting products. "
                  "Pragmatic, data-driven, and ruthless about cutting scope.",
        tools=["plan_tracker", "workflow_store"],
        allow_delegation=True,
    ),
    RoleKind.RESEARCHER: Role(
        kind=RoleKind.RESEARCHER,
        title="Researcher",
        goal="Gather authoritative facts, market data, and prior precedents "
             "from internal knowledge bases and the open web.",
        backstory="Ex-management-consulting researcher. Skims a hundred sources "
                  "to surface the three that actually matter.",
        tools=["rag_search", "memory_recall", "web_search"],
    ),
    RoleKind.WRITER: Role(
        kind=RoleKind.WRITER,
        title="Writer",
        goal="Produce clear, on-brand, evidence-backed written artifacts "
             "(emails, JD drafts, summary reports).",
        backstory="A staff-level technical writer who turns dense findings "
                  "into 200-word messages that busy HR leaders will read.",
        tools=["tone_guide"],
    ),
    RoleKind.REVIEWER: Role(
        kind=RoleKind.REVIEWER,
        title="Reviewer",
        goal="Stress-test drafts for accuracy, safety, bias, tone, and "
             "compliance before they reach the end user.",
        backstory="Former compliance officer who has rejected 1000+ candidate "
                  "communications for the smallest legal or wording issues.",
        tools=["policy_check", "bias_scorer"],
    ),
    RoleKind.EXECUTOR: Role(
        kind=RoleKind.EXECUTOR,
        title="Executor",
        goal="Take a finalized decision and apply it via side-effect tools "
             "(send email, create ticket, update CRM).",
        backstory="An ops generalist who is fanatical about idempotency and "
                  "retry-safe operations.",
        tools=["notification", "ticket_service", "dingtalk_sync"],
    ),
    RoleKind.TECH_SCORER: Role(
        kind=RoleKind.TECH_SCORER,
        title="Technical Screener",
        goal="Evaluate a resume strictly on hard-skill match: languages, "
             "frameworks, system design, and depth.",
        backstory="A staff engineer who has interviewed 200+ candidates.",
    ),
    RoleKind.CULTURE_SCORER: Role(
        kind=RoleKind.CULTURE_SCORER,
        title="Culture Screener",
        goal="Evaluate a resume on values alignment, ownership, learning "
             "agility, and collaboration signals.",
        backstory="A people-ops partner with deep experience calibrating "
                  "across 5+ business units.",
    ),
    RoleKind.DOMAIN_SCORER: Role(
        kind=RoleKind.DOMAIN_SCORER,
        title="Domain Screener",
        goal="Evaluate industry-specific experience, vertical depth, and "
             "transferable patterns from prior roles.",
        backstory="A sector specialist (fintech / healthcare / e-commerce).",
    ),
    RoleKind.BIAS_REVIEWER: Role(
        kind=RoleKind.BIAS_REVIEWER,
        title="Bias Reviewer",
        goal="Catch demographic, age, gender, ethnicity, and school-name "
             "bias in agent-produced text before it reaches a candidate.",
        backstory="An employment-law-aware reviewer trained on a corpus of "
                  "10k+ rejected-but-undiverse job ads.",
        tools=["bias_scorer"],
    ),
}


# ----------------------------------------------------------------------
# Agent role registry
# ----------------------------------------------------------------------

@dataclass
class AgentRoleAssignment:
    """One row in the registry: an agent id (any string) bound to a role."""

    agent_id: str
    role: Role
    weight: float = 1.0
    tenant_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "role": self.role.to_dict(),
            "weight": self.weight,
            "tenant_id": self.tenant_id,
            "metadata": self.metadata,
        }


class AgentRoleRegistry:
    """In-memory registry mapping agent_id -> Role + weight.

    A real deployment might back this with Supabase, but the API is
    intentionally tiny so swapping is a one-class change.
    """

    def __init__(self) -> None:
        self._items: Dict[str, AgentRoleAssignment] = {}

    # ---- CRUD ---------------------------------------------------------

    def register(
        self,
        agent_id: str,
        role: Role,
        *,
        weight: float = 1.0,
        tenant_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AgentRoleAssignment:
        if weight <= 0:
            raise ValueError("weight must be > 0")
        assignment = AgentRoleAssignment(
            agent_id=agent_id,
            role=role,
            weight=weight,
            tenant_id=tenant_id,
            metadata=metadata or {},
        )
        self._items[agent_id] = assignment
        logger.debug(
            "multiagent.registry.register agent=%s role=%s weight=%.2f",
            agent_id, role.kind.value, weight,
        )
        return assignment

    def unregister(self, agent_id: str) -> bool:
        return self._items.pop(agent_id, None) is not None

    def get(self, agent_id: str) -> Optional[AgentRoleAssignment]:
        return self._items.get(agent_id)

    def list(self, *, role_kind: Optional[RoleKind] = None,
             tenant_id: Optional[str] = None) -> List[AgentRoleAssignment]:
        out: List[AgentRoleAssignment] = []
        for item in self._items.values():
            if role_kind is not None and item.role.kind != role_kind:
                continue
            if tenant_id is not None and item.tenant_id not in (None, tenant_id):
                continue
            out.append(item)
        return out

    def clear(self) -> None:
        self._items.clear()

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, agent_id: str) -> bool:
        return agent_id in self._items


# ----------------------------------------------------------------------
# Default role bootstrap
# ----------------------------------------------------------------------

def register_default_roles(
    registry: Optional[AgentRoleRegistry] = None,
    *,
    agent_ids: Optional[Dict[RoleKind, Iterable[str]]] = None,
) -> AgentRoleRegistry:
    """Register a small set of demo agents on the preset roles.

    Returns the registry. Safe to call multiple times — duplicate
    agent_ids are overwritten (last write wins).
    """
    reg = registry or AgentRoleRegistry()
    mapping = agent_ids or {
        RoleKind.PM: ["agent.pm.alice"],
        RoleKind.RESEARCHER: ["agent.researcher.bob"],
        RoleKind.WRITER: ["agent.writer.carol"],
        RoleKind.REVIEWER: ["agent.reviewer.dan"],
        RoleKind.EXECUTOR: ["agent.executor.eve"],
        RoleKind.TECH_SCORER: ["agent.tech.frank"],
        RoleKind.CULTURE_SCORER: ["agent.culture.grace"],
        RoleKind.DOMAIN_SCORER: ["agent.domain.heidi"],
        RoleKind.BIAS_REVIEWER: ["agent.bias.ivan"],
    }
    for kind, ids in mapping.items():
        role = ROLE_PRESETS[kind]
        for aid in ids:
            reg.register(aid, role)
    return reg