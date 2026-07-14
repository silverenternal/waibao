"""外部供应商统一接入层.

支持的能力维度:
    LLM / Embedding / Vision / OCR / STT / Notify / CompanyLookup

切换供应商只需修改环境变量,无需改业务代码。

示例:
    from backend.providers import registry
    llm = registry.get_llm_provider()
    resp = await llm.chat(messages)
"""
from __future__ import annotations

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
from .contract import (  # v10.0 T5004 unified contract
    MockGateError,
    ProviderContract,
    ProviderErrorKind,
    make_contract,
)

__all__ = [
    "AuthError",
    "BudgetExceeded",
    "CircuitOpenError",
    "InvalidRequestError",
    "ProviderError",
    "QuotaExceededError",
    "RateLimitError",
    "TimeoutError",
    "UpstreamUnavailableError",
    # T5004 unified contract
    "ProviderContract",
    "ProviderErrorKind",
    "MockGateError",
    "make_contract",
]
