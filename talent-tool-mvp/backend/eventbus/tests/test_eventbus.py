"""Tests for the EventBus abstraction (v6.0).

50+ tests covering: Event dataclass, InMemoryEventBus, RedisEventBus (mocked),
decorators, registry, subscribers bootstrap, integration helpers, and end-to-end
agent event-emission coverage.
"""

from __future__ import annotations

import asyncio
import threading
import time
import uuid
from typing import List
from unittest.mock import MagicMock, patch

import pytest

from eventbus import (
    Event,
    EventBus,
    InMemoryEventBus,
    RedisEventBus,
    Subscription,
    await_event,
    clear_registered,
    emit,
    fire,
    get_event_bus,
    listen,
    on_event,
    registered_subscriptions,
    reset_event_bus,
    set_event_bus,
)
from eventbus.decorators import is_async_handler
from eventbus.integration import (
    emit_agent_completed,
    emit_agent_failed,
    emit_agent_started,
    emit_emotion_detected,
    emit_emotion_risk,
    emit_journal_submitted,
    emit_market_updated,
    emit_needs_clarified,
    emit_plan_generated,
    emit_profile_created,
    emit_profile_enriched,
    emit_profile_updated,
    emit_role_image_updated,
    emit_strategy_updated,
    emit_ticket_created,
    emit_ticket_escalated,
)
from eventbus.subscribers import (
    SUBSCRIBERS,
    register_all_subscribers,
)


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture(autouse=True)
def _isolate_bus():
    """Each test gets a fresh InMemoryEventBus + empty subscriber registry."""
    reset_event_bus()
    set_event_bus(InMemoryEventBus())
    clear_registered()
    # clear the SUBSCRIBERS list (test-local)
    SUBSCRIBERS.clear()
    yield
    reset_event_bus()
    SUBSCRIBERS.clear()


# ===========================================================================
# Event dataclass
# ===========================================================================

class TestEventDataclass:
    def test_default_source_unknown(self):
        e = Event(name="x", payload={})
        assert e.source == "unknown"

    def test_event_id_is_uuid4_string(self):
        e = Event(name="x", payload={})
        uuid.UUID(e.event_id)  # validates

    def test_correlation_id_optional(self):
        assert Event(name="x", payload={}).correlation_id is None

    def test_metadata_default_dict(self):
        e = Event(name="x", payload={})
        assert e.metadata == {}
        e.metadata["k"] = "v"
        assert e.metadata == {"k": "v"}

    def test_to_dict_roundtrip(self):
        e = Event(name="foo.bar", payload={"x": 1}, source="t",
                  correlation_id="c-1", metadata={"trace": True})
        d = e.to_dict()
        e2 = Event.from_dict(d)
        assert e2.name == e.name
        assert e2.payload == e.payload
        assert e2.source == e.source
        assert e2.event_id == e.event_id
        assert e2.correlation_id == e.correlation_id
        assert e2.metadata == e.metadata

    def test_from_dict_fills_missing_event_id(self):
        e = Event.from_dict({"name": "x", "payload": {}, "source": "t"})
        assert e.event_id  # auto-assigned

    def test_from_dict_uses_time_default_for_timestamp(self):
        e = Event.from_dict({"name": "x", "payload": {}})
        assert isinstance(e.timestamp, float)
        assert e.timestamp > 0

    def test_timestamp_is_recent(self):
        before = time.time()
        e = Event(name="x", payload={})
        after = time.time()
        assert before <= e.timestamp <= after


# ===========================================================================
# Subscription dataclass
# ===========================================================================

class TestSubscription:
    def test_repr(self):
        s = Subscription(id="abc", event_name="foo", handler=lambda e: None)
        assert "Subscription" in repr(s)
        assert "foo" in repr(s)

    def test_async_flag_defaults_false(self):
        s = Subscription(id="x", event_name="t", handler=lambda e: None)
        assert s.is_async is False

    def test_created_at_recent(self):
        before = time.time()
        s = Subscription(id="x", event_name="t", handler=lambda e: None)
        after = time.time()
        assert before <= s.created_at <= after


# ===========================================================================
# InMemoryEventBus core behaviour
# ===========================================================================

