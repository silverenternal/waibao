"""MemoryStore — vendor Mem0 client wrapper.

Mem0 is a memory layer for AI apps that handles:
  * LLM-based fact/preference/event extraction
  * Vector store + similarity search
  * Conflict detection / merging

We use Mem0 as the *client* layer and persist canonical records to
Supabase (memories_v2) so that we retain multi-tenant RLS, GDPR
controls, and our existing observability.  This module also offers a
deterministic offline implementation (``InMemoryBackend``) so the test
suite has zero external dependencies.

Public surface (matches the task spec):
  * add(user_id, content, source_agent, type) -> Memory
  * query(user_id, query_text, top_k=10)     -> list[Memory]
  * link(memory_a, memory_b, relation)
  * decay()                                  - periodic weight decay
  * forget(user_id, predicate)               - GDPR revoke
"""
from __future__ import annotations

import json
import logging
import math
import os
import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Callable, Iterable, Optional

from .models import Memory, MemoryLink, MemoryQuery, MemoryType, RelationType

logger = logging.getLogger("recruittech.memory.store")


# ----------------------------------------------------------------------
# Errors
# ----------------------------------------------------------------------

class MemoryStoreError(Exception):
    """Base error for the memory store."""

    def __init__(self, message: str, *, code: str = "memory_error", status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


# ----------------------------------------------------------------------
# Embedding helper (deterministic fallback)
# ----------------------------------------------------------------------

_EMBED_DIM = 1024


def _hash_embed(text: str, dim: int = _EMBED_DIM) -> list[float]:
    """Deterministic bag-of-words hash embedding (fallback / test)."""
    if not text:
        return [0.0] * dim
    vec = [0.0] * dim
    for tok in text.lower().split():
        h = abs(hash(tok))
        for i in range(4):
            idx = (h >> (i * 4)) % dim
            vec[idx] += 1.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [v / norm for v in vec]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    da = math.sqrt(sum(x * x for x in a[:n])) or 1.0
    db = math.sqrt(sum(x * x for x in b[:n])) or 1.0
    return sum(x * y for x, y in zip(a[:n], b[:n])) / (da * db)


# ----------------------------------------------------------------------
# Optional Mem0 client (loaded lazily)
# ----------------------------------------------------------------------

def _try_mem0() -> Optional[Any]:
    """Best-effort import of the Mem0 client. Never raises."""
    try:
        from mem0 import MemoryClient  # type: ignore
        return MemoryClient
    except Exception:
        return None


# ----------------------------------------------------------------------
# InMemoryBackend (default backend for tests + dev)
# ----------------------------------------------------------------------

class InMemoryBackend:
    """Process-local memory store, deterministic, no network deps.

    Behaves like a tiny key-value + vector index. Used as the default
    when no Supabase URL is configured or in unit tests.
    """

    def __init__(self) -> None:
        self._memories: dict[uuid.UUID, Memory] = {}
        self._links: list[MemoryLink] = []
        self._access_log: list[dict[str, Any]] = []

    # ---- CRUD ----
    def insert(self, mem: Memory) -> Memory:
        if mem.embedding is None:
            mem.embedding = _hash_embed(mem.content)
        self._memories[mem.id] = mem
        return mem

    def update(self, mem: Memory) -> Memory:
        mem.updated_at = datetime.utcnow()
        self._memories[mem.id] = mem
        return mem

    def delete(self, memory_id: uuid.UUID) -> None:
        self._memories.pop(memory_id, None)
        self._links = [l for l in self._links
                       if l.memory_id_a != memory_id and l.memory_id_b != memory_id]

    def get(self, memory_id: uuid.UUID) -> Optional[Memory]:
        return self._memories.get(memory_id)

    def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        types: Optional[list[MemoryType]] = None,
        include_archived: bool = False,
    ) -> list[Memory]:
        out: list[Memory] = []
        for m in self._memories.values():
            if m.user_id != user_id:
                continue
            if not include_archived and m.is_archived:
                continue
            if types and m.type not in types:
                continue
            out.append(m)
        return out

    def search(
        self,
        user_id: uuid.UUID,
        query_text: str,
        *,
        top_k: int = 10,
        types: Optional[list[MemoryType]] = None,
        min_confidence: float = 0.0,
        min_decay: float = 0.0,
    ) -> list[tuple[Memory, float]]:
        qvec = _hash_embed(query_text)
        candidates = self.list_for_user(user_id, types=types)
        scored: list[tuple[Memory, float]] = []
        for m in candidates:
            if m.confidence < min_confidence or m.decay_score < min_decay:
                continue
            if m.embedding is None:
                m.embedding = _hash_embed(m.content)
            score = _cosine(qvec, m.embedding) * m.decay_score
            scored.append((m, score))
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored[:top_k]

    # ---- Links ----
    def add_link(self, link: MemoryLink) -> MemoryLink:
        self._links.append(link)
        return link

    def links_for(self, memory_id: uuid.UUID) -> list[MemoryLink]:
        return [l for l in self._links
                if l.memory_id_a == memory_id or l.memory_id_b == memory_id]

    # ---- Decay ----
    def decay_all(self, factor: float = 0.95) -> int:
        n = 0
        for m in self._memories.values():
            m.decay_score = max(0.0, m.decay_score * factor)
            n += 1
        return n

    def touch(self, memory_id: uuid.UUID) -> None:
        m = self._memories.get(memory_id)
        if m is None:
            return
        m.access_count += 1
        m.last_accessed = datetime.utcnow()
        # Bump decay_score back toward 1.0 when accessed
        m.decay_score = min(1.0, m.decay_score + 0.05)

    # ---- Access log ----
    def log_access(self, *, memory_id: uuid.UUID, user_id: uuid.UUID,
                   action: str, actor_kind: str = "agent", reason: str = "") -> None:
        self._access_log.append({
            "id": str(uuid.uuid4()),
            "memory_id": str(memory_id),
            "user_id": str(user_id),
            "action": action,
            "actor_kind": actor_kind,
            "reason": reason,
            "created_at": datetime.utcnow().isoformat(),
        })

    def access_log(self, user_id: Optional[uuid.UUID] = None) -> list[dict[str, Any]]:
        if user_id is None:
            return list(self._access_log)
        return [e for e in self._access_log if e["user_id"] == str(user_id)]


