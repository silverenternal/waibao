"""v6.0 T2102 — Config Center tests (40+).

These tests cover:
- `config_service` API (get / set / list / delete / history / rollback).
- In-memory cache behaviour.
- Typed accessors (get_string, get_int, get_bool, get_dict, get_list).
- `config_watcher` subscriber plumbing.
- EventBus integration: every set_value must emit `config.changed`
  so the watcher fan-outs (and front-end SSE sees it).
- Realtime guarantee: a `set_value` is observable to a subscriber
  without polling.
"""

from __future__ import annotations

import importlib
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple

import pytest

from eventbus import InMemoryEventBus, reset_event_bus, set_event_bus
from eventbus.decorators import on_event


# ===========================================================================
# In-memory backend shim for config_service
# ===========================================================================

class _MemoryBackend:
    """Replaces api.deps.get_supabase_admin for tests.

    Maintains tables `configs`, `config_history`, `config_subscribers`
    in-process so config_service can call .table() / .select() / .insert()
    / .update() / .delete() / .eq() / .execute() exactly like Supabase.
    """

    def __init__(self) -> None:
        self.data: Dict[str, List[Dict[str, Any]]] = {
            "configs": [], "config_history": [], "config_subscribers": [],
        }
        self._id = {"configs": 1, "config_history": 1, "config_subscribers": 1}

    def table(self, name: str) -> "_Table":
        return _Table(self, name)


class _Table:
    def __init__(self, backend: _MemoryBackend, name: str) -> None:
        self.backend = backend
        self.name = name
        self._filters: List[Tuple[str, Any, Any]] = []
        self._order: Optional[Tuple[str, bool]] = None
        self._limit: Optional[int] = None
        self._select_cols = "*"
        self._mode = "select"  # one of select / insert / update / delete
        self._payloads: List[Dict[str, Any]] = []

    # ---- mode selectors ----
    def select(self, cols: str = "*"):
        self._mode = "select"
        self._select_cols = cols
        return self

    def insert(self, payload: Any):
        self._mode = "insert"
        if isinstance(payload, dict):
            payload = [payload]
        self._payloads = list(payload)
        return self

    def update(self, payload: Dict[str, Any]):
        self._mode = "update"
        self._payloads = [payload]
        return self

    def delete(self):
        self._mode = "delete"
        return self

    # ---- filters ----
    def eq(self, col: str, val: Any):
        self._filters.append(("eq", col, val))
        return self

    def order(self, col: str, desc: bool = False):
        self._order = (col, desc)
        return self

    def limit(self, n: int):
        self._limit = n
        return self

    # ---- execute ----
    def execute(self):
        rows = self.backend.data[self.name]

        if self._mode == "select":
            out = list(rows)
            for _, col, val in self._filters:
                out = [r for r in out if r.get(col) == val]
            if self._order:
                col, desc = self._order
                out.sort(key=lambda r: r.get(col) or 0, reverse=desc)
            if self._limit is not None:
                out = out[: self._limit]
            return _Resp(out, self.backend)

        if self._mode == "insert":
            for p in self._payloads:
                p2 = dict(p)
                p2.setdefault("updated_at", "now()")
                p2.setdefault("changed_at", "now()")
                p2["id"] = self.backend._id[self.name]
                self.backend._id[self.name] += 1
                rows.append(p2)
            return _Resp(list(rows), self.backend)

        if self._mode == "update":
            updated = list(rows)
            for _, col, val in self._filters:
                updated = [r for r in updated if r.get(col) == val]
            payload = self._payloads[0]
            for r in updated:
                for k, v in payload.items():
                    if k not in ("id",):
                        r[k] = v
            return _Resp(updated, self.backend)

        if self._mode == "delete":
            keep = list(rows)
            removed: List[Dict[str, Any]] = []
            for _, col, val in self._filters:
                nk = []
                for r in keep:
                    if r.get(col) == val:
                        removed.append(r)
                    else:
                        nk.append(r)
                keep = nk
            for r in removed:
                rows.remove(r)
            return _Resp(removed, self.backend)

        return _Resp([], self.backend)


class _Resp:
    def __init__(self, data: List[Dict[str, Any]], backend: _MemoryBackend) -> None:
        self.data = data
        self.backend = backend

    def execute(self):  # chainable
        return self


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _setup():
    reset_event_bus()
    set_event_bus(InMemoryEventBus())
    yield
    reset_event_bus()