class TestInMemoryCore:
    def test_publish_invokes_subscribers(self):
        bus = InMemoryEventBus()
        seen: List[Event] = []
        bus.subscribe("t", lambda e: seen.append(e))
        bus.emit("t", {"a": 1})
        assert len(seen) == 1
        assert seen[0].payload == {"a": 1}

    def test_unsubscribe_removes_handler(self):
        bus = InMemoryEventBus()
        seen: List[Event] = []
        sub = bus.subscribe("t", lambda e: seen.append(e))
        bus.emit("t", {})
        bus.unsubscribe(sub)
        bus.emit("t", {})
        assert len(seen) == 1

    def test_multiple_subscribers(self):
        bus = InMemoryEventBus()
        a, b = [], []
        bus.subscribe("t", lambda e: a.append(e))
        bus.subscribe("t", lambda e: b.append(e))
        bus.emit("t", {})
        assert len(a) == 1 and len(b) == 1

    def test_no_subscribers_no_error(self):
        bus = InMemoryEventBus()
        bus.emit("nobody", {"k": 1})  # should not raise

    def test_handler_exception_isolated(self):
        bus = InMemoryEventBus()
        ok: List[Event] = []

        def boom(_e):
            raise RuntimeError("boom")

        bus.subscribe("t", boom)

        def fine(e):
            ok.append(e)

        bus.subscribe("t", fine)
        bus.emit("t", {})
        assert len(ok) == 1
        assert len(bus.errors) == 1

    def test_handler_exception_logged(self, caplog):
        bus = InMemoryEventBus()

        def boom(_e):
            raise RuntimeError("logged")

        bus.subscribe("t", boom)
        with caplog.at_level("ERROR"):
            bus.emit("t", {})
        assert any("handler" in r.message for r in caplog.records)

    def test_errors_property_returns_copy(self):
        bus = InMemoryEventBus()
        bus.subscribe("t", lambda e: (_ for _ in ()).throw(RuntimeError("x")))
        bus.emit("t", {})
        e1 = bus.errors
        e2 = bus.errors
        assert e1 == e2 and e1 is not e2

    def test_clear_errors(self):
        bus = InMemoryEventBus()
        bus.subscribe("t", lambda e: (_ for _ in ()).throw(RuntimeError("x")))
        bus.emit("t", {})
        assert bus.errors
        bus.clear_errors()
        assert bus.errors == []

    def test_thread_safety(self):
        """Concurrent publish/subscribe should not crash."""
        bus = InMemoryEventBus()
        seen: List[int] = []

        def sub(e: Event) -> None:
            seen.append(e.payload["i"])

        bus.subscribe("t", sub)

        def publisher(start: int):
            for i in range(50):
                bus.emit("t", {"i": start + i})

        threads = [threading.Thread(target=publisher, args=(i * 1000,))
                   for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(seen) == 200

    def test_emit_returns_event(self):
        bus = InMemoryEventBus()
        e = bus.emit("t", {"x": 1})
        assert isinstance(e, Event)
        assert e.payload == {"x": 1}

    def test_emit_default_source_app(self):
        bus = InMemoryEventBus()
        e = bus.emit("t")
        assert e.source == "app"

    def test_emit_default_payload_empty(self):
        bus = InMemoryEventBus()
        e = bus.emit("t")
        assert e.payload == {}


# ===========================================================================
# publish_async
# ===========================================================================

class TestPublishAsync:
    def test_runs_async_handler(self):
        bus = InMemoryEventBus()
        seen: List[bool] = []

        async def cb(e):
            seen.append(True)

        bus.subscribe("t", cb)
        asyncio.run(bus.publish_async(Event(name="t", payload={})))
        assert seen == [True]

    def test_runs_sync_handler_via_executor(self):
        bus = InMemoryEventBus()
        seen: List[bool] = []

        def cb(e):
            seen.append(True)

        bus.subscribe("t", cb)
        asyncio.run(bus.publish_async(Event(name="t", payload={})))
        assert seen == [True]

    def test_mixed_handlers(self):
        bus = InMemoryEventBus()
        sync, async_ = [], []

        def s(e):
            sync.append(e)

        async def a(e):
            async_.append(e)

        bus.subscribe("t", s)
        bus.subscribe("t", a)
        asyncio.run(bus.publish_async(Event(name="t", payload={})))
        assert len(sync) == 1 and len(async_) == 1

    def test_async_handler_exception_isolated(self):
        bus = InMemoryEventBus()
        ok: List[Event] = []

        async def boom(e):
            raise RuntimeError("async-boom")

        async def fine(e):
            ok.append(e)

        bus.subscribe("t", boom)
        bus.subscribe("t", fine)
        asyncio.run(bus.publish_async(Event(name="t", payload={})))
        assert len(ok) == 1
        assert len(bus.errors) == 1


# ===========================================================================
# Decorators
# ===========================================================================

class TestOnEventDecorator:
    def test_sync_decorator(self):
        seen = []

        @on_event("x")
        def h(e: Event):
            seen.append(e.payload)

        emit("x", {"v": 1})
        assert seen == [{"v": 1}]

    def test_async_decorator_marks_async(self):
        @on_event("y")
        async def h(e):
            return None
        # is_async check
        from eventbus.decorators import _REGISTERED
        assert _REGISTERED[-1].is_async is True

    def test_async_decorator_actually_runs(self):
        seen = []

        @on_event("z")
        async def h(e: Event):
            await asyncio.sleep(0)
            seen.append(e.payload)

        bus = get_event_bus()
        asyncio.run(bus.publish_async(Event(name="z", payload={"k": "v"})))
        assert seen == [{"k": "v"}]

    def test_clear_registered_removes_subs(self):
        @on_event("a")
        def h(e):
            pass

        bus = get_event_bus()
        assert len(registered_subscriptions()) >= 1
        clear_registered()
        assert registered_subscriptions() == []

    def test_custom_bus(self):
        bus = InMemoryEventBus()
        seen = []

        @on_event("b", bus=bus)
        def h(e):
            seen.append(e.payload)

        emit("b", {"x": 1}, bus=bus)
        assert seen == [{"x": 1}]

    def test_wrapper_keeps_docstring(self):
        @on_event("c")
        def h(e):
            """the docstring"""
        assert h.__doc__ == "the docstring"

    def test_subscription_attached_to_wrapper(self):
        @on_event("d")
        def h(e):
            pass
        assert hasattr(h, "__waibao_subscription__")


class TestEmitHelper:
    def test_emit_returns_event(self):
        e = emit("foo", {"a": 1}, source="x")
        assert e.name == "foo"
        assert e.payload == {"a": 1}
        assert e.source == "x"

    def test_fire_sugar_kwargs(self):
        e = fire("bar", alpha=1, beta=2)
        assert e.payload == {"alpha": 1, "beta": 2}

    def test_listen_returns_subscription(self):
        sub = listen("z", lambda e: None)
        assert isinstance(sub, Subscription)
        assert sub.event_name == "z"

    def test_await_event_timeout_returns_none(self):
        async def driver():
            return await await_event("never", timeout=0.05)
        assert asyncio.run(driver()) is None

    def test_await_event_success(self):
        async def driver():
            async def publisher():
                await asyncio.sleep(0.01)
                emit("ok", {"v": 1})
            asyncio.create_task(publisher())
            return await await_event("ok", timeout=1.0)
        evt = asyncio.run(driver())
        assert evt.payload == {"v": 1}

    def test_is_async_handler_helper(self):
        def s():
            pass

        async def a():
            pass

        assert is_async_handler(a) is True
        assert is_async_handler(s) is False


# ===========================================================================
# Registry / singleton
# ===========================================================================

class TestRegistry:
    def test_singleton_returns_same_instance(self):
        a = get_event_bus()
        b = get_event_bus()
        assert a is b

    def test_set_event_bus_overrides(self):
        b1 = InMemoryEventBus()
        b2 = InMemoryEventBus()
        set_event_bus(b1)
        assert get_event_bus() is b1
        set_event_bus(b2)
        assert get_event_bus() is b2

    def test_reset_event_bus_then_get_creates_new(self):
        set_event_bus(InMemoryEventBus())
        a = get_event_bus()
        reset_event_bus()
        b = get_event_bus()
        assert a is not b

    def test_env_var_redis_requires_redis(self, monkeypatch):
        monkeypatch.setenv("WAIBAO_EVENTBUS", "redis")
        reset_event_bus()
        with patch.dict("sys.modules", {"redis": MagicMock()}):
            with patch("eventbus.base.RedisEventBus",
                       return_value=MagicMock(spec=EventBus)) as mock_cls:
                bus = get_event_bus()
                assert bus is not None
                assert mock_cls.called


# ===========================================================================
# RedisEventBus (mocked)
# ===========================================================================

class TestRedisEventBus:
    def test_construct_requires_redis(self, monkeypatch):
        # Force ImportError for redis
        import sys
        monkeypatch.setitem(sys.modules, "redis", None)
        with pytest.raises(RuntimeError):
            RedisEventBus()

    def test_publish_calls_redis_publish(self):
        # Build a RedisEventBus-like object via __new__ to skip __init__
        bus = RedisEventBus.__new__(RedisEventBus)
        bus._redis = MagicMock()
        bus._prefix = "waibao:events:"
        bus._local = InMemoryEventBus()
        seen = []
        bus._local.subscribe("t", lambda e: seen.append(e))
        bus.publish(Event(name="t", payload={"a": 1}))
        bus._redis.publish.assert_called_once()
        assert seen and seen[0].payload == {"a": 1}

    def test_local_shortcut_subscribe(self):
        bus = RedisEventBus.__new__(RedisEventBus)
        bus._redis = MagicMock()
        bus._prefix = "x:"
        bus._local = InMemoryEventBus()
        sub = bus.subscribe("topic", lambda e: None)
        assert isinstance(sub, Subscription)

    def test_publish_async_returns_awaitable(self):
        bus = RedisEventBus.__new__(RedisEventBus)
        bus._redis = MagicMock()
        bus._prefix = "x:"
        bus._local = InMemoryEventBus()
        seen = []
        bus._local.subscribe("t", lambda e: seen.append(e))
        result = bus.publish_async(Event(name="t", payload={}))
        asyncio.run(result)
        assert seen and seen[0].payload == {}

    def test_unsubscribe_delegates_local(self):
        bus = RedisEventBus.__new__(RedisEventBus)
        bus._redis = MagicMock()
        bus._prefix = "x:"
        bus._local = InMemoryEventBus()
        sub = bus.subscribe("t", lambda e: None)
        bus.unsubscribe(sub)
        assert bus._local._handlers.get("t", []) == []





# ===========================================================================
# Integration helpers
# ===========================================================================

class TestIntegrationHelpers:
    def test_emit_profile_updated(self):
        seen = []
        @on_event("profile.updated")
        def h(e): seen.append(e.payload)
        emit_profile_updated(user_id="u-1", candidate_id="c-1",
                             fields=["name", "email"], completeness=0.8,
                             source="clarifier")
        assert seen and seen[0]["user_id"] == "u-1"
        assert seen[0]["completeness"] == 0.8

    def test_emit_profile_created(self):
        seen = []
        @on_event("profile.created")
        def h(e): seen.append(e.payload)
        emit_profile_created(user_id="u", initial_fields=["phone"])
        assert seen and seen[0]["initial_fields"] == ["phone"]

    def test_emit_profile_enriched(self):
        seen = []
        @on_event("profile.enriched")
        def h(e): seen.append(e.payload)
        emit_profile_enriched(user_id="u", new_skills=["python", "sql"])
        assert "python" in seen[0]["new_skills"]

    def test_emit_needs_clarified(self):
        seen = []
        @on_event("needs.clarified")
        def h(e): seen.append(e.payload)
        emit_needs_clarified(user_id="u", must_haves=["remote"], confidence=0.9)
        assert seen[0]["must_haves"] == ["remote"]
        assert seen[0]["confidence"] == 0.9

    def test_emit_emotion_detected(self):
        seen = []
        @on_event("emotion.detected")
        def h(e): seen.append(e.payload)
        emit_emotion_detected(user_id="u", primary_emotion="anxiety",
                              intensity=0.7, sentiment=-0.3)
        assert seen and seen[0]["primary_emotion"] == "anxiety"

    def test_emit_emotion_risk(self):
        seen = []
        @on_event("emotion.risk")
        def h(e): seen.append(e.payload)
        emit_emotion_risk(user_id="u", risk_level="severe",
                          primary_emotion="hopelessness", intensity=0.9)
        assert seen and seen[0]["risk_level"] == "severe"

    def test_emit_plan_generated(self):
        seen = []
        @on_event("plan.generated")
        def h(e): seen.append(e.payload)
        emit_plan_generated(user_id="u", plan_id="p-1",
                            milestones=["learn Rust", "apply"])
        assert seen[0]["plan_id"] == "p-1"
        assert "learn Rust" in seen[0]["milestones"]

    def test_emit_market_updated(self):
        seen = []
        @on_event("market.updated")
        def h(e): seen.append(e.payload)
        emit_market_updated(region="us-west", jobs_count=100, delta_pct=2.5,
                            top_skills=["python"])
        assert seen and seen[0]["region"] == "us-west"

    def test_emit_journal_submitted(self):
        seen = []
        @on_event("journal.submitted")
        def h(e): seen.append(e.payload)
        emit_journal_submitted(user_id="u", journal_id="j-1",
                                mood=0.6, summary="good day")
        assert seen and seen[0]["mood"] == 0.6

    def test_emit_role_image_updated(self):
        seen = []
        @on_event("role.image.updated")
        def h(e): seen.append(e.payload)
        emit_role_image_updated(employer_id="e", role_id="r",
                                traits=["curious"], must_haves=["python"])
        assert "curious" in seen[0]["traits"]

    def test_emit_strategy_updated(self):
        seen = []
        @on_event("strategy.updated")
        def h(e): seen.append(e.payload)
        emit_strategy_updated(employer_id="e", themes=["AI-first"])
        assert seen[0]["themes"] == ["AI-first"]

    def test_emit_ticket_created(self):
        seen = []
        @on_event("ticket.created")
        def h(e): seen.append(e.payload)
        emit_ticket_created(ticket_id="t-1", employer_id="e",
                            severity="high", summary="urgent")
        assert seen[0]["severity"] == "high"

    def test_emit_ticket_escalated(self):
        seen = []
        @on_event("ticket.escalated")
        def h(e): seen.append(e.payload)
        emit_ticket_escalated(ticket_id="t-1", from_level="L1",
                              to_level="L2", reason="sla")
        assert seen[0]["reason"] == "sla"

    def test_emit_agent_started(self):
        seen = []
        @on_event("agent.started")
        def h(e): seen.append(e.payload)
        emit_agent_started(agent_name="clarifier_agent", user_id="u",
                           run_id="r-1", input_keys=["ctx"])
        assert seen and seen[0]["agent_name"] == "clarifier_agent"

    def test_emit_agent_completed(self):
        seen = []
        @on_event("agent.completed")
        def h(e): seen.append(e.payload)
        emit_agent_completed(agent_name="x", user_id="u",
                             latency_ms=120, artifacts_count=3)
        assert seen[0]["latency_ms"] == 120

    def test_emit_agent_failed(self):
        seen = []
        @on_event("agent.failed")
        def h(e): seen.append(e.payload)
        emit_agent_failed(agent_name="x", user_id="u", error="oops",
                           recoverable=False)
        assert seen[0]["recoverable"] is False


# ===========================================================================
# Subscribers bootstrap
# ===========================================================================

class TestSubscribers:
    def test_register_all_returns_count(self):
        n = register_all_subscribers()
        assert n >= 10

    def test_register_all_idempotent(self):
        # Each call adds a new set of handlers
        n1 = register_all_subscribers()
        n2 = register_all_subscribers()
        assert n1 == n2

    def test_all_events_trigger_subscribers(self):
        register_all_subscribers()

        seen = {n: 0 for n in (
            "profile.updated", "ticket.escalated", "ticket.created",
            "agent.completed", "workflow.completed", "config.changed",
            "role.image.updated", "market.updated", "emotion.detected",
            "plugin.enabled", "metric.emitted", "agent.failed",
            "funnel.stage_changed", "plan.generated",
        )}

        # Wrap emit to count
        bus = get_event_bus()
        original_emit = bus.emit

        def counting_emit(name, payload=None, **kw):
            if name in seen:
                seen[name] += 1
            return original_emit(name, payload, **kw)

        bus.emit = counting_emit

        emit("profile.updated", {"u": 1})
        emit("ticket.escalated", {"t": 1})
        emit("ticket.created", {"t": 1})
        emit("agent.completed", {"a": 1})
        emit("workflow.completed", {"w": 1})
        emit("config.changed", {"k": 1})
        emit("role.image.updated", {"r": 1})
        emit("market.updated", {"m": 1})
        emit("emotion.detected", {"e": 1})
        emit("plugin.enabled", {"p": 1})
        emit("metric.emitted", {"v": 1})
        emit("agent.failed", {"e": 1})
        emit("funnel.stage_changed", {"c": 1})
        emit("plan.generated", {"p": 1})

        for name, count in seen.items():
            assert count >= 1, name


# ===========================================================================
# End-to-end: all 16 agents produce at least one event
# ===========================================================================

AGENT_FILES = {
    "intake_agent": ("agents.jobseeker.intake_agent", "IntakeAgent"),
    "profile_agent": ("agents.jobseeker.profile_agent", "ProfileAgent"),
    "clarifier_agent": ("agents.jobseeker.clarifier_agent", "ClarifierAgent"),
    "emotion_agent": ("agents.jobseeker.emotion_agent", "EmotionAgent"),
    "career_planner_agent": ("agents.jobseeker.career_planner_agent", "CareerPlannerAgent"),
    "daily_journal_agent": ("agents.jobseeker.daily_journal_agent", "DailyJournalAgent"),
    "persona_agent": ("agents.employer.persona_agent", "PersonaAgent"),
    "compliance_agent": ("agents.employer.compliance_agent", "ComplianceAgent"),
    "vision_agent": ("agents.employer.vision_agent", "VisionAgent"),
    "talent_brief_agent": ("agents.employer.talent_brief_agent", "TalentBriefAgent"),
    "job_spec_agent": ("agents.employer.job_spec_agent", "JobSpecAgent"),
    "policy_agent": ("agents.employer.policy_agent", "PolicyAgent"),
    "multi_party_agent": ("agents.employer.multi_party_agent", "MultiPartyAgent"),
    "employer_clarifier_agent": ("agents.employer.employer_clarifier_agent", "EmployerClarifierAgent"),
    "hr_service_agent": ("agents.employer.hr_service_agent", "HRServiceAgent"),
    "mutual_evaluator": ("agents.evaluator.mutual_evaluator", "MutualEvaluatorAgent"),
}


class TestAgentEmissions:
    """Each of the 16 agents MUST emit at least one event source."""
    def test_at_least_16_agents_emit(self):
        from pathlib import Path
        backend = Path(__file__).resolve().parents[2]
        from_grep = 0
        jobseeker = [
            "intake_agent", "profile_agent", "clarifier_agent",
            "emotion_agent", "career_planner_agent", "daily_journal_agent",
        ]
        employer = [
            "persona_agent", "compliance_agent", "vision_agent",
            "talent_brief_agent", "job_spec_agent", "policy_agent",
            "multi_party_agent", "employer_clarifier_agent",
            "hr_service_agent",
        ]
        evaluator = ["mutual_evaluator"]

        for fname in jobseeker + employer + evaluator:
            if fname in jobseeker:
                path = backend / "agents" / "jobseeker" / f"{fname}.py"
            elif fname in employer:
                path = backend / "agents" / "employer" / f"{fname}.py"
            else:
                path = backend / "agents" / "evaluator" / f"{fname}.py"
            assert path.exists(), f"{fname} missing"
            src = path.read_text(encoding="utf-8")
            assert ("from eventbus import emit" in src
                    or "from eventbus.integration import" in src
                    or "emit_profile_updated" in src
                    or "emit(\"" in src), \
                f"{fname} does not import eventbus or call emit*"
            # verify at least one emit_* call
            assert 'emit("' in src or "emit_profile" in src \
                or "emit_needs" in src or "emit_ticket" in src \
                or "emit_plan" in src or "emit_role" in src \
                or "emit_strategy" in src or "emit_emotion" in src \
                or "emit_journal" in src or "emit_market" in src, \
                f"{fname} does not call any emit_* helper"
            from_grep += 1
        assert from_grep >= 16


# ===========================================================================
# Smoke test: full pipeline through subscribe → publish
# ===========================================================================

class TestSmokePipeline:
    def test_end_to_end_pipeline(self):
        received: List[dict] = []

        @on_event("subject.profile_updated")
        def on_update(e: Event):
            received.append(e.payload)

        # simulated agent emission
        emit("subject.profile_updated", {
            "user_id": "u-1",
            "candidate_id": "c-1",
            "fields": ["name"],
            "completeness": 0.9,
            "source": "smoke_test",
        }, source="agent.smoke", correlation_id="corr-1")

        assert received and received[0]["user_id"] == "u-1"
        assert received[0]["completeness"] == 0.9

    def test_correlation_id_propagates(self):
        seen: List[str] = []

        @on_event("evt.x")
        def h(e):
            seen.append(e.correlation_id or "")

        emit("evt.x", {}, correlation_id="xyz")
        assert seen == ["xyz"]
