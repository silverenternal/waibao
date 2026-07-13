"""T2703: Multi-Agent Orchestration (CrewAI vendor-in).

Public surface (matches the task spec):
  * Role / RoleKind / ROLE_PRESETS           - role catalogue
  * AgentRoleRegistry                         - registers which agent performs which role
  * ConsensusStrategy / ConsensusResult       - voting primitives
  * CollaborationPattern / ScenarioKind       - workflow patterns
  * Orchestrator                              - the CrewAI-backed orchestrator
  * get_orchestrator / reset_orchestrator     - singleton access

Design notes:
  * Vendors CrewAI semantics but ships a deterministic in-memory backend so
    the test suite has no external dependencies.
  * The orchestrator emits `multiagent.task.completed` to the existing
    EventBus and writes a shared context chunk to the MemoryStore so
    downstream agents can pick up where the previous round left off.
"""
from __future__ import annotations

from .consensus import (
    ConsensusResult,
    ConsensusStrategy,
    ConsensusVote,
    aggregate,
    aggregate_majority,
    aggregate_quorum,
    aggregate_unanimous,
    aggregate_weighted,
)
from .orchestrator import (
    Orchestrator,
    OrchestrationResult,
    OrchestrationTask,
    get_orchestrator,
    reset_orchestrator,
)
from .patterns import (
    CollaborationPattern,
    ScenarioKind,
    build_pattern,
)
from .roles import (
    ROLE_PRESETS,
    AgentRoleAssignment,
    AgentRoleRegistry,
    Role,
    RoleKind,
    register_default_roles,
)

__all__: list[str] = [
    # roles
    "Role",
    "RoleKind",
    "ROLE_PRESETS",
    "AgentRoleAssignment",
    "AgentRoleRegistry",
    "register_default_roles",
    # consensus
    "ConsensusStrategy",
    "ConsensusVote",
    "ConsensusResult",
    "aggregate",
    "aggregate_majority",
    "aggregate_weighted",
    "aggregate_unanimous",
    "aggregate_quorum",
    # patterns
    "CollaborationPattern",
    "ScenarioKind",
    "build_pattern",
    # orchestrator
    "Orchestrator",
    "OrchestrationTask",
    "OrchestrationResult",
    "get_orchestrator",
    "reset_orchestrator",
]