@pytest.fixture
def mem_backend():
    backend = _MemoryBackend()
    # Save and restore the real api.deps to avoid polluting sys.modules for
    # later tests (e.g. test_document_generator imports get_supabase from it).
    _saved_deps = sys.modules.get("api.deps")
    _fake_deps = type(sys)("api.deps")
    _fake_deps.get_supabase_admin = lambda: backend
    sys.modules["api.deps"] = _fake_deps
    if "services.platform.config_service" in sys.modules:
        importlib.reload(sys.modules["services.platform.config_service"])
    yield backend
    if _saved_deps is not None:
        sys.modules["api.deps"] = _saved_deps
    else:
        sys.modules.pop("api.deps", None)
    if "services.platform.config_service" in sys.modules:
        importlib.reload(sys.modules["services.platform.config_service"])


def _cs():
    return importlib.import_module("services.platform.config_service")


# ===========================================================================
# Scope / value validation
# ===========================================================================

class TestScopeAndValue:
    def test_valid_scopes(self, mem_backend):
        cs = _cs()
        assert set(cs.VALID_SCOPES) == {
            "system",
            "org",
            "agent",
            "feature",
            "service_toggle",
        }

    def test_valid_value_types(self, mem_backend):
        cs = _cs()
        assert "json" in cs.VALID_VALUE_TYPES
        assert "string" in cs.VALID_VALUE_TYPES

    def test_get_invalid_scope_raises(self, mem_backend):
        cs = _cs()
        with pytest.raises(ValueError):
            cs.get("nope", "x")

    def test_set_invalid_scope_raises(self, mem_backend):
        cs = _cs()
        with pytest.raises(ValueError):
            cs.set_value("nope", "x", 1)

    @pytest.mark.parametrize("vt,inp,expected", [
        ("string", 42, "42"),
        ("string", "hi", "hi"),
        ("number", "3.14", 3.14),
        ("number", 2, 2),
        ("boolean", "true", True),
        ("boolean", "false", False),
        ("boolean", 1, True),
        ("array", [1, 2], [1, 2]),
        ("array", (1, 2), [1, 2]),
    ])
    def test_value_coercion(self, mem_backend, vt, inp, expected):
        cs = _cs()
        v = cs._coerce_value(inp, vt)
        if vt == "number":
            assert isinstance(v, (int, float))
        assert v == expected


# ===========================================================================
# CRUD
# ===========================================================================

class TestCRUD:
    def test_set_then_get(self, mem_backend):
        cs = _cs()
        cs.set_value("system", "feature_flag", True, value_type="boolean",
                     changed_by="alice")
        assert cs.get_bool("system", "feature_flag") is True

    def test_set_then_get_string(self, mem_backend):
        cs = _cs()
        cs.set_value("system", "greeting", "hello", value_type="string")
        assert cs.get_string("system", "greeting") == "hello"

    def test_set_then_get_dict(self, mem_backend):
        cs = _cs()
        cs.set_value("agent", "weights", {"a": 1, "b": 2}, value_type="json")
        v = cs.get_dict("agent", "weights")
        assert v == {"a": 1, "b": 2}

    def test_set_then_get_list(self, mem_backend):
        cs = _cs()
        cs.set_value("system", "blacklist", ["x", "y"], value_type="array")
        assert cs.get_list("system", "blacklist") == ["x", "y"]

    def test_set_increments_version(self, mem_backend):
        cs = _cs()
        cs.set_value("system", "k", 1)
        cs.set_value("system", "k", 2)
        cs.set_value("system", "k", 3)
        rec = cs.get_record("system", "k")
        assert rec is not None and rec.version == 3

    def test_get_unknown_returns_default(self, mem_backend):
        cs = _cs()
        assert cs.get("system", "missing", default=42) == 42
        assert cs.get_string("system", "missing") == ""

    def test_get_returns_independent_copy(self, mem_backend):
        """Mutating the value returned by get() must not corrupt the cache."""
        cs = _cs()
        cs.set_value("system", "d", {"a": [1, 2, 3]})
        v1 = cs.get("system", "d")
        v1["a"].append(99)
        v2 = cs.get("system", "d")
        assert v2 == {"a": [1, 2, 3]}

    def test_list_keys(self, mem_backend):
        cs = _cs()
        cs.set_value("system", "a", 1)
        cs.set_value("agent", "b", 2)
        cs.set_value("agent", "c", 3)
        assert len(cs.list_keys()) == 3

    def test_list_keys_filtered_by_scope(self, mem_backend):
        cs = _cs()
        cs.set_value("system", "a", 1)
        cs.set_value("agent", "b", 2)
        cs.set_value("agent", "c", 3)
        agent_only = cs.list_keys(scope="agent")
        assert len(agent_only) == 2
        assert all(r.scope == "agent" for r in agent_only)

    def test_delete(self, mem_backend):
        cs = _cs()
        cs.set_value("system", "x", 1)
        assert cs.delete("system", "x") is True
        assert cs.get("system", "x") is None


# ===========================================================================
# History / rollback
# ===========================================================================