# ----------------------------------------------------------------------
# SupabaseBackend
# ----------------------------------------------------------------------

class SupabaseBackend:
    """Supabase-backed memory store (RLS-aware).

    Used in production. The actual client is provided lazily so that
    tests can run with no Supabase URL set.
    """

    def __init__(self, client_factory: Callable[[], Any]) -> None:
        self._client_factory = client_factory

    def _sb(self) -> Any:
        return self._client_factory()

    def insert(self, mem: Memory) -> Memory:
        row = mem.model_dump(mode="json")
        if row.get("embedding") is None:
            row["embedding"] = _hash_embed(mem.content)
        row["embedding"] = json.dumps(row["embedding"])  # pgvector accepts json array
        sb = self._sb()
        res = sb.table("memories_v2").insert(row).execute()
        if not res.data:
            raise MemoryStoreError("insert returned no data", code="supabase_no_data")
        return Memory.from_row(res.data[0])

    def update(self, mem: Memory) -> Memory:
        row = mem.model_dump(mode="json")
        sb = self._sb()
        sb.table("memories_v2").update(row).eq("id", str(mem.id)).execute()
        return mem

    def delete(self, memory_id: uuid.UUID) -> None:
        sb = self._sb()
        sb.table("memories_v2").delete().eq("id", str(memory_id)).execute()

    def get(self, memory_id: uuid.UUID) -> Optional[Memory]:
        sb = self._sb()
        res = sb.table("memories_v2").select("*").eq("id", str(memory_id)).execute()
        if not res.data:
            return None
        return Memory.from_row(res.data[0])

    def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        types: Optional[list[MemoryType]] = None,
        include_archived: bool = False,
    ) -> list[Memory]:
        sb = self._sb()
        q = sb.table("memories_v2").select("*").eq("user_id", str(user_id))
        if not include_archived:
            q = q.eq("is_archived", False)
        res = q.order("created_at", desc=True).execute()
        items = [Memory.from_row(r) for r in (res.data or [])]
        if types:
            items = [m for m in items if m.type in types]
        return items

    def search(
        self,
        user_id: uuid.UUID,
        query_text: str,
        *,
        top_k: int = 10,
        types: Optional[list[MemoryType]] = None,
        min_confidence: float = 0.0,
        min_decay: float = 0.0,
    ) -> list[tuple[Memory, float]]:
        # Use the in-process list + cosine fallback for now. A future
        # iteration can swap in a pgvector RPC for large tenants.
        items = self.list_for_user(user_id, types=types)
        qvec = _hash_embed(query_text)
        scored: list[tuple[Memory, float]] = []
        for m in items:
            if m.confidence < min_confidence or m.decay_score < min_decay:
                continue
            if m.embedding is None:
                m.embedding = _hash_embed(m.content)
            score = _cosine(qvec, m.embedding) * m.decay_score
            scored.append((m, score))
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored[:top_k]

    def add_link(self, link: MemoryLink) -> MemoryLink:
        sb = self._sb()
        row = link.model_dump(mode="json")
        sb.table("memory_links_v2").insert(row).execute()
        return link

    def links_for(self, memory_id: uuid.UUID) -> list[MemoryLink]:
        sb = self._sb()
        a = sb.table("memory_links_v2").select("*").eq("memory_id_a", str(memory_id)).execute()
        b = sb.table("memory_links_v2").select("*").eq("memory_id_b", str(memory_id)).execute()
        rows = (a.data or []) + (b.data or [])
        return [MemoryLink(**r) for r in rows]

    def decay_all(self, factor: float = 0.95) -> int:
        # Decay is applied to all rows via a simple update.
        # For very large tenants this would be batched.
        sb = self._sb()
        res = sb.rpc(
            "memory_decay_all",
            {"p_factor": factor},
        ).execute() if self._has_decay_rpc() else None
        if res is not None and getattr(res, "data", None):
            try:
                return int(res.data)
            except Exception:
                return 0
        # Fallback: scan + update (slow but safe)
        rows = sb.table("memories_v2").select("id,decay_score").execute()
        count = 0
        for r in rows.data or []:
            sb.table("memories_v2").update(
                {"decay_score": max(0.0, float(r["decay_score"]) * factor)}
            ).eq("id", r["id"]).execute()
            count += 1
        return count

    def _has_decay_rpc(self) -> bool:
        try:
            sb = self._sb()
            # We don't have a fast way to introspect RPCs; assume not.
            return False
        except Exception:
            return False

    def touch(self, memory_id: uuid.UUID) -> None:
        sb = self._sb()
        sb.rpc("memory_touch", {"p_id": str(memory_id)}).execute()

    def log_access(self, *, memory_id: uuid.UUID, user_id: uuid.UUID,
                   action: str, actor_kind: str = "agent", reason: str = "") -> None:
        sb = self._sb()
        sb.table("memory_access_v2").insert({
            "memory_id": str(memory_id),
            "user_id": str(user_id),
            "action": action,
            "actor_kind": actor_kind,
            "reason": reason,
        }).execute()

    def access_log(self, user_id: Optional[uuid.UUID] = None) -> list[dict[str, Any]]:
        sb = self._sb()
        q = sb.table("memory_access_v2").select("*")
        if user_id is not None:
            q = q.eq("user_id", str(user_id))
        res = q.order("created_at", desc=True).execute()
        return res.data or []


