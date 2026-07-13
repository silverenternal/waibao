"""T2704: Prompt v2 — versioned prompt registry with A/B traffic split.

Vendors Agenta semantics:
  * prompt_versions       — immutable per-version content with status
                           (draft / active / retired)
  * prompt_metrics        — rolling 4-dim evaluator scores
  * traffic_pct           — A/B split across active versions (sum = 100)
  * get_active_prompt     — weighted-bucket selection for live traffic
  * create_version        — create a new draft version (auto-increments)
  * retire_version        — mark a version retired, redistribute traffic
  * shift_traffic         — progressively move traffic between two versions

The default backend is in-memory so the test suite has zero external
dependencies. A real deployment swaps in `SupabasePromptStore` (kept
out of this file to keep the public surface small).
"""
from __future__ import annotations

import json
import logging
import os
import random
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger("waibao.platform.prompt_v2")


# ----------------------------------------------------------------------
# Status / metric constants
# ----------------------------------------------------------------------

class PromptStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    RETIRED = "retired"


METRIC_DIMENSIONS: Tuple[str, ...] = ("accuracy", "fluency", "safety", "bias")


# ----------------------------------------------------------------------
# Dataclasses
# ----------------------------------------------------------------------

@dataclass
class PromptVersion:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = ""
    name: str = ""
    agent: str = "default"
    version: int = 1
    content: str = ""
    description: str = ""
    variables: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    traffic_pct: int = 0
    status: PromptStatus = PromptStatus.DRAFT
    parent_version: Optional[int] = None
    created_by: str = "system"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    retired_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "agent": self.agent,
            "version": self.version,
            "content": self.content,
            "description": self.description,
            "variables": list(self.variables),
            "tags": list(self.tags),
            "traffic_pct": self.traffic_pct,
            "status": self.status.value,
            "parent_version": self.parent_version,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "retired_at": self.retired_at,
            "metadata": dict(self.metadata),
        }


@dataclass
class PromptMetric:
    prompt_id: str
    version: int
    metric_name: str
    value: float
    sample_size: int = 0
    computed_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prompt_id": self.prompt_id,
            "version": self.version,
            "metric_name": self.metric_name,
            "value": self.value,
            "sample_size": self.sample_size,
            "computed_at": self.computed_at,
            "metadata": dict(self.metadata),
        }


# ----------------------------------------------------------------------
# Errors
# ----------------------------------------------------------------------