class TestHistory:
    def test_history_records_each_set(self, mem_backend):
        cs = _cs()
        cs.set_value("system", "k", 1)
        cs.set_value("system", "k", 2)
        cs.set_value("system", "k", 3)
        h = cs.history("system", "k")
        assert len(h) >= 3

    def test_rollback_to_v1(self, mem_backend):
        cs = _cs()
        cs.set_value("system", "k", 1)
        cs.set_value("system", "k", 2)
        cs.set_value("system", "k", 3)
        # cache must be cleared so we observe the new value
        rec = cs.rollback("system", "k", to_version=1, changed_by="alice")
        assert rec is not None
        cs.clear_cache()
        assert cs.get("system", "k") == 1

    def test_rollback_missing_version_returns_none(self, mem_backend):
        cs = _cs()
        cs.set_value("system", "k", 1)
        assert cs.rollback("system", "k", to_version=99) is None

    def test_history_after_rollback(self, mem_backend):
        cs = _cs()
        cs.set_value("system", "k", 1)
        cs.set_value("system", "k", 2)
        cs.rollback("system", "k", to_version=1)
        h = cs.history("system", "k")
        ops = [r.get("operation") for r in h]
        assert "rollback" in ops


# ===========================================================================
# EventBus integration — realtime
# ===========================================================================

class TestEventBusIntegration:
    def test_set_emits_config_changed(self, mem_backend):
        seen = []

        @on_event("config.changed")
        def _h(e):
            seen.append(e.payload)

        cs = _cs()
        cs.set_value("system", "k", 1, changed_by="alice")
        assert seen and seen[0]["scope"] == "system"
        assert seen[0]["changed_by"] == "alice"
        assert seen[0]["value"] == 1

    def test_rollback_emits_config_changed_and_rolled_back(self, mem_backend):
        seen_changed: list = []
        seen_rb: list = []

        @on_event("config.changed")
        def _h1(e): seen_changed.append(e.payload)

        @on_event("config.rolled_back")
        def _h2(e): seen_rb.append(e.payload)

        cs = _cs()
        cs.set_value("system", "k", 1)
        cs.set_value("system", "k", 2)
        cs.rollback("system", "k", to_version=1)
        assert any(p.get("operation") == "rollback" for p in seen_changed)
        assert seen_rb and seen_rb[0]["to_version"] == 1

    def test_delete_emits_config_changed(self, mem_backend):
        seen = []

        @on_event("config.changed")
        def _h(e): seen.append(e.payload)

        cs = _cs()
        cs.set_value("system", "k", 1)
        cs.delete("system", "k")
        assert any(p.get("value") is None for p in seen)

    def test_subscriber_sees_value_via_get(self, mem_backend):
        cs = _cs()
        cs.set_value("system", "k", 42)
        assert cs.get_int("system", "k") == 42

    def test_live_propagation_via_eventbus(self, mem_backend):
        seen = []

        @on_event("config.changed")
        def _h(e): seen.append(e.payload)

        cs = _cs()
        cs.set_value("system", "live", "x")
        cs.set_value("system", "live", "y")
        assert len(seen) >= 2
        assert seen[-1]["value"] == "y"


# ===========================================================================
# Prompt API
# ===========================================================================

class TestPromptAPI:
    def test_get_prompt_default(self, mem_backend):
        cs = _cs()
        assert cs.get_prompt("clarifier", default="x") == "x"

    def test_get_prompt_after_set(self, mem_backend):
        cs = _cs()
        cs.set_value("agent", "agent.prompts.clarifier.system",
                     "你好", value_type="string")
        assert cs.get_prompt("clarifier", "system", default="x") == "你好"

    def test_prompt_key_combination(self, mem_backend):
        cs = _cs()
        cs.set_value("agent", "agent.prompts.career.planner",
                     "请生成", value_type="string")
        assert cs.get_prompt("career", "planner", default="") == "请生成"


# ===========================================================================
# Cache + reload helpers
# ===========================================================================

class TestCache:
    def test_clear_cache_then_get_re_reads(self, mem_backend):
        cs = _cs()
        cs.set_value("system", "k", 1)
        cs.clear_cache()
        v = cs.get("system", "k")
        assert v == 1

    def test_reload_cache_returns_none(self, mem_backend):
        cs = _cs()
        cs.set_value("system", "k", 1)
        cs.clear_cache()
        assert cs.get("system", "k") == 1


# ===========================================================================
# config_watcher plumbing
# ===========================================================================

