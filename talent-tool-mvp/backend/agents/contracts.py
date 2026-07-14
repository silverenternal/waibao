"""v10.0 T5001 — Agent contracts (strong Pydantic schemas).

The runtime dataclasses in ``agents.runtime`` (``AgentInput`` / ``AgentOutput``
/ ``ToolCall``) are kept for backward compatibility with the 16 existing
agents.  This module adds **strongly-typed, validated** Pydantic mirrors used
by :class:`agents.gateway.AgentGateway` at the trust boundary:

* :class:`AgentInputModel`  — validated input envelope.
* :class:`AgentOutputModel` — validated output envelope.
* :class:`ToolCallModel`    — a single tool invocation record.
* :class:`AgentContract`    — per-agent declared input/output JSON schema +
  metadata, registered by each agent so the gateway can validate.

Everything round-trips with the runtime dataclasses via ``from_runtime`` /
``to_runtime`` so the gateway can accept either shape.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Persona vocabulary shared across the platform.
VALID_PERSONAS: tuple[str, ...] = (
    "jobseeker",
    "employer",
    "hr",
    "dept_head",
    "talent_partner",
    "admin",
    "super_admin",
    "system",
)


class ToolCallModel(BaseModel):
    """A single tool invocation performed by an agent."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, description="Registered tool name")
    args: dict[str, Any] = Field(default_factory=dict, description="Tool arguments")
    result: Any = Field(default=None, description="Tool result (if completed)")
    error: Optional[str] = Field(default=None, description="Error string on failure")
    duration_ms: int = Field(default=0, ge=0)


class AgentInputModel(BaseModel):
    """Validated agent input envelope.

    Stricter than the runtime dataclass: ``user_id``/``text`` are required
    and non-empty, ``persona`` is validated against the known vocabulary,
    and ``max_cost_cents`` is bounded.
    """

    model_config = ConfigDict(extra="allow")

    user_id: str = Field(..., min_length=1, description="Caller user id")
    persona: str = Field(..., description="Caller persona / role")
    text: str = Field(default="", description="Raw user input")
    context: dict[str, Any] = Field(default_factory=dict)
    memory_scope: str = Field(default="working")
    request_id: Optional[str] = Field(default=None, max_length=64)
    trace_id: Optional[str] = Field(default=None, max_length=64)
    tenant_id: Optional[str] = Field(default=None)
    max_cost_cents: int = Field(default=50, ge=0, le=100_000)

    @field_validator("persona")
    @classmethod
    def _validate_persona(cls, v: str) -> str:
        if v not in VALID_PERSONAS:
            raise ValueError(
                f"persona {v!r} not in {VALID_PERSONAS}"
            )
        return v

    @field_validator("memory_scope")
    @classmethod
    def _validate_scope(cls, v: str) -> str:
        allowed = {"short_term", "working", "long_term"}
        if v not in allowed:
            raise ValueError(f"memory_scope {v!r} not in {allowed}")
        return v

    # ---- interop with runtime dataclass ---------------------------------
    def to_runtime(self):
        from agents.runtime import AgentInput, MemoryScope

        kwargs: dict[str, Any] = dict(
            user_id=self.user_id,
            persona=self.persona,
            text=self.text,
            context=dict(self.context),
            memory_scope=MemoryScope(self.memory_scope),
            max_cost_cents=self.max_cost_cents,
        )
        if self.request_id:
            kwargs["request_id"] = self.request_id
        if self.trace_id:
            kwargs["trace_id"] = self.trace_id
        return AgentInput(**kwargs)

    @classmethod
    def from_runtime(cls, ai: Any) -> "AgentInputModel":
        scope = getattr(ai, "memory_scope", "working")
        scope_val = getattr(scope, "value", scope)
        return cls(
            user_id=ai.user_id,
            persona=ai.persona,
            text=getattr(ai, "text", "") or "",
            context=getattr(ai, "context", {}) or {},
            memory_scope=scope_val,
            request_id=getattr(ai, "request_id", None),
            trace_id=getattr(ai, "trace_id", None),
            max_cost_cents=getattr(ai, "max_cost_cents", 50),
        )