class PromptRegistryError(Exception):
    def __init__(self, message: str, *, code: str = "prompt_error",
                 status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


# ----------------------------------------------------------------------
# In-memory registry
# ----------------------------------------------------------------------

class InMemoryPromptRegistry:
    """Thread-safe registry; backs the public `PromptService`."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._prompts: Dict[str, PromptVersion] = {}  # id -> row
        self._metrics: List[PromptMetric] = []
        # (tenant_id, name, agent) -> [version, ...]
        self._version_index: Dict[Tuple[str, str, str], List[int]] = {}

    # ---- create / read -----------------------------------------------

    def create_version(
        self,
        *,
        tenant_id: str,
        name: str,
        agent: str = "default",
        content: str,
        description: str = "",
        variables: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        traffic_pct: int = 0,
        status: PromptStatus = PromptStatus.DRAFT,
        parent_version: Optional[int] = None,
        created_by: str = "system",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PromptVersion:
        with self._lock:
            key = (tenant_id, name, agent)
            versions = self._version_index.setdefault(key, [])
            next_version = (max(versions) + 1) if versions else 1

            row = PromptVersion(
                tenant_id=tenant_id,
                name=name,
                agent=agent,
                version=next_version,
                content=content,
                description=description,
                variables=list(variables or []),
                tags=list(tags or []),
                traffic_pct=traffic_pct,
                status=status,
                parent_version=parent_version,
                created_by=created_by,
                metadata=dict(metadata or {}),
            )
            self._prompts[row.id] = row
            versions.append(next_version)

            if status == PromptStatus.ACTIVE:
                self._validate_traffic_locked(key)
            return row

    def get_by_id(self, prompt_id: str) -> Optional[PromptVersion]:
        return self._prompts.get(prompt_id)

    def list_versions(self, tenant_id: str, name: str,
                      agent: str = "default") -> List[PromptVersion]:
        key = (tenant_id, name, agent)
        with self._lock:
            ids = list(self._version_index.get(key, []))
        rows = []
        for v in ids:
            for row in self._prompts.values():
                if row.version == v and row.tenant_id == tenant_id \
                        and row.name == name and row.agent == agent:
                    rows.append(row)
                    break
        rows.sort(key=lambda r: r.version)
        return rows

    def list_active(self, tenant_id: str, name: str,
                    agent: str = "default") -> List[PromptVersion]:
        return [r for r in self.list_versions(tenant_id, name, agent)
                if r.status == PromptStatus.ACTIVE]

    # ---- traffic / status transitions --------------------------------

    def get_active_prompt(
        self,
        tenant_id: str,
        name: str,
        agent: str = "default",
        *,
        bucket: Optional[int] = None,
        rng: Optional[random.Random] = None,
    ) -> Optional[PromptVersion]:
        active = self.list_active(tenant_id, name, agent)
        if not active:
            # fall back to most recent non-retired
            all_versions = self.list_versions(tenant_id, name, agent)
            for r in reversed(all_versions):
                if r.status != PromptStatus.RETIRED:
                    return r
            return None
        weights = [max(0, r.traffic_pct) for r in active]
        total = sum(weights)
        if total <= 0:
            return active[0]
        if bucket is None:
            r = rng or random
            bucket = r.randint(0, total - 1)
        cursor = 0
        for row, w in zip(active, weights):
            cursor += w
            if bucket < cursor:
                return row
        return active[-1]

    def retire_version(self, tenant_id: str, name: str, agent: str,
                       version: int, *, redistribute_to: Optional[int] = None) -> PromptVersion:
        with self._lock:
            row = self._find_locked(tenant_id, name, agent, version)
            if row.status == PromptStatus.RETIRED:
                raise PromptRegistryError("already retired")
            row.status = PromptStatus.RETIRED
            row.retired_at = time.time()
            row.updated_at = time.time()
            row.traffic_pct = 0

            # Redistribute the freed-up traffic to remaining actives.
            actives = self.list_active(tenant_id, name, agent)
            if actives:
                if redistribute_to is not None:
                    target = next((r for r in actives if r.id == redistribute_to), None)
                else:
                    target = None
                if target is None:
                    target = actives[0]
                # Push all remaining traffic onto the target so the sum stays 100.
                target.traffic_pct = 100
                for r in actives:
                    if r.id != target.id:
                        r.traffic_pct = 0
            self._validate_traffic_locked((tenant_id, name, agent))
            return row

    def activate_version(self, tenant_id: str, name: str, agent: str,
                         version: int, *, traffic_pct: int = 100) -> PromptVersion:
        with self._lock:
            row = self._find_locked(tenant_id, name, agent, version)
            row.status = PromptStatus.ACTIVE
            row.traffic_pct = traffic_pct
            row.updated_at = time.time()
            self._validate_traffic_locked((tenant_id, name, agent))
            return row

    def shift_traffic(self, tenant_id: str, name: str, agent: str,
                      *, from_version: int, to_version: int,
                      shift_pct: int) -> Tuple[PromptVersion, PromptVersion]:
        """Move ``shift_pct`` points from one active version to another."""
        if shift_pct <= 0:
            raise PromptRegistryError("shift_pct must be > 0")
        with self._lock:
            src = self._find_locked(tenant_id, name, agent, from_version)
            dst = self._find_locked(tenant_id, name, agent, to_version)
            if src.status != PromptStatus.ACTIVE or dst.status != PromptStatus.ACTIVE:
                raise PromptRegistryError("both versions must be active")
            if shift_pct > src.traffic_pct:
                raise PromptRegistryError(
                    f"shift_pct ({shift_pct}) > src.traffic_pct ({src.traffic_pct})"
                )
            src.traffic_pct -= shift_pct
            dst.traffic_pct += shift_pct
            src.updated_at = dst.updated_at = time.time()
            self._validate_traffic_locked((tenant_id, name, agent))
            return src, dst

    # ---- metrics -----------------------------------------------------

    def record_metric(self, metric: PromptMetric) -> None:
        with self._lock:
            self._metrics.append(metric)

    def list_metrics(self, prompt_id: str, metric_name: Optional[str] = None,
                     limit: int = 100) -> List[PromptMetric]:
        out = [m for m in self._metrics if m.prompt_id == prompt_id]
        if metric_name is not None:
            out = [m for m in out if m.metric_name == metric_name]
        out.sort(key=lambda m: m.computed_at, reverse=True)
        return out[:limit]

    # ---- internals ---------------------------------------------------

    def _find_locked(self, tenant_id: str, name: str, agent: str,
                     version: int) -> PromptVersion:
        for row in self._prompts.values():
            if row.tenant_id == tenant_id and row.name == name \
                    and row.agent == agent and row.version == version:
                return row
        raise PromptRegistryError(f"prompt not found: {name} v{version}")

    def _validate_traffic_locked(self, key: Tuple[str, str, str]) -> None:
        active_rows = [r for r in self._prompts.values()
                       if (r.tenant_id, r.name, r.agent) == key
                       and r.status == PromptStatus.ACTIVE]
        # Validation only kicks in when 2+ active versions exist —
        # a single new active row defaults to 100 and is always valid.
        if len(active_rows) < 2:
            if len(active_rows) == 1 and active_rows[0].traffic_pct == 0:
                raise PromptRegistryError(
                    f"single active version must carry 100% traffic",
                    code="traffic_invalid", status_code=409,
                )
            return
        total = sum(r.traffic_pct for r in active_rows)
        if total != 100:
            raise PromptRegistryError(
                f"active traffic_pct for {key} must sum to 100 (got {total})",
                code="traffic_invalid", status_code=409,
            )


# ----------------------------------------------------------------------
# Public service
# ----------------------------------------------------------------------

class PromptService:
    """High-level façade used by the rest of the platform."""

    def __init__(self, registry: Optional[InMemoryPromptRegistry] = None) -> None:
        self.registry = registry or InMemoryPromptRegistry()
        self._lock = threading.RLock()

    # ---- CRUD wrappers ----------------------------------------------

    def create_version(self, *, tenant_id: str, name: str,
                       content: str, agent: str = "default",
                       **kwargs: Any) -> PromptVersion:
        if not tenant_id or not name or not content:
            raise PromptRegistryError("tenant_id / name / content required")
        with self._lock:
            return self.registry.create_version(
                tenant_id=tenant_id, name=name, agent=agent,
                content=content, **kwargs,
            )

    def list_versions(self, tenant_id: str, name: str,
                      agent: str = "default") -> List[PromptVersion]:
        return self.registry.list_versions(tenant_id, name, agent)

    def get_active_prompt(self, tenant_id: str, name: str,
                          agent: str = "default",
                          *, bucket: Optional[int] = None) -> Optional[PromptVersion]:
        return self.registry.get_active_prompt(
            tenant_id, name, agent, bucket=bucket,
        )

    def retire_version(self, tenant_id: str, name: str, agent: str,
                       version: int, *, redistribute_to: Optional[int] = None) -> PromptVersion:
        return self.registry.retire_version(
            tenant_id, name, agent, version, redistribute_to=redistribute_to,
        )

    def activate_version(self, tenant_id: str, name: str, agent: str,
                         version: int, *, traffic_pct: int = 100) -> PromptVersion:
        return self.registry.activate_version(
            tenant_id, name, agent, version, traffic_pct=traffic_pct,
        )

    def shift_traffic(self, tenant_id: str, name: str, agent: str,
                      *, from_version: int, to_version: int,
                      shift_pct: int) -> Tuple[PromptVersion, PromptVersion]:
        return self.registry.shift_traffic(
            tenant_id, name, agent,
            from_version=from_version, to_version=to_version,
            shift_pct=shift_pct,
        )

    # ---- ConfigCenter integration -----------------------------------

    def render(self, prompt: PromptVersion, variables: Dict[str, Any]) -> str:
        """Render ``{{var}}`` placeholders in ``content`` against ``variables``."""
        text = prompt.content
        for key, value in variables.items():
            text = text.replace("{{" + key + "}}", str(value))
        return text

    # ---- diff --------------------------------------------------------

    @staticmethod
    def diff(left: PromptVersion, right: PromptVersion) -> Dict[str, Any]:
        """Naïve unified diff of the two contents."""
        import difflib
        diff_lines = list(difflib.unified_diff(
            left.content.splitlines(),
            right.content.splitlines(),
            fromfile=f"v{left.version}",
            tofile=f"v{right.version}",
            lineterm="",
        ))
        return {
            "left": {"id": left.id, "version": left.version, "status": left.status.value},
            "right": {"id": right.id, "version": right.version, "status": right.status.value},
            "diff": "\n".join(diff_lines),
            "changed": left.content != right.content,
            "size_left": len(left.content),
            "size_right": len(right.content),
        }


# ----------------------------------------------------------------------
# Singleton
# ----------------------------------------------------------------------

_SERVICE: Optional[PromptService] = None


def get_prompt_service() -> PromptService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = PromptService()
    return _SERVICE


def reset_prompt_service() -> None:
    global _SERVICE
    _SERVICE = None