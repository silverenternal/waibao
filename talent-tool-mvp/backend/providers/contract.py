"""v10.0 T5004 — Unified ``ProviderContract``.

This module gives every provider (LLM / Vision / OCR / STT / Embedding /
Lookup / Notify …) a *single* declared contract so the rest of the platform
can reason about them uniformly:

* **Timeout** — a per-call wall-clock cap, defaulting from env.
* **Retry policy** — bound to the existing :class:`providers.base.RetryPolicy`.
* **Error taxonomy** — a normalised :class:`ProviderErrorKind` enum so the
  resilience layer and Prometheus metrics speak the same vocabulary.
* **Explicit mock gate** — ``mock_enabled`` is *never* inferred silently. It
  is read from the contract's ``mock_enabled`` flag, which defaults to the
  ``WAIBAO_PROVIDER_MOCK`` env var (explicit opt-in). A provider running in
  mock mode **must** declare it; the registry refuses to serve a real caller
  with a mock unless the gate is open. This closes the v10.0 audit finding
  where a missing key could silently downgrade a production call to a mock
  with no signal.

The contract is intentionally a pure dataclass + helpers — it has no I/O and
no third-party imports, so it can be imported from anywhere (tests, the
gateway, the registry) without pulling in network clients.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Optional

from .base import RetryPolicy
from .exceptions import (
    AuthError,
    BudgetExceeded,
    CircuitOpenError,
    InvalidRequestError,
    ProviderError,
    QuotaExceededError,
    RateLimitError,
    TimeoutError,
    UpstreamUnavailableError,
)


# ===========================================================================
# Error taxonomy
# ===========================================================================
class ProviderErrorKind(str, Enum):
    """Normalised provider error categories.

    The string value is used as the Prometheus label ``status`` so dashboards
    and alerts share one vocabulary with the retry / circuit layer.
    """

    OK = "ok"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    AUTH = "auth"
    QUOTA = "quota"
    BUDGET = "budget"
    INVALID_REQUEST = "invalid_request"
    UPSTREAM_UNAVAILABLE = "upstream_unavailable"
    CIRCUIT_OPEN = "circuit_open"
    UNKNOWN = "unknown"

    @classmethod
    def from_exception(cls, exc: BaseException) -> "ProviderErrorKind":
        """Map any raised exception to a normalised kind."""
        if exc is None:
            return cls.OK
        if isinstance(exc, TimeoutError):
            return cls.TIMEOUT
        if isinstance(exc, RateLimitError):
            return cls.RATE_LIMITED
        if isinstance(exc, AuthError):
            return cls.AUTH
        if isinstance(exc, QuotaExceededError):
            return cls.QUOTA
        if isinstance(exc, BudgetExceeded):
            return cls.BUDGET
        if isinstance(exc, InvalidRequestError):
            return cls.INVALID_REQUEST
        if isinstance(exc, CircuitOpenError):
            return cls.CIRCUIT_OPEN
        if isinstance(exc, UpstreamUnavailableError):
            return cls.UPSTREAM_UNAVAILABLE
        if isinstance(exc, ProviderError):
            return cls.UNKNOWN
        return cls.UNKNOWN

    def is_retryable(self) -> bool:
        """Whether the resilience layer should retry this kind."""
        return self in {
            self.TIMEOUT,
            self.RATE_LIMITED,
            self.UPSTREAM_UNAVAILABLE,
            self.CIRCUIT_OPEN,
        }


# ===========================================================================
# Mock gate — explicit, never inferred
# ===========================================================================
class MockGateError(RuntimeError):
    """Raised when a real caller is about to receive mock data without an
    explicit opt-in. This is a fail-closed guard: production traffic must
    never silently degrade to a mock."""


def _resolve_mock_default() -> bool:
    """Read the explicit env opt-in for provider mocking.

    ``WAIBAO_PROVIDER_MOCK=1`` (or ``true`` / ``yes``) enables the mock path
    globally. Absent / ``0`` => mocks are off. This is read at call time so
    tests can flip it via ``monkeypatch.setenv``.
    """
    raw = os.environ.get("WAIBAO_PROVIDER_MOCK", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


# ===========================================================================
# The contract
# ===========================================================================
@dataclass
class ProviderContract:
    """Declared capabilities + resilience knobs for a single provider.

    Providers construct one of these in ``__init__`` and expose it as
    ``self.contract``. The registry / gateway / metrics layer reads it to
    decide timeout, retry, mock fallback and error labelling.
    """

    name: str
    contract_type: str  # llm | embedding | vision | ocr | stt | lookup | notify ...
    supported_models: list[str] = field(default_factory=list)

    # Resilience knobs -------------------------------------------------------
    timeout_seconds: float = 30.0
    retry: RetryPolicy = field(default_factory=RetryPolicy)

    # Explicit mock gate -----------------------------------------------------
    # ``mock_enabled`` controls *whether this provider instance is a mock*.
    # It defaults to the WAIBAO_PROVIDER_MOCK env var so the decision is
    # always explicit and auditable.
    mock_enabled: bool = field(default_factory=_resolve_mock_default)
    # ``allow_mock_fallback`` controls whether a *real* call may degrade to
    # the mock provider when the real one is unavailable. Off by default —
    # silent mock fallback in production is an audit finding.
    allow_mock_fallback: bool = False

    # Cost / pricing hook ----------------------------------------------------
    cost_calculator: Optional[Callable[[Any], float]] = None
    pricing: Dict[str, tuple[float, float]] = field(default_factory=dict)

    # Metadata ---------------------------------------------------------------
    vendor: str = ""
    version: str = "1.0.0"
    extra: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.retry.max_retries < 0:
            raise ValueError("retry.max_retries must be >= 0")

    # ---- helpers ----------------------------------------------------------
    def assert_real_allowed(self) -> None:
        """Fail-closed: raise if this contract is a mock but the caller did
        not explicitly opt into mocks. Called by the registry before handing
        a provider to production traffic."""
        if self.mock_enabled and not _resolve_mock_default():
            raise MockGateError(
                f"provider {self.name!r} is a mock but WAIBAO_PROVIDER_MOCK "
                f"is not set — refusing to serve real traffic with mock data"
            )

    def fallback_to_mock_ok(self) -> bool:
        """Whether a failed real call may degrade to the mock provider."""
        return self.allow_mock_fallback and _resolve_mock_default()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "contract_type": self.contract_type,
            "supported_models": list(self.supported_models),
            "timeout_seconds": self.timeout_seconds,
            "retry": {
                "max_retries": self.retry.max_retries,
                "base_delay": self.retry.base_delay,
                "max_delay": self.retry.max_delay,
            },
            "mock_enabled": self.mock_enabled,
            "allow_mock_fallback": self.allow_mock_fallback,
            "vendor": self.vendor,
            "version": self.version,
        }


# ===========================================================================
# Convenience constructor used by provider base classes
# ===========================================================================
def make_contract(
    name: str,
    contract_type: str,
    *,
    timeout_seconds: Optional[float] = None,
    max_retries: Optional[int] = None,
    base_delay: Optional[float] = None,
    max_delay: Optional[float] = None,
    mock_enabled: Optional[bool] = None,
    allow_mock_fallback: bool = False,
    supported_models: Optional[list[str]] = None,
    pricing: Optional[Dict[str, tuple[float, float]]] = None,
    vendor: str = "",
) -> ProviderContract:
    """Build a :class:`ProviderContract` with sensible env-driven defaults.

    Timeout and retry defaults are read from ``PROVIDER_TIMEOUT_SECONDS`` /
    ``PROVIDER_MAX_RETRIES`` / ``PROVIDER_BASE_DELAY`` env vars when the
    caller does not pass them explicitly, so operators can tune the whole
    fleet without a deploy.
    """
    if timeout_seconds is None:
        try:
            timeout_seconds = float(os.environ.get("PROVIDER_TIMEOUT_SECONDS", "30"))
        except ValueError:
            timeout_seconds = 30.0
    if max_retries is None:
        try:
            max_retries = int(os.environ.get("PROVIDER_MAX_RETRIES", "3"))
        except ValueError:
            max_retries = 3
    if base_delay is None:
        try:
            base_delay = float(os.environ.get("PROVIDER_BASE_DELAY", "1.0"))
        except ValueError:
            base_delay = 1.0
    if max_delay is None:
        max_delay = 30.0

    return ProviderContract(
        name=name,
        contract_type=contract_type,
        supported_models=list(supported_models or []),
        timeout_seconds=timeout_seconds,
        retry=RetryPolicy(
            max_retries=max_retries,
            base_delay=base_delay,
            max_delay=max_delay,
        ),
        mock_enabled=_resolve_mock_default() if mock_enabled is None else mock_enabled,
        allow_mock_fallback=allow_mock_fallback,
        pricing=dict(pricing or {}),
        vendor=vendor,
    )


__all__ = [
    "ProviderContract",
    "ProviderErrorKind",
    "MockGateError",
    "make_contract",
]