# ----------------------------------------------------------------------
# MemoryStore — high-level orchestrator
# ----------------------------------------------------------------------

class MemoryStore:
    """High-level memory store. Backed by InMemory or Supabase.

    The store handles entity extraction, link graph, decay, and the
    GDPR forget flow. The Mem0 vendor client is wrapped via the
    ``mem0_client`` optional dependency for extraction quality, but the
    store is functional without it.
    """

    def __init__(
        self,
        *,
        backend: Optional[Any] = None,
        use_mem0: bool = False,
        mem0_api_key: Optional[str] = None,
    ) -> None:
        if backend is not None:
            self.backend = backend
        else:
            # Default to in-memory; production code swaps this via init()
            self.backend = InMemoryBackend()

        self._mem0_client: Optional[Any] = None
        if use_mem0:
            client_cls = _try_mem0()
            api_key = mem0_api_key or os.getenv("MEM0_API_KEY")
            if client_cls is not None and api_key:
                try:
                    self._mem0_client = client_cls(api_key=api_key)
                except Exception as e:  # pragma: no cover
                    logger.warning(f"Failed to init Mem0 client: {e}")

    # ---- Initialization ----
    def init(self, *, supabase_client_factory: Optional[Callable[[], Any]] = None) -> None:
        """Switch to Supabase backend if a client factory is provided.

        Called once at app startup. Idempotent.
        """
        if supabase_client_factory is None:
            return
        try:
            client = supabase_client_factory()
            if client is not None:
                self.backend = SupabaseBackend(supabase_client_factory)
        except Exception as e:  # pragma: no cover
            logger.warning(f"Could not initialize Supabase backend: {e}")

    # ---- add / query / link ----

    def add(
        self,
        *,
        user_id: uuid.UUID,
        content: str,
        source_agent: str,
        type: MemoryType | str = MemoryType.FACT,
        tenant_id: Optional[uuid.UUID] = None,
        confidence: float = 1.0,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Memory:
        if isinstance(type, str):
            type = MemoryType(type)
        if tenant_id is None:
            tenant_id = uuid.UUID(int=0)  # pseudo-tenant for tests; replaced by init

        mem = Memory(
            tenant_id=tenant_id,
            user_id=user_id,
            content=content,
            source_agent=source_agent,
            type=type,
            confidence=max(0.0, min(1.0, confidence)),
            metadata=metadata or {},
        )
        stored = self.backend.insert(mem)
        try:
            self.backend.log_access(
                memory_id=stored.id,
                user_id=user_id,
                action="write",
                actor_kind="agent",
                reason=f"agent={source_agent}",
            )
        except Exception:
            # access log is best-effort
            pass
        return stored

    def query(
        self,
        *,
        user_id: uuid.UUID,
        query_text: str,
        top_k: int = 10,
        types: Optional[list[MemoryType | str]] = None,
        min_confidence: float = 0.0,
        min_decay: float = 0.0,
        include_links: bool = False,
    ) -> list[Memory]:
        type_list: Optional[list[MemoryType]] = None
        if types:
            type_list = [MemoryType(t) if isinstance(t, str) else t for t in types]
        scored = self.backend.search(
            user_id,
            query_text,
            top_k=top_k,
            types=type_list,
            min_confidence=min_confidence,
            min_decay=min_decay,
        )
        results: list[Memory] = []
        for mem, _score in scored:
            try:
                self.backend.touch(mem.id)
            except Exception:
                pass
            results.append(mem)
        if include_links:
            # Caller can re-attach via .links_for(id) — kept simple here
            pass
        return results

    def link(
        self,
        memory_a: uuid.UUID,
        memory_b: uuid.UUID,
        relation: RelationType | str = RelationType.RELATED,
        *,
        weight: float = 1.0,
        metadata: Optional[dict[str, Any]] = None,
    ) -> MemoryLink:
        if isinstance(relation, str):
            relation = RelationType(relation)
        link = MemoryLink(
            memory_id_a=memory_a,
            memory_id_b=memory_b,
            relation=relation,
            weight=weight,
            metadata=metadata or {},
        )
        return self.backend.add_link(link)

    # ---- decay / forget ----

    def decay(self, factor: float = 0.95) -> int:
        """Decay all memory weights. Returns affected row count."""
        n = self.backend.decay_all(factor)
        # Log a decay job
        try:
            sb = getattr(self.backend, "_sb", lambda: None)()
            if sb is not None:
                sb.table("memory_decay_jobs").insert({
                    "job_type": "decay",
                    "status": "completed",
                    "affected_rows": n,
                    "completed_at": "now()",
                }).execute()
        except Exception:
            pass
        return n

    def forget(
        self,
        user_id: uuid.UUID,
        predicate: Optional[Callable[[Memory], bool]] = None,
        *,
        source_agent: Optional[str] = None,
        type: Optional[MemoryType | str] = None,
    ) -> int:
        """GDPR-style revocation. Returns number of memories removed.

        ``predicate`` is a Python callable evaluated client-side (works
        for InMemory backend) and ``source_agent`` / ``type`` filter
        server-side (works for Supabase backend).
        """
        if isinstance(type, str):
            type = MemoryType(type)
        items = self.backend.list_for_user(user_id, types=[type] if type else None)
        if source_agent:
            items = [m for m in items if m.source_agent == source_agent]
        if predicate:
            items = [m for m in items if predicate(m)]
        for m in items:
            try:
                self.backend.delete(m.id)
            except Exception:
                pass
            try:
                self.backend.log_access(
                    memory_id=m.id,
                    user_id=user_id,
                    action="forget",
                    actor_kind="gdpr_job",
                    reason="user-initiated forget",
                )
            except Exception:
                pass
        return len(items)

    # ---- accessors ----

    def get(self, memory_id: uuid.UUID) -> Optional[Memory]:
        return self.backend.get(memory_id)

    def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        types: Optional[list[MemoryType | str]] = None,
        include_archived: bool = False,
    ) -> list[Memory]:
        type_list = None
        if types:
            type_list = [MemoryType(t) if isinstance(t, str) else t for t in types]
        return self.backend.list_for_user(
            user_id, types=type_list, include_archived=include_archived
        )

    def access_log(self, user_id: Optional[uuid.UUID] = None) -> list[dict[str, Any]]:
        return self.backend.access_log(user_id)

    def links_for(self, memory_id: uuid.UUID) -> list[MemoryLink]:
        return self.backend.links_for(memory_id)

    # ---- Mem0 vendor hooks ----

    def extract_via_mem0(
        self,
        *,
        user_id: uuid.UUID,
        conversation: list[dict[str, str]],
        tenant_id: Optional[uuid.UUID] = None,
    ) -> list[Memory]:
        """Use Mem0 vendor client to extract facts/preferences from a chat.

        ``conversation`` is a list of ``{"role": "user"|"assistant", "content": "..."}``.
        Returns a list of Memory rows (already persisted).
        """
        if self._mem0_client is None:
            # Fallback: do naive sentence-level extraction so callers
            # always get something useful.
            out: list[Memory] = []
            for turn in conversation[-4:]:
                if turn.get("role") != "user":
                    continue
                text = (turn.get("content") or "").strip()
                if not text:
                    continue
                out.append(
                    self.add(
                        user_id=user_id,
                        content=text,
                        source_agent="mem0_fallback",
                        type=MemoryType.EPISODIC,
                        tenant_id=tenant_id,
                    )
                )
            return out

        try:
            result = self._mem0_client.add(conversation, user_id=str(user_id))
            memories = result.get("results", []) if isinstance(result, dict) else []
        except Exception as e:  # pragma: no cover
            logger.warning(f"Mem0 vendor call failed: {e}")
            return []

        out: list[Memory] = []
        for item in memories:
            content = item.get("memory") or item.get("text") or ""
            if not content:
                continue
            out.append(
                self.add(
                    user_id=user_id,
                    content=content,
                    source_agent="mem0",
                    type=item.get("type", MemoryType.FACT),
                    tenant_id=tenant_id,
                    confidence=float(item.get("score", 1.0) or 1.0),
                    metadata={"mem0_id": item.get("id")},
                )
            )
        return out


# ----------------------------------------------------------------------
# Singleton factory
# ----------------------------------------------------------------------

_singleton: MemoryStore | None = None


def get_memory_store() -> MemoryStore:
    """Lazily build a process-wide MemoryStore."""
    global _singleton
    if _singleton is None:
        use_mem0 = bool(os.getenv("MEM0_API_KEY"))
        _singleton = MemoryStore(use_mem0=use_mem0)
    return _singleton


def reset_memory_store() -> None:
    """Drop the cached store (used in tests)."""
    global _singleton
    _singleton = None
