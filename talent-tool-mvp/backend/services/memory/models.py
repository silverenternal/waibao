"""Memory data models — T2702.

Pydantic dataclasses describing the canonical memory record, the link
graph edge, and a typed query request. No vendor imports: stable shape
for the API and tests.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class MemoryType(str, Enum):
    FACT = "fact"            # objective fact about the user ("works at Acme")
    PREFERENCE = "preference"  # user preference ("prefers remote work")
    EVENT = "event"            # something that happened ("interviewed 2026-06-01")
    SUMMARY = "summary"        # LLM-generated summary of a session
    TASK = "task"              # todo / open question ("follow up on offer")
    EPISODIC = "episodic"      # episodic snapshot (linked to a turn / session)


class RelationType(str, Enum):
    RELATED = "related"
    FOLLOWS = "follows"
    CONTRADICTS = "contradicts"
    SUPPORTS = "supports"
    DERIVED_FROM = "derived_from"
    REFERENCES = "references"


class Memory(BaseModel):
    """Canonical memory record (mirrors `memories_v2` row)."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    content: str
    summary: Optional[str] = None
    embedding: Optional[list[float]] = None
    source_agent: str
    type: MemoryType = MemoryType.FACT
    confidence: float = 1.0
    decay_score: float = 1.0
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    is_archived: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        d = self.model_dump(mode="json")
        return d

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Memory":
        """Build a Memory from a Supabase row dict.

        Tolerates missing optional fields and the pgvector ``embedding`` being
        serialized as a string in some client versions.
        """
        emb = row.get("embedding")
        if isinstance(emb, str):
            try:
                import json as _json
                emb = _json.loads(emb)
            except Exception:
                emb = None
        return cls(
            id=row["id"],
            tenant_id=row["tenant_id"],
            user_id=row["user_id"],
            content=row["content"],
            summary=row.get("summary"),
            embedding=emb,
            source_agent=row["source_agent"],
            type=MemoryType(row.get("type", "fact")),
            confidence=float(row.get("confidence", 1.0)),
            decay_score=float(row.get("decay_score", 1.0)),
            access_count=int(row.get("access_count", 0)),
            last_accessed=row.get("last_accessed"),
            metadata=row.get("metadata") or {},
            is_archived=bool(row.get("is_archived", False)),
            created_at=row.get("created_at") or datetime.utcnow(),
            updated_at=row.get("updated_at") or datetime.utcnow(),
        )


class MemoryLink(BaseModel):
    """Edge in the memory graph."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    memory_id_a: uuid.UUID
    memory_id_b: uuid.UUID
    relation: RelationType = RelationType.RELATED
    weight: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class MemoryQuery(BaseModel):
    """Typed memory query (used by agent context injection)."""

    user_id: uuid.UUID
    query_text: str
    top_k: int = 10
    types: Optional[list[MemoryType]] = None
    min_confidence: float = 0.0
    min_decay: float = 0.0
    include_archived: bool = False
    include_links: bool = False
    metadata_filter: dict[str, Any] = Field(default_factory=dict)
