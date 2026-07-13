"""Consensus strategies for multi-agent voting.

We support four strategies:
  * majority   - >50% of agents agree on the same label/value
  * unanimous  - every agent agrees on the same label/value
  * weighted   - each agent vote carries weight * score, top score wins
  * quorum     - at least N agents must vote, then majority wins

Each strategy returns a ``ConsensusResult`` with the chosen decision,
the per-vote breakdown, and the confidence.
"""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Tuple


class ConsensusStrategy(str, Enum):
    MAJORITY = "majority"
    UNANIMOUS = "unanimous"
    WEIGHTED = "weighted"
    QUORUM = "quorum"


@dataclass
class ConsensusVote:
    """One agent's vote."""

    agent_id: str
    decision: Any
    confidence: float = 1.0
    weight: float = 1.0
    rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "decision": self.decision,
            "confidence": self.confidence,
            "weight": self.weight,
            "rationale": self.rationale,
        }


@dataclass
class ConsensusResult:
    """Output of an aggregation."""

    strategy: ConsensusStrategy
    decision: Any
    confidence: float
    votes: List[ConsensusVote] = field(default_factory=list)
    tally: Dict[Any, float] = field(default_factory=dict)
    reached: bool = True
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy": self.strategy.value,
            "decision": self.decision,
            "confidence": self.confidence,
            "votes": [v.to_dict() for v in self.votes],
            "tally": dict(self.tally),
            "reached": self.reached,
            "notes": self.notes,
        }


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _coerce_key(decision: Any) -> Any:
    """Cast unhashable decisions into a stable string key for tallying."""
    if isinstance(decision, (str, int, float, bool, tuple)):
        return decision
    return repr(decision)


def _score_confidence(votes: Iterable[ConsensusVote],
                      key: Any, *, weighted: bool = False) -> float:
    """Average confidence of votes whose decision matches ``key``."""
    relevant = [v for v in votes if _coerce_key(v.decision) == key]
    if not relevant:
        return 0.0
    if weighted:
        total_w = sum(v.weight for v in relevant) or 1.0
        return sum(v.confidence * v.weight for v in relevant) / total_w
    return statistics.fmean(v.confidence for v in relevant)


# ----------------------------------------------------------------------
# Aggregators
# ----------------------------------------------------------------------

def aggregate_majority(votes: List[ConsensusVote]) -> ConsensusResult:
    """Pick the decision with >50% of votes (unweighted)."""
    if not votes:
        return ConsensusResult(
            strategy=ConsensusStrategy.MAJORITY,
            decision=None,
            confidence=0.0,
            reached=False,
            notes="no votes",
        )

    counts = Counter(_coerce_key(v.decision) for v in votes)
    top_key, top_count = counts.most_common(1)[0]
    total = sum(counts.values())
    ratio = top_count / total

    if ratio <= 0.5:
        # Try with confidence-weighted dominance as a tie-break.
        weighted_tally: Dict[Any, float] = defaultdict(float)
        for v in votes:
            weighted_tally[_coerce_key(v.decision)] += v.confidence
        top_key = max(weighted_tally.items(), key=lambda x: x[1])[0]
        ratio = weighted_tally[top_key] / sum(weighted_tally.values())

    decision = next(
        (v.decision for v in votes if _coerce_key(v.decision) == top_key),
        top_key,
    )
    confidence = _score_confidence(votes, top_key)

    return ConsensusResult(
        strategy=ConsensusStrategy.MAJORITY,
        decision=decision,
        confidence=round(confidence, 4),
        votes=list(votes),
        tally={k: float(v) for k, v in counts.items()},
        reached=ratio > 0.5,
        notes=f"top={top_key!r} ratio={ratio:.2f}",
    )


def aggregate_unanimous(votes: List[ConsensusVote]) -> ConsensusResult:
    """All votes must agree on the same decision."""
    if not votes:
        return ConsensusResult(
            strategy=ConsensusStrategy.UNANIMOUS,
            decision=None,
            confidence=0.0,
            reached=False,
            notes="no votes",
        )
    keys = {_coerce_key(v.decision) for v in votes}
    reached = len(keys) == 1
    decision = votes[0].decision if reached else None
    confidence = _score_confidence(votes, _coerce_key(decision)) if reached else 0.0
    return ConsensusResult(
        strategy=ConsensusStrategy.UNANIMOUS,
        decision=decision,
        confidence=round(confidence, 4),
        votes=list(votes),
        tally={k: 1.0 for k in keys},
        reached=reached,
        notes=f"distinct={len(keys)}",
    )


def aggregate_weighted(votes: List[ConsensusVote]) -> ConsensusResult:
    """Sum confidence * weight per decision; highest wins."""
    if not votes:
        return ConsensusResult(
            strategy=ConsensusStrategy.WEIGHTED,
            decision=None,
            confidence=0.0,
            reached=False,
            notes="no votes",
        )

    tally: Dict[Any, float] = defaultdict(float)
    for v in votes:
        tally[_coerce_key(v.decision)] += v.confidence * v.weight
    top_key = max(tally.items(), key=lambda x: x[1])[0]
    total = sum(tally.values()) or 1.0
    decision = next(
        (v.decision for v in votes if _coerce_key(v.decision) == top_key),
        top_key,
    )
    confidence = _score_confidence(votes, top_key, weighted=True)

    return ConsensusResult(
        strategy=ConsensusStrategy.WEIGHTED,
        decision=decision,
        confidence=round(confidence, 4),
        votes=list(votes),
        tally={k: round(v, 4) for k, v in tally.items()},
        reached=True,
        notes=f"top={top_key!r} share={tally[top_key] / total:.2f}",
    )


def aggregate_quorum(votes: List[ConsensusVote], *,
                     quorum: int = 2) -> ConsensusResult:
    """Require at least ``quorum`` votes, then majority wins."""
    if len(votes) < quorum:
        return ConsensusResult(
            strategy=ConsensusStrategy.QUORUM,
            decision=None,
            confidence=0.0,
            votes=list(votes),
            reached=False,
            notes=f"quorum not met ({len(votes)}/{quorum})",
        )
    base = aggregate_majority(votes)
    return ConsensusResult(
        strategy=ConsensusStrategy.QUORUM,
        decision=base.decision,
        confidence=base.confidence,
        votes=base.votes,
        tally=base.tally,
        reached=base.reached,
        notes=f"quorum met ({len(votes)}/{quorum}) :: {base.notes}",
    )


# ----------------------------------------------------------------------
# Strategy dispatcher
# ----------------------------------------------------------------------

def aggregate(strategy: ConsensusStrategy,
              votes: List[ConsensusVote],
              *, quorum: int = 2) -> ConsensusResult:
    if strategy == ConsensusStrategy.MAJORITY:
        return aggregate_majority(votes)
    if strategy == ConsensusStrategy.UNANIMOUS:
        return aggregate_unanimous(votes)
    if strategy == ConsensusStrategy.WEIGHTED:
        return aggregate_weighted(votes)
    if strategy == ConsensusStrategy.QUORUM:
        return aggregate_quorum(votes, quorum=quorum)
    raise ValueError(f"unknown strategy: {strategy!r}")