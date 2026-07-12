"""Unified exception type for the Mothership API (T1606).

The ``APIError`` is the single exception class that should be raised from
service / pipeline / agent code.  A global exception handler installed by
``setup.setup_application`` translates it to a structured JSON response
with HTTP status, error code, and optional headers.
"""
from __future__ import annotations

from typing import Any, Mapping

from errors import ErrorCode, default_message_for, http_status_for


class APIError(Exception):
    """Single exception class representing a public-facing API error.

    Parameters
    ----------
    code:
        An :class:`~errors.ErrorCode` member (preferred) or raw string.
    detail:
        Optional human-readable override.  If omitted, the default message
        for the code is used.
    status_code:
        Optional explicit HTTP status.  Defaults to the canonical status
        associated with the error code.
    headers:
        Optional dict of HTTP headers (e.g. ``Retry-After``).
    extra:
        Optional dict of additional fields merged into the response body.
    """

    def __init__(
        self,
        code: ErrorCode | str,
        detail: str | None = None,
        *,
        status_code: int | None = None,
        headers: Mapping[str, str] | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> None:
        self.code: ErrorCode | str = self._coerce_code(code)
        self.detail: str = detail or default_message_for(self.code) if isinstance(self.code, ErrorCode) else (detail or "Unknown error")
        self.status_code: int = status_code or (
            http_status_for(self.code) if isinstance(self.code, ErrorCode) else 500
        )
        self.headers: dict[str, str] = dict(headers or {})
        self.extra: dict[str, Any] = dict(extra or {})
        super().__init__(self.detail)

    @staticmethod
    def _coerce_code(code: ErrorCode | str) -> ErrorCode | str:
        """Return the canonical code, accepting strings for forward-compat."""
        if isinstance(code, ErrorCode):
            return code
        if isinstance(code, str):
            try:
                return ErrorCode(code)
            except ValueError:
                return code
        raise TypeError(f"code must be ErrorCode or str, got {type(code).__name__}")

    # ------------------------------------------------------------------
    # Convenience constructors
    # ------------------------------------------------------------------
    @classmethod
    def not_found(cls, resource: str = "Resource") -> "APIError":
        return cls(ErrorCode.NOT_FOUND, f"{resource} not found", status_code=404)

    @classmethod
    def forbidden(cls, detail: str = "Permission denied") -> "APIError":
        return cls(ErrorCode.FORBIDDEN, detail, status_code=403)

    @classmethod
    def unauthorized(cls, detail: str = "Authentication required") -> "APIError":
        return cls(ErrorCode.UNAUTHORIZED, detail, status_code=401)

    @classmethod
    def conflict(cls, detail: str = "Resource conflict") -> "APIError":
        return cls(ErrorCode.CONFLICT, detail, status_code=409)

    @classmethod
    def validation(cls, detail: str = "Validation error") -> "APIError":
        return cls(ErrorCode.VALIDATION_ERROR, detail, status_code=422)

    @classmethod
    def rate_limited(cls, retry_after: int | None = None) -> "APIError":
        headers = {"Retry-After": str(retry_after)} if retry_after else None
        return cls(ErrorCode.RATE_LIMITED, "Too many requests", status_code=429, headers=headers)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """Build the JSON body returned to clients."""
        code_value = self.code.value if isinstance(self.code, ErrorCode) else str(self.code)
        body: dict[str, Any] = {"detail": self.detail, "code": code_value}
        if self.extra:
            body.update(self.extra)
        return body

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        code_value = self.code.value if isinstance(self.code, ErrorCode) else str(self.code)
        return f"APIError(code={code_value!r}, status_code={self.status_code}, detail={self.detail!r})"


__all__ = ["APIError"]