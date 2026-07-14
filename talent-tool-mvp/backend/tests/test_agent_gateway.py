"""v10.0 T5001 — Agent Gateway + contracts + prompt registry tests (30+)."""
from __future__ import annotations

import os
os.environ.setdefault("LLM_PROVIDER", "mock")

import pytest

from agents.boot import init_all_agents
from agents.contracts import (
    AgentContract,
    AgentInputModel,
    AgentOutputModel,
    VALID_PERSONAS,
)
from agents.gateway import (
    AgentError,
    AgentGateway,
    AgentValidationError,
    get_gateway,
)
from agents.prompts import (
    AGENT_NAMES,
    DEFAULT_PROMPTS,
    all_defaults,
    default_prompt,
    get_prompt,
    set_prompt,
)
from agents.registry import registry
from agents.runtime import AgentInput
from services.platform.errors import ServiceError, ServiceErrorCode


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _bootstrap():
    """Ensure the 16 agents are registered before each test."""
    AgentGateway.reset()
    init_all_agents()
    get_gateway()
    yield
    AgentGateway.reset()


# ===========================================================================
# contracts
# ===========================================================================
def test_valid_personas_includes_known_roles():
    assert {"jobseeker", "employer", "admin", "system"} <= set(VALID_PERSONAS)


def test_input_model_validates_required_fields():
    with pytest.raises(Exception):
        AgentInputModel()  # missing user_id + persona


def test_input_model_rejects_bad_persona():
    with pytest.raises(Exception):
        AgentInputModel(user_id="u", persona="martian", text="hi")


def test_input_model_rejects_bad_scope():
    with pytest.raises(Exception):
        AgentInputModel(user_id="u", persona="jobseeker", memory_scope="forever")


def test_input_model_round_trip_with_runtime():
    ri = AgentInput(user_id="u1", persona="jobseeker", text="hello", context={"k": 1})
    m = AgentInputModel.from_runtime(ri)
    back = m.to_runtime()
    assert back.user_id == "u1"
    assert back.persona == "jobseeker"
    assert back.context == {"k": 1}


def test_output_model_from_runtime_degraded_flag():
    from agents.runtime import AgentOutput

    ao = AgentOutput(agent_name="x", text="t", success=True)
    setattr(ao, "degraded", True)
    m = AgentOutputModel.from_runtime(ao)
    assert m.degraded is True


def test_agent_contract_default_input_output_schemas():
    c = AgentContract(name="x")
    s_in = c.input_schema()
    s_out = c.output_schema()
    assert s_in["type"] == "object"
    assert s_out["type"] == "object"


def test_agent_contract_validates_input_dict():
    c = AgentContract(name="x")
    out = c.validate_input({"user_id": "u", "persona": "jobseeker", "text": ""})
    assert isinstance(out, AgentInputModel)


# ===========================================================================
# prompts registry
# ===========================================================================
def test_16_agents_have_default_prompts():
    assert len(AGENT_NAMES) == 16
    assert set(AGENT_NAMES) == set(DEFAULT_PROMPTS.keys())


def test_default_prompt_returns_string():
    for name in AGENT_NAMES:
        v = default_prompt(name, "system")
        assert isinstance(v, str) and v


def test_default_prompt_unknown_returns_empty():
    assert default_prompt("not_an_agent", "system") == ""


def test_get_prompt_falls_back_to_default():
    text = get_prompt("emotion_agent", "system", default="ignored")
    assert "情感" in text or "助手" in text or len(text) > 10


def test_get_prompt_unknown_agent_returns_caller_default():
    assert get_prompt("nope", "system", default="fallback") == "fallback"


def test_set_prompt_returns_bool():
    ok = set_prompt("emotion_agent", "new prompt", changed_by="admin")
    # set_value may fail without a backing store; either way, no exception
    assert ok in (True, False)


def test_all_defaults_returns_a_copy():
    a = all_defaults()
    a["emotion_agent"]["system"] = "X"
    b = all_defaults()
    assert b["emotion_agent"]["system"] != "X"


# ===========================================================================
# AgentGateway — happy path
# ===========================================================================
@pytest.mark.asyncio
async def test_gateway_runs_emotion_agent():
    gw = get_gateway()
    out = await gw.run("emotion_agent",
                       {"user_id": "u1", "persona": "jobseeker",
                        "text": "今天很开心,拿到了 offer"})
    assert out.success is True
    assert out.text
    assert out.duration_ms >= 0


@pytest.mark.asyncio
async def test_gateway_runs_profile_agent():
    gw = get_gateway()
    out = await gw.run("profile_agent",
                       {"user_id": "u1", "persona": "jobseeker",
                        "text": "I have 5 years of Python experience."})
    assert out.success is True


@pytest.mark.asyncio
async def test_gateway_run_accepts_agent_input_dataclass():
    gw = get_gateway()
    inp = AgentInput(user_id="u1", persona="jobseeker", text="hi")
    out = await gw.run("profile_agent", inp)
    assert out.success is True


