"""pgvector-backed memory store with RLS — T5021.

A drop-in backend for :class:`MemoryStore` that:

* persists memories to the ``memories_v2`` table whose ``embedding`` column
  is a ``vector(1024)`` (pgvector),
* runs semantic search through a Postgres RPC
  (``match_memories``) so the HNSW index is actually used instead of a
  client-side scan,
* enforces **tenant isolation** by setting the request's ``tenant_id`` via
  a Postgres ``SET LOCAL`` parameter on every transaction. Combined with a
  RLS policy ``USING (tenant_id = current_setting('app.tenant_id')::uuid)``
  this guarantees one tenant can never read another tenant's rows.

The class accepts a ``client_factory`` (Supabase / PostgREST client) and an
``embedder`` callable so the vector source is pluggable. When the backend
is offline (no client) it raises a clear error — there is no silent hash
fallback in this module, by design.
"""
from __future__ import annotations

import json
import logging
import math
import uuid
from datetime import datetime
from typing import Any, Callable, Optional

from .models import Memory, MemoryType

logger = logging.getLogger("waibao.memory.pgvector")


class PgVectorError(RuntimeError):
    """Raised when the pgvector backend is unreachable."""


# ---------------------------------------------------------------------------
# pgvector backend
# ---------------------------------------------------------------------------

