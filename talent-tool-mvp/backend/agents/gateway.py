"""v10.0 T5001 — Agent Gateway (strong-contract entry point).

``AgentGateway`` is the single, uniform door through which every agent
invocation should pass.  It wraps the existing :class:`agents.registry` +
:class:`agents.runtime.BaseAgent` machinery with enterprise guarantees:

* **Uniform input validation** — the payload is coerced through the agent's
  :class:`agents.contracts.AgentContract` (Pydantic).  Bad input becomes a
  typed :class:`AGENT_INPUT_INVALID` error, never a stack trace.
* **Uniform error handling** — all failures surface as an ``AgentOutput``
  with ``success=False`` and a stable error code, or (opt-in) raise a
  :class:`ServiceError`.
* **Uniform logging / metric / audit** — one structured log line + an
  EventBus ``agent.invoked`` / ``agent.failed`` event per call.
* **Uniform tracing** — an OpenTelemetry-style span around every run.
* **Automatic degradation** — when the underlying LLM/provider is down, the
  gateway serves a cached or mock response so the caller still gets a usable,
  ``degraded=True`` answer instead of a 500.

Backward compatibility: agents keep their own ``run()``; the gateway calls
into it.  Existing callers are untouched.  New callers use
``gateway.run(agent_name, input)``.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Optional

from agents.contracts import AgentContract, AgentInputModel, AgentOutputModel
from services.platform.errors import ServiceError, ServiceErrorCode

logger = logging.getLogger("recruittech.agents.gateway")


class AgentError(ServiceError):
    """Agent-scoped error (execution failed)."""

    def __init__(self, message: str = "Agent execution failed",
                 code: ServiceErrorCode = ServiceErrorCode.AGENT_EXECUTION_FAILED,
                 **kw: Any) -> None:
        super().__init__(code, message, **kw)


class AgentValidationError(ServiceError):
    def __init__(self, message: str = "Agent input invalid", **kw: Any) -> None:
        super().__init__(ServiceErrorCode.AGENT_INPUT_INVALID, message, **kw)


class ProviderError(ServiceError):
    def __init__(self, message: str = "LLM provider error", **kw: Any) -> None:
        super().__init__(ServiceErrorCode.LLM_PROVIDER_ERROR, message, **kw)


class AgentGateway:
    """Singleton front door for all agent runs."""

    _instance: Optional["AgentGateway"] = None

    def __init__(self, registry: Any = None) -> None:
        self._registry = registry
        self._contracts: dict[str, AgentContract] = {}
        # simple last-good-response cache for degradation, keyed by agent+user
        self._degradation_cache: dict[str, AgentOutputModel] = {}
        self._metrics: dict[str, dict[str, int]] = {}

    # ---- singleton ------------------------------------------------------
    @classmethod
    def instance(cls) -> "AgentGateway":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Test helper — drop the singleton and its state."""
        cls._instance = None

    # ---- registry access ------------------------------------------------
    @property
    def registry(self) -> Any:
        if self._registry is None:
            from agents.registry import registry as _reg
            self._registry = _reg
        return self._registry

    def contract_for(self, agent_name: str) -> AgentContract:
        """Return the declared contract for an agent (generic if none)."""
        if agent_name in self._contracts:
            return self._contracts[agent_name]
        agent = self.registry.get(agent_name)
        contract = getattr(agent, "contract", None) if agent else None
        if not isinstance(contract, AgentContract):
            contract = AgentContract(
                name=agent_name,
                version=getattr(agent, "version", "1.0.0") if agent else "1.0.0",
                description=getattr(agent, "description", "") if agent else "",
                required_personas=tuple(getattr(agent, "required_personas", ()) or ()) if agent else (),
            )
        self._contracts[agent_name] = contract
        return contract

    # ---- metrics --------------------------------------------------------
    def _bump(self, agent_name: str, key: str) -> None:
        m = self._metrics.setdefault(agent_name, {"ok": 0, "error": 0, "degraded": 0, "calls": 0})
        m[key] = m.get(key, 0) + 1

    def metrics(self) -> dict[str, dict[str, int]]:
        return {a: dict(v) for a, v in self._metrics.items()}

    # ---- core -----------------------------------------------------------
    async def run(
        self,
        agent_name: str,
        agent_input: Any,
        *,
        raise_on_error: bool = False,
        allow_degrade: bool = True,
        pii_policy: Any = None,
        injection_guard: Any = None,
    ) -> AgentOutputModel:
        """Run ``agent_name`` with ``agent_input`` under full governance.

        ``agent_input`` may be a runtime ``AgentInput`` dataclass, an
        :class:`AgentInputModel`, or a plain ``dict``.  Returns a validated
        :class:`AgentOutputModel`.  On failure, returns a failed output
        (``success=False``) unless ``raise_on_error`` is set.

        ``pii_policy`` / ``injection_guard`` — optional governance objects
        (see :mod:`agents.governance`).  When supplied the gateway runs them
        as a pre-flight on the input text before the agent executes.
        """
        start = time.time()
        request_id = str(uuid.uuid4())[:12]
        self._bump(agent_name, "calls")

        # 1. resolve agent -------------------------------------------------
        agent = self.registry.get(agent_name)
        if agent is None:
            err = AgentError(
                f"Agent '{agent_name}' not registered",
                code=ServiceErrorCode.AGENT_NOT_REGISTERED,
                details={"agent": agent_name},
            )
            return self._fail(agent_name, request_id, err, start, raise_on_error)

        contract = self.contract_for(agent_name)

        # 2. validate input ------------------------------------------------
        try:
            validated_in = contract.validate_input(agent_input)
        except Exception as exc:  # noqa: BLE001
            err = AgentValidationError(
                f"Invalid input for '{agent_name}': {exc}",
                details={"agent": agent_name},
                cause=exc,
            )
            return self._fail(agent_name, request_id, err, start, raise_on_error)

        # 3. persona guard -------------------------------------------------
        personas = tuple(getattr(agent, "required_personas", ()) or ())
        persona = getattr(validated_in, "persona", None)
        if personas and persona not in personas:
            err = ServiceError(
                ServiceErrorCode.AGENT_PERSONA_FORBIDDEN,
                f"persona '{persona}' not allowed for {agent_name}",
                details={"agent": agent_name, "persona": persona, "allowed": list(personas)},
            )
            return self._fail(agent_name, request_id, err, start, raise_on_error)

        # 3b. governance pre-flight (PII + injection) ---------------------
        in_text = getattr(validated_in, "text", "") or ""
        if injection_guard is not None:
            try:
                injection_guard.enforce(in_text)
            except ServiceError as exc:
                self._emit("agent.governance.blocked",
                           {"agent": agent_name, "request_id": request_id,
                            "reason": "injection", "code": exc.code_value})
                return self._fail(agent_name, request_id, exc, start, raise_on_error)
        if pii_policy is not None:
            try:
                scrubbed, findings = pii_policy.apply(in_text)
            except ServiceError as exc:
                self._emit("agent.governance.blocked",
                           {"agent": agent_name, "request_id": request_id,
                            "reason": "pii", "code": exc.code_value})
                return self._fail(agent_name, request_id, exc, start, raise_on_error)
            if findings and scrubbed != in_text:
                setattr(validated_in, "text", scrubbed)

        # 4. tracing + execute --------------------------------------------
        runtime_input = validated_in.to_runtime() if isinstance(validated_in, AgentInputModel) else validated_in
        self._emit("agent.invoked", {"agent": agent_name, "request_id": request_id,
                                      "persona": persona})
        span = self._start_span(agent_name, getattr(runtime_input, "trace_id", None))
        try:
            raw_output = await agent.run(runtime_input)
        except Exception as exc:  # noqa: BLE001
            self._end_span(span)
            # 5. degradation path -----------------------------------------
            if allow_degrade:
                degraded = self._degrade(agent_name, runtime_input, exc)
                if degraded is not None:
                    self._bump(agent_name, "degraded")
                    degraded.request_id = request_id
                    degraded.duration_ms = int((time.time() - start) * 1000)
                    logger.warning("[gateway] %s degraded after error: %s", agent_name, exc)
                    self._emit("agent.degraded", {"agent": agent_name,
                                                  "request_id": request_id, "error": str(exc)})
                    return degraded
            err = AgentError(
                f"Agent '{agent_name}' raised: {exc}",
                details={"agent": agent_name}, cause=exc,
            )
            return self._fail(agent_name, request_id, err, start, raise_on_error)
        finally:
            self._end_span(span)

        # 6. validate + normalize output ----------------------------------
        try:
            validated_out = AgentOutputModel.from_runtime(raw_output)
        except Exception as exc:  # noqa: BLE001
            err = ServiceError(
                ServiceErrorCode.AGENT_OUTPUT_INVALID,
                f"Agent '{agent_name}' produced invalid output: {exc}",
                details={"agent": agent_name}, cause=exc,
            )
            return self._fail(agent_name, request_id, err, start, raise_on_error)

        validated_out.request_id = request_id
        if not validated_out.duration_ms:
            validated_out.duration_ms = int((time.time() - start) * 1000)

        if validated_out.success:
            self._bump(agent_name, "ok")
            # cache last good output for future degradation
            self._degradation_cache[self._cache_key(agent_name, runtime_input)] = validated_out
            self._emit("agent.completed", {"agent": agent_name, "request_id": request_id,
                                           "duration_ms": validated_out.duration_ms})
        else:
            self._bump(agent_name, "error")
            self._emit("agent.failed", {"agent": agent_name, "request_id": request_id,
                                        "error": validated_out.error})
            if raise_on_error:
                raise AgentError(validated_out.error or "agent failed",
                                 details={"agent": agent_name})

        logger.info("[gateway] %s ok=%s degraded=%s %dms request_id=%s",
                    agent_name, validated_out.success, validated_out.degraded,
                    validated_out.duration_ms, request_id)
        return validated_out

    # ---- helpers --------------------------------------------------------
    def _cache_key(self, agent_name: str, runtime_input: Any) -> str:
        uid = getattr(runtime_input, "user_id", "anon")
        return f"{agent_name}:{uid}"

    def _degrade(self, agent_name: str, runtime_input: Any,
                 exc: Exception) -> Optional[AgentOutputModel]:
        """Best-effort degraded response when the primary path fails.

        Strategy: return the last good cached output for this agent+user;
        else a minimal, honest mock so the UI stays functional.
        """
        key = self._cache_key(agent_name, runtime_input)
        cached = self._degradation_cache.get(key)
        if cached is not None:
            clone = cached.model_copy(deep=True)
            clone.degraded = True
            clone.artifacts = {**clone.artifacts, "_degraded_reason": str(exc)}
            return clone
        # minimal mock fallback
        return AgentOutputModel(
            agent_name=agent_name,
            text="服务暂时不可用,已为你切换到降级模式。请稍后重试。",
            success=True,
            degraded=True,
            artifacts={"_degraded_reason": str(exc), "_fallback": "mock"},
        )

    def _fail(self, agent_name: str, request_id: str, err: ServiceError,
              start: float, raise_on_error: bool) -> AgentOutputModel:
        self._bump(agent_name, "error")
        logger.warning("[gateway] %s failed code=%s: %s",
                       agent_name, err.code_value, err.message)
        self._emit("agent.failed", {"agent": agent_name, "request_id": request_id,
                                    "code": err.code_value, "error": err.message})
        if raise_on_error:
            raise err
        return AgentOutputModel(
            agent_name=agent_name,
            text="",
            success=False,
            error=err.message,
            request_id=request_id,
            duration_ms=int((time.time() - start) * 1000),
            artifacts={"error_code": err.code_value, **({"details": dict(err.details)} if err.details else {})},
        )

    def _emit(self, event: str, payload: dict[str, Any]) -> None:
        try:
            from eventbus import emit
            emit(event, payload, source="agent.gateway")
        except Exception as exc:  # noqa: BLE001
            logger.debug("gateway emit %s failed: %s", event, exc)

    def _start_span(self, agent_name: str, trace_id: Optional[str]) -> Any:
        try:
            from agents.tracing import tracer
            return tracer.start_span(f"gateway.{agent_name}", trace_id=trace_id)
        except Exception:  # noqa: BLE001
            return None

    def _end_span(self, span: Any) -> None:
        if span is None:
            return
        try:
            from agents.tracing import tracer
            tracer.end_span()
        except Exception:  # noqa: BLE001
            pass


def get_gateway() -> AgentGateway:
    """Module-level accessor for the singleton gateway."""
    return AgentGateway.instance()


__all__ = [
    "AgentGateway",
    "get_gateway",
    "AgentError",
    "AgentValidationError",
    "ProviderError",
]