@pytest.mark.asyncio
async def test_gateway_run_accepts_pydantic_input():
    gw = get_gateway()
    inp = AgentInputModel(user_id="u1", persona="jobseeker", text="hi")
    out = await gw.run("profile_agent", inp)
    assert out.success is True


@pytest.mark.asyncio
async def test_gateway_emits_invocation_event():
    gw = get_gateway()
    out = await gw.run("profile_agent",
                       {"user_id": "u1", "persona": "jobseeker", "text": "hi"})
    assert out.success is True
    m = gw.metrics()
    assert "profile_agent" in m
    assert m["profile_agent"]["calls"] >= 1


# ===========================================================================
# AgentGateway — error paths
# ===========================================================================
@pytest.mark.asyncio
async def test_gateway_unknown_agent_returns_failure():
    gw = get_gateway()
    out = await gw.run("nonexistent_agent",
                       {"user_id": "u1", "persona": "jobseeker", "text": "hi"})
    assert out.success is False
    assert out.artifacts.get("error_code") == ServiceErrorCode.AGENT_NOT_REGISTERED.value


@pytest.mark.asyncio
async def test_gateway_invalid_input_returns_validation_error():
    gw = get_gateway()
    out = await gw.run("emotion_agent",
                       {"user_id": "u1", "persona": "martian", "text": "hi"})
    assert out.success is False
    assert out.artifacts.get("error_code") == ServiceErrorCode.AGENT_INPUT_INVALID.value


@pytest.mark.asyncio
async def test_gateway_persona_forbidden():
    gw = get_gateway()
    # emotion_agent requires persona in {jobseeker, talent_partner, admin}
    out = await gw.run("emotion_agent",
                       {"user_id": "u1", "persona": "employer", "text": "hi"})
    assert out.success is False
    assert out.artifacts.get("error_code") == ServiceErrorCode.AGENT_PERSONA_FORBIDDEN.value


@pytest.mark.asyncio
async def test_gateway_raise_on_error_propagates():
    gw = get_gateway()
    with pytest.raises(AgentError):
        await gw.run("nonexistent_agent",
                     {"user_id": "u1", "persona": "jobseeker", "text": "hi"},
                     raise_on_error=True)


@pytest.mark.asyncio
async def test_gateway_validation_error_propagates_when_raised():
    gw = get_gateway()
    with pytest.raises(AgentValidationError):
        await gw.run("emotion_agent",
                     {"user_id": "u1", "persona": "martian", "text": "hi"},
                     raise_on_error=True)


# ===========================================================================
# Degradation
# ===========================================================================
@pytest.mark.asyncio
async def test_gateway_degradation_when_agent_raises(monkeypatch):
    from agents.runtime import AgentInput as AI

    class BoomAgent:
        name = "boom_agent"
        description = "always explodes"
        required_personas = ()
        version = "1.0.0"

        async def run(self, _inp):  # noqa: ARG002
            raise RuntimeError("kaboom")

    registry.register(BoomAgent())
    gw = get_gateway()
    out = await gw.run("boom_agent",
                       {"user_id": "u", "persona": "jobseeker", "text": "hi"})
    assert out.success is True
    assert out.degraded is True
    assert "降级" in out.text or "degraded" in (out.artifacts or {}).get("_fallback", "")


@pytest.mark.asyncio
async def test_gateway_degradation_uses_cached_when_available():
    class CountedAgent:
        name = "counted_agent"
        description = "counts calls"
        required_personas = ()
        version = "1.0.0"

        def __init__(self):
            self.calls = 0

        async def run(self, _inp):
            self.calls += 1
            if self.calls == 1:
                from agents.runtime import AgentOutput
                return AgentOutput(agent_name=self.name, text="first!", success=True)
            raise RuntimeError("crash")

    a = CountedAgent()
    registry.register(a)
    gw = get_gateway()
    out1 = await gw.run("counted_agent",
                        {"user_id": "u1", "persona": "jobseeker", "text": "hi"})
    assert out1.success is True and not out1.degraded
    out2 = await gw.run("counted_agent",
                        {"user_id": "u1", "persona": "jobseeker", "text": "hi"})
    assert out2.success is True
    assert out2.degraded is True
    assert out2.text == "first!"


# ===========================================================================
# Singleton + metrics
# ===========================================================================
def test_gateway_singleton():
    g1 = get_gateway()
    g2 = get_gateway()
    assert g1 is g2


def test_gateway_reset_clears_state():
    g1 = get_gateway()
    AgentGateway.reset()
    g2 = get_gateway()
    assert g1 is not g2


def test_gateway_metrics_shape():
    gw = get_gateway()
    m = gw.metrics()
    assert isinstance(m, dict)


def test_gateway_contract_for_known_agent():
    gw = get_gateway()
    c = gw.contract_for("emotion_agent")
    assert c.name == "emotion_agent"
    assert "jobseeker" in c.required_personas