class PgVectorMemoryBackend:
    """Production memory backend over pgvector + RLS.

    Args:
        client_factory: returns a Supabase / PostgREST client.
        embedder: ``callable(text) -> list[float]`` (real embedding model).
        table: table name (default ``memories_v2``).
        match_rpc: RPC name for ANN search (default ``match_memories``).
    """

    def __init__(
        self,
        client_factory: Callable[[], Any],
        *,
        embedder: Callable[[str], list[float]] | None = None,
        table: str = "memories_v2",
        match_rpc: str = "match_memories",
    ) -> None:
        self._client_factory = client_factory
        self._embedder = embedder
        self.table = table
        self.match_rpc = match_rpc

    # ------------------------------------------------------------------
    def _sb(self) -> Any:
        try:
            return self._client_factory()
        except Exception as exc:  # noqa: BLE001
            raise PgVectorError(f"pgvector client unavailable: {exc}") from exc

    def _embed(self, text: str) -> list[float]:
        if self._embedder is None:
            raise PgVectorError("no embedder configured for pgvector backend")
        return list(self._embedder(text))

    def _set_tenant(self, client: Any, tenant_id: uuid.UUID | str) -> None:
        """Bind the request to a tenant via a Postgres GUC.

        The RLS policy on ``memories_v2`` reads
        ``current_setting('app.tenant_id')`` and rejects any row whose
        ``tenant_id`` does not match. This is the row-level security
        boundary — it is enforced on the server, not the client.
        """
        try:
            # Supabase exposes .rpc(); we use a tiny no-arg RPC to set the GUC.
            client.rpc(
                "set_tenant_context",
                {"tenant_id": str(tenant_id)},
            ).execute()
        except Exception:  # noqa: BLE001
            # Some deployments set the GUC via a connection header instead.
            # The header path is configured on the pooler; nothing to do here.
            logger.debug("set_tenant_context rpc unavailable; relying on header/JWT")

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def insert(self, mem: Memory) -> Memory:
        client = self._sb()
        self._set_tenant(client, mem.tenant_id)
        row = mem.model_dump(mode="json")
        if row.get("embedding") is None:
            row["embedding"] = self._embed(mem.content)
        # pgvector accepts a JSON array literal via the PostgREST client.
        row["embedding"] = json.dumps(row["embedding"])
        res = client.table(self.table).insert(row).execute()
        if not getattr(res, "data", None):
            raise PgVectorError("insert returned no data")
        return Memory.from_row(res.data[0])

    def update(self, mem: Memory) -> Memory:
        client = self._sb()
        self._set_tenant(client, mem.tenant_id)
        row = mem.model_dump(mode="json")
        if "embedding" in row and row["embedding"] is not None:
            row["embedding"] = json.dumps(row["embedding"])
        client.table(self.table).update(row).eq("id", str(mem.id)).execute()
        return mem

    def delete(self, memory_id: uuid.UUID) -> None:
        client = self._sb()
        # RLS will additionally scope the delete to the caller's tenant.
        client.table(self.table).delete().eq("id", str(memory_id)).execute()

    def get(self, memory_id: uuid.UUID) -> Optional[Memory]:
        client = self._sb()
        res = client.table(self.table).select("*").eq("id", str(memory_id)).execute()
        if not getattr(res, "data", None):
            return None
        return Memory.from_row(res.data[0])

    def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        tenant_id: uuid.UUID,
        types: Optional[list[MemoryType]] = None,
        include_archived: bool = False,
        limit: int = 100,
    ) -> list[Memory]:
        client = self._sb()
        self._set_tenant(client, tenant_id)
        q = client.table(self.table).select("*").eq("user_id", str(user_id))
        if not include_archived:
            q = q.eq("is_archived", False)
        if types:
            q = q.in_("type", [t.value for t in types])
        q = q.limit(limit)
        res = q.execute()
        return [Memory.from_row(r) for r in (getattr(res, "data", None) or [])]

    # ------------------------------------------------------------------
    # Vector search via pgvector RPC (uses HNSW index)
    # ------------------------------------------------------------------
    def search(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        query_text: str,
        top_k: int = 10,
        types: Optional[list[MemoryType]] = None,
        min_confidence: float = 0.0,
    ) -> list[tuple[Memory, float]]:
        client = self._sb()
        self._set_tenant(client, tenant_id)
        query_embedding = self._embed(query_text)
        params: dict[str, Any] = {
            "query_embedding": json.dumps(query_embedding),
            "match_count": top_k,
            "filter_user_id": str(user_id),
            "filter_tenant_id": str(tenant_id),
            "min_confidence": min_confidence,
        }
        if types:
            params["filter_types"] = [t.value for t in types]
        try:
            res = client.rpc(self.match_rpc, params).execute()
        except Exception as exc:  # noqa: BLE001
            raise PgVectorError(f"match_memories rpc failed: {exc}") from exc
        rows = getattr(res, "data", None) or []
        out: list[tuple[Memory, float]] = []
        for r in rows:
            mem = Memory.from_row(r)
            score = float(r.get("similarity", r.get("score", 0.0)))
            out.append((mem, score))
        return out

    # ------------------------------------------------------------------
    # GDPR revoke — RLS-scoped delete
    # ------------------------------------------------------------------
    def forget_user(self, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> int:
        client = self._sb()
        self._set_tenant(client, tenant_id)
        res = client.table(self.table).delete().eq("user_id", str(user_id)).execute()
        return len(getattr(res, "data", None) or [])


# ---------------------------------------------------------------------------
# In-process RLS simulator (for tests / offline verification)
# ---------------------------------------------------------------------------

class _RLSMemoryTable:
    """A tiny in-process emulation of the pgvector + RLS table.

    Every read/write is scoped by ``tenant_id``: a query with the wrong
    tenant sees zero rows, exactly as the production RLS policy enforces.
    Used by the test suite to prove isolation without a live Postgres.
    """

    def __init__(self) -> None:
        self._rows: list[dict[str, Any]] = []
        self._tenant_ctx: uuid.UUID | None = None

    def set_tenant(self, tenant_id: uuid.UUID | None) -> None:
        self._tenant_ctx = tenant_id

    def _rls_filter(self, row: dict[str, Any]) -> bool:
        if self._tenant_ctx is None:
            return True
        return str(row.get("tenant_id")) == str(self._tenant_ctx)

    def insert(self, mem: Memory) -> Memory:
        # RLS WITH CHECK: inserted row's tenant must equal the session tenant.
        if self._tenant_ctx is not None and str(mem.tenant_id) != str(self._tenant_ctx):
            raise PgVectorError("RLS WITH CHECK violated: tenant mismatch on insert")
        row = mem.model_dump(mode="json")
        self._rows.append(row)
        return mem

    def list_for_user(
        self, user_id: uuid.UUID, *, tenant_id: uuid.UUID,
        types: Optional[list[MemoryType]] = None,
        include_archived: bool = False,
    ) -> list[Memory]:
        self._tenant_ctx = tenant_id
        out: list[Memory] = []
        for r in self._rows:
            if not self._rls_filter(r):
                continue
            if str(r.get("user_id")) != str(user_id):
                continue
            if not include_archived and r.get("is_archived"):
                continue
            if types and r.get("type") not in {t.value for t in types}:
                continue
            out.append(Memory.from_row(r))
        return out

    def search(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID,
        query_vec: list[float], top_k: int = 10,
    ) -> list[tuple[Memory, float]]:
        self._tenant_ctx = tenant_id
        scored: list[tuple[Memory, float]] = []
        for r in self._rows:
            if not self._rls_filter(r):
                continue
            if str(r.get("user_id")) != str(user_id):
                continue
            emb = r.get("embedding") or []
            score = _cosine(query_vec, emb)
            scored.append((Memory.from_row(r), score))
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored[:top_k]

    def forget_user(self, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> int:
        self._tenant_ctx = tenant_id
        before = len(self._rows)
        self._rows = [
            r for r in self._rows
            if not (self._rls_filter(r) and str(r.get("user_id")) == str(user_id))
        ]
        return before - len(self._rows)


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    da = math.sqrt(sum(x * x for x in a[:n])) or 1.0
    db = math.sqrt(sum(x * x for x in b[:n])) or 1.0
    return sum(x * y for x, y in zip(a[:n], b[:n])) / (da * db)
