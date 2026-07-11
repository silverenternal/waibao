"""Provider 统一异常体系.

所有外部供应商调用失败时,统一抛 ProviderError 子类。
业务层只需要捕获 ProviderError 即可。
"""
from __future__ import annotations

from typing import Any


class ProviderError(Exception):
    """所有 Provider 异常的基类."""

    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        status_code: int | None = None,
        retryable: bool = True,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.status_code = status_code
        self.retryable = retryable
        self.details = details or {}


class AuthError(ProviderError):
    """认证失败 (401/403),不可重试."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, retryable=False, **kwargs)


class RateLimitError(ProviderError):
    """触发供应商限流 (429),可重试."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, status_code=429, retryable=True, **kwargs)


class QuotaExceededError(ProviderError):
    """账户配额耗尽,不可重试."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, status_code=402, retryable=False, **kwargs)


class BudgetExceeded(ProviderError):
    """租户日预算超限,熔断该租户调用."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, retryable=False, **kwargs)


class CircuitOpenError(ProviderError):
    """熔断器打开,直接拒绝."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, retryable=True, **kwargs)


class TimeoutError(ProviderError):  # noqa: A001 - 故意覆盖 builtin 风格
    """请求超时."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, retryable=True, **kwargs)


class InvalidRequestError(ProviderError):
    """参数非法,不可重试."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, status_code=400, retryable=False, **kwargs)


class UpstreamUnavailableError(ProviderError):
    """上游 5xx 或网络故障,可重试."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, status_code=503, retryable=True, **kwargs)
