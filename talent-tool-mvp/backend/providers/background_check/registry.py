"""BackgroundCheck Provider 子注册中心 (T1307)."""
from __future__ import annotations

import os
from threading import Lock

from ..exceptions import InvalidRequestError, ProviderError
from .base import BackgroundCheckProvider
from .mock import MockBackgroundCheckProvider

_bg_check: BackgroundCheckProvider | None = None
_lock = Lock()


def get_background_check_provider() -> BackgroundCheckProvider:
    global _bg_check
    if _bg_check is not None:
        return _bg_check
    with _lock:
        if _bg_check is not None:
            return _bg_check
        name = (os.getenv("BG_CHECK_PROVIDER") or "mock").lower()
        if name == "mock":
            _bg_check = MockBackgroundCheckProvider()
            return _bg_check
        if name == "checkr":
            from .checkr import CheckrProvider
            try:
                _bg_check = CheckrProvider()
                if not _bg_check._configured():  # type: ignore[attr-defined]
                    raise InvalidRequestError(
                        "Checkr credentials missing",
                        details={"env": ["CHECKR_API_KEY"]},
                    )
            except ProviderError:
                _bg_check = MockBackgroundCheckProvider()
            return _bg_check
        raise InvalidRequestError(
            f"unknown BG_CHECK_PROVIDER={name}",
            details={"supported": ["checkr", "mock"]},
        )


def reset_cache() -> None:
    global _bg_check
    with _lock:
        _bg_check = None


__all__ = ["get_background_check_provider", "reset_cache"]
