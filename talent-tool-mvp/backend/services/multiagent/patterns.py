"""Collaboration patterns — how agents are wired into a crew.

CrewAI uses "process" (sequential / hierarchical) but we generalize:
  * sequential   - agent1 -> agent2 -> ... -> agentN
  * parallel     - run all agents in parallel, aggregate via consensus
  * hierarchical - PM routes sub-tasks to specialists, then aggregates
  * debate       - writer produces draft, reviewer challenges, writer revises
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from .consensus import ConsensusStrategy
from .roles import Role, RoleKind

logger = logging.getLogger("waibao.multiagent.patterns")


class CollaborationPattern(str, Enum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    HIERARCHICAL = "hierarchical"
    DEBATE = "debate"


class ScenarioKind(str, Enum):
    """The four core scenarios in the T2703 spec."""

    RESUME_SCORING = "resume_scoring"
    BIAS_REVIEW = "bias_review"
    OFFER_NEGOTIATION = "offer_negotiation"
    STRATEGY_DECODE = "strategy_decode"


@dataclass
class StepPlan:
    """One executable step in a pattern."""

    role: Role
    agent_id: Optional[str] = None
    description: str = ""
    expected_output_keys: Tuple[str, ...] = ()
    weight: float = 1.0


@dataclass
class PatternPlan:
    """Full plan produced by `build_pattern`."""

    scenario: ScenarioKind
    pattern: CollaborationPattern
    consensus: ConsensusStrategy
    steps: List[StepPlan] = field(default_factory=list)
    max_rounds: int = 3
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario": self.scenario.value,
            "pattern": self.pattern.value,
            "consensus": self.consensus.value,
            "max_rounds": self.max_rounds,
            "description": self.description,
            "steps": [
                {
                    "role": s.role.to_dict(),
                    "agent_id": s.agent_id,
                    "description": s.description,
                    "expected_output_keys": list(s.expected_output_keys),
                    "weight": s.weight,
                }
                for s in self.steps
            ],
        }


# ----------------------------------------------------------------------
# Pattern builder
# ----------------------------------------------------------------------

def build_pattern(
    scenario: ScenarioKind,
    *,
    consensus: Optional[ConsensusStrategy] = None,
    max_rounds: int = 3,
) -> PatternPlan:
    """Return the canonical plan for one of the four core scenarios.

    Each scenario has:
      * a default pattern,
      * the steps that need to run (with roles),
      * the consensus strategy for tie-breaking.
    """
    if scenario == ScenarioKind.RESUME_SCORING:
        return PatternPlan(
            scenario=scenario,
            pattern=CollaborationPattern.PARALLEL,
            consensus=consensus or ConsensusStrategy.WEIGHTED,
            max_rounds=max_rounds,
            description="3 screeners independently score the resume; weighted vote picks the final score.",
            steps=[
                StepPlan(
                    role=Role(
                        kind=RoleKind.TECH_SCORER,
                        title="Technical Screener",
                        goal="Score hard-skill fit 0..100.",
                        backstory="Staff engineer.",
                    ),
                    description="Score technical fit",
                    expected_output_keys=("score", "rationale"),
                    weight=2.0,
                ),
                StepPlan(
                    role=Role(
                        kind=RoleKind.CULTURE_SCORER,
                        title="Culture Screener",
                        goal="Score values alignment 0..100.",
                        backstory="People-ops partner.",
                    ),
                    description="Score culture fit",
                    expected_output_keys=("score", "rationale"),
                    weight=1.0,
                ),
                StepPlan(
                    role=Role(
                        kind=RoleKind.DOMAIN_SCORER,
                        title="Domain Screener",
                        goal="Score industry/vertical fit 0..100.",
                        backstory="Sector specialist.",
                    ),
                    description="Score domain fit",
                    expected_output_keys=("score", "rationale"),
                    weight=1.5,
                ),
            ],
        )

    if scenario == ScenarioKind.BIAS_REVIEW:
        return PatternPlan(
            scenario=scenario,
            pattern=CollaborationPattern.DEBATE,
            consensus=consensus or ConsensusStrategy.UNANIMOUS,
            max_rounds=max_rounds,
            description="Writer drafts, BiasReviewer challenges, then revises until approved.",
            steps=[
                StepPlan(
                    role=Role(
                        kind=RoleKind.WRITER,
                        title="Writer",
                        goal="Draft candidate-facing communication.",
                        backstory="Staff technical writer.",
                    ),
                    description="Draft initial text",
                    expected_output_keys=("draft",),
                    weight=1.0,
                ),
                StepPlan(
                    role=Role(
                        kind=RoleKind.BIAS_REVIEWER,
                        title="Bias Reviewer",
                        goal="Detect and reject biased phrasing.",
                        backstory="Employment-law-aware reviewer.",
                    ),
                    description="Review for bias",
                    expected_output_keys=("issues", "verdict"),
                    weight=2.0,
                ),
            ],
        )

    if scenario == ScenarioKind.OFFER_NEGOTIATION:
        return PatternPlan(
            scenario=scenario,
            pattern=CollaborationPattern.SEQUENTIAL,
            consensus=consensus or ConsensusStrategy.MAJORITY,
            max_rounds=max_rounds,
            description="Researcher gathers market data, Writer drafts offer, Reviewer signs off.",
            steps=[
                StepPlan(
                    role=Role(
                        kind=RoleKind.RESEARCHER,
                        title="Researcher",
                        goal="Pull salary benchmarks and candidate signals.",
                        backstory="Ex-consulting researcher.",
                    ),
                    description="Research market + candidate",
                    expected_output_keys=("benchmarks", "candidate_context"),
                    weight=1.0,
                ),
                StepPlan(
                    role=Role(
                        kind=RoleKind.WRITER,
                        title="Writer",
                        goal="Compose the offer package + talking points.",
                        backstory="Staff writer.",
                    ),
                    description="Draft offer package",
                    expected_output_keys=("offer", "talking_points"),
                    weight=1.0,
                ),
                StepPlan(
                    role=Role(
                        kind=RoleKind.REVIEWER,
                        title="Reviewer",
                        goal="Validate policy/legal/safety on the offer.",
                        backstory="Compliance officer.",
                    ),
                    description="Final review",
                    expected_output_keys=("verdict", "issues"),
                    weight=2.0,
                ),
            ],
        )

    if scenario == ScenarioKind.STRATEGY_DECODE:
        return PatternPlan(
            scenario=scenario,
            pattern=CollaborationPattern.HIERARCHICAL,
            consensus=consensus or ConsensusStrategy.MAJORITY,
            max_rounds=max_rounds,
            description="PM decomposes the strategic question into sub-tasks, "
                        "delegates to specialists, then aggregates a final review.",
            steps=[
                StepPlan(
                    role=Role(
                        kind=RoleKind.PM,
                        title="Product Manager",
                        goal="Decompose the strategic question.",
                        backstory="Senior PM.",
                    ),
                    description="Decompose goal",
                    expected_output_keys=("sub_tasks",),
                    weight=2.0,
                ),
                StepPlan(
                    role=Role(
                        kind=RoleKind.WRITER,
                        title="Writer",
                        goal="Produce a written synthesis.",
                        backstory="Staff writer.",
                    ),
                    description="Produce written synthesis",
                    expected_output_keys=("narrative",),
                    weight=1.0,
                ),
                StepPlan(
                    role=Role(
                        kind=RoleKind.RESEARCHER,
                        title="Researcher",
                        goal="Back claims with citations.",
                        backstory="Ex-consulting researcher.",
                    ),
                    description="Back claims with citations",
                    expected_output_keys=("citations",),
                    weight=1.5,
                ),
                StepPlan(
                    role=Role(
                        kind=RoleKind.REVIEWER,
                        title="Reviewer",
                        goal="Aggregate + final QA.",
                        backstory="Compliance officer.",
                    ),
                    description="Aggregate + final QA",
                    expected_output_keys=("final", "issues"),
                    weight=2.0,
                ),
            ],
        )

    raise ValueError(f"unknown scenario: {scenario!r}")