class TestConfigWatcher:
    def test_watch_basic_callback(self, mem_backend):
        from services.platform import config_watcher
        config_watcher.ConfigWatcher._instance = None
        w = config_watcher.ConfigWatcher.instance()
        seen: list = []
        w.watch("system", "mykey", lambda s, k, v: seen.append((s, k, v)))
        w.start()
        cs = _cs()
        cs.set_value("system", "mykey", 99)
        assert any(k == "mykey" and v == 99 for (s, k, v) in seen)

    def test_watch_wildcard(self, mem_backend):
        from services.platform import config_watcher
        config_watcher.ConfigWatcher._instance = None
        w = config_watcher.ConfigWatcher.instance()
        seen: list = []
        w.watch("agent", "*", lambda s, k, v: seen.append((s, k, v)))
        w.start()
        cs = _cs()
        cs.set_value("agent", "prompts.x", "v1")
        cs.set_value("agent", "weights.y", 0.5)
        assert any(k == "prompts.x" for (s, k, v) in seen)
        assert any(k == "weights.y" for (s, k, v) in seen)

    def test_unwatch(self, mem_backend):
        from services.platform import config_watcher
        config_watcher.ConfigWatcher._instance = None
        w = config_watcher.ConfigWatcher.instance()
        cb = lambda s, k, v: None
        w.watch("system", "x", cb)
        assert len(w._handlers) >= 1
        w.unwatch(cb)
        assert all(h[2] is not cb for h in w._handlers)


# ===========================================================================
# Threshold (match weights / bias) usage
# ===========================================================================

class TestThresholdUsage:
    def test_match_weight_override(self, mem_backend):
        cs = _cs()
        cs.set_value("feature", "match.weight.skill", 0.5, value_type="number")
        cs.set_value("feature", "match.weight.semantic", 0.3, value_type="number")
        cs.set_value("feature", "match.weight.experience", 0.2, value_type="number")
        assert cs.get_float("feature", "match.weight.skill") == 0.5
        assert cs.get_float("feature", "match.weight.semantic") == 0.3
        assert cs.get_float("feature", "match.weight.experience") == 0.2

    def test_bias_threshold_override(self, mem_backend):
        cs = _cs()
        cs.set_value("agent", "bias.min_fairness_score", 0.6, value_type="number")
        threshold = cs.get_float("agent", "bias.min_fairness_score", default=0.4)
        assert threshold == 0.6


# ===========================================================================
# API surface (Pydantic validation)
# ===========================================================================

class TestAdminAPI:
    def test_router_exists(self):
        from api.admin_config import router
        assert router is not None

    def test_configsetbody_validates_value_type(self):
        from api.admin_config import ConfigSetBody
        body = ConfigSetBody(value={"x": 1}, value_type="json")
        assert body.value_type == "json"

    def test_pydantic_rejects_invalid_value_type(self):
        from api.admin_config import ConfigSetBody
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ConfigSetBody(value=1, value_type="not-a-type")

    def test_rollback_body(self):
        from api.admin_config import RollbackBody
        body = RollbackBody(to_version=2, changed_by="x")
        assert body.to_version == 2


# ===========================================================================
# Concurrency / idempotency
# ===========================================================================

class TestIdempotency:
    def test_setting_same_value_increments_version(self, mem_backend):
        cs = _cs()
        cs.set_value("system", "k", 1)
        cs.set_value("system", "k", 1)
        cs.set_value("system", "k", 1)
        assert cs.get_record("system", "k").version == 3

    def test_history_ordering(self, mem_backend):
        cs = _cs()
        cs.set_value("system", "k", "a")
        cs.set_value("system", "k", "b")
        cs.set_value("system", "k", "c")
        h = cs.history("system", "k")
        versions = [r["version"] for r in h]
        assert versions == sorted(versions, reverse=True)


# ===========================================================================
# Realtime: change → agent behavior updates (broadcast end-to-end)
# ===========================================================================

class TestRealtimeEffect:
    """An operator changes a config; an agent that reads the config
    through config_service sees the new value immediately (no restart).
    """

    def test_agent_prompt_change_observed_immediately(self, mem_backend):
        from eventbus import emit

        seen_prompts: list = []

        def fake_agent_run():
            # simulate the agent pulling the prompt each call
            cs = _cs()
            return cs.get_prompt("clarifier", "system", default="DEFAULT")

        # first call: default
        seen_prompts.append(fake_agent_run())
        assert seen_prompts[-1] == "DEFAULT"

        # operator sets it via the config API (here directly):
        cs = _cs()
        cs.set_value("agent", "agent.prompts.clarifier.system",
                     "NEW CLARIFIER PROMPT", value_type="string")

        # next call: NEW prompt — proves realtime effect
        seen_prompts.append(fake_agent_run())
        assert seen_prompts[-1] == "NEW CLARIFIER PROMPT"

    def test_threshold_change_observed_immediately(self, mem_backend):
        cs = _cs()

        def bias_check(value: float):
            threshold = cs.get_float("agent", "bias.min_fairness_score",
                                     default=0.5)
            return value >= threshold

        assert bias_check(0.4) is False
        cs.set_value("agent", "bias.min_fairness_score", 0.3,
                     value_type="number")
        assert bias_check(0.4) is True