class AgentOutputModel(BaseModel):
    """Validated agent output envelope."""

    model_config = ConfigDict(extra="allow")

    agent_name: str = Field(..., min_length=1)
    text: str = Field(default="")
    artifacts: dict[str, Any] = Field(default_factory=dict)
    memory_writes: list[dict[str, Any]] = Field(default_factory=list)
    signals: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[ToolCallModel] = Field(default_factory=list)
    reasoning_chain: list[dict[str, Any]] = Field(default_factory=list)
    cost_cents: int = Field(default=0, ge=0)
    tokens_used: int = Field(default=0, ge=0)
    request_id: str = Field(default="")
    duration_ms: int = Field(default=0, ge=0)
    success: bool = Field(default=True)
    error: Optional[str] = Field(default=None)
    degraded: bool = Field(default=False, description="True when a fallback path served the request")

    @classmethod
    def from_runtime(cls, ao: Any) -> "AgentOutputModel":
        return cls(
            agent_name=ao.agent_name,
            text=getattr(ao, "text", "") or "",
            artifacts=getattr(ao, "artifacts", {}) or {},
            memory_writes=getattr(ao, "memory_writes", []) or [],
            signals=getattr(ao, "signals", []) or [],
            reasoning_chain=getattr(ao, "reasoning_chain", []) or [],
            cost_cents=getattr(ao, "cost_cents", 0) or 0,
            tokens_used=getattr(ao, "tokens_used", 0) or 0,
            request_id=getattr(ao, "request_id", "") or "",
            duration_ms=getattr(ao, "duration_ms", 0) or 0,
            success=getattr(ao, "success", True),
            error=getattr(ao, "error", None),
            degraded=bool(getattr(ao, "degraded", False)),
        )

    def to_runtime(self):
        from agents.runtime import AgentOutput

        out = AgentOutput(
            agent_name=self.agent_name,
            text=self.text,
            artifacts=dict(self.artifacts),
            memory_writes=list(self.memory_writes),
            signals=list(self.signals),
            cost_cents=self.cost_cents,
            tokens_used=self.tokens_used,
            request_id=self.request_id,
            duration_ms=self.duration_ms,
            success=self.success,
            error=self.error,
            reasoning_chain=list(self.reasoning_chain),
        )
        # attach degraded flag (dataclass has no field, set dynamically)
        setattr(out, "degraded", self.degraded)
        return out


class AgentContract(BaseModel):
    """Declared contract for a single agent.

    Each agent may expose ``input_model`` / ``output_model`` (Pydantic
    classes).  The gateway uses these to validate the envelope; when an
    agent declares nothing, the generic :class:`AgentInputModel` /
    :class:`AgentOutputModel` are used.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    version: str = "1.0.0"
    description: str = ""
    required_personas: tuple[str, ...] = ()
    input_model: type[BaseModel] = AgentInputModel
    output_model: type[BaseModel] = AgentOutputModel

    def validate_input(self, payload: Any) -> BaseModel:
        if isinstance(payload, self.input_model):
            return payload
        if isinstance(payload, BaseModel):
            payload = payload.model_dump()
        elif not isinstance(payload, dict):
            # runtime dataclass
            payload = AgentInputModel.from_runtime(payload).model_dump()
        return self.input_model.model_validate(payload)

    def validate_output(self, payload: Any) -> BaseModel:
        if isinstance(payload, self.output_model):
            return payload
        if isinstance(payload, BaseModel):
            payload = payload.model_dump()
        elif not isinstance(payload, dict):
            payload = AgentOutputModel.from_runtime(payload).model_dump()
        return self.output_model.model_validate(payload)

    def input_schema(self) -> dict[str, Any]:
        return self.input_model.model_json_schema()

    def output_schema(self) -> dict[str, Any]:
        return self.output_model.model_json_schema()


__all__ = [
    "VALID_PERSONAS",
    "ToolCallModel",
    "AgentInputModel",
    "AgentOutputModel",
    "AgentContract",
]
