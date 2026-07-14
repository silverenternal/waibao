"""T5014 — Security fail-fast startup gate.

Centralises the security pre-flight checks that run once at process
startup. Each check either passes silently or raises — there is **no**
silent fallback. The checks are:

1. ``check_jwt_secret``    — JWT signing secret present, length ≥ 32,
   not on the known-weak block-list.
2. ``check_cryptography``  — ``cryptography.fernet`` importable (no HMAC
   pseudo-encryption fallback for PII).
3. ``check_saml_lib``      — when ``SAML_REQUIRE_SIGNED_RESPONSE`` is on,
   ``python3-saml`` must be importable so SAML responses are actually
   signature-verified.
4. ``check_audit_coverage``— optional (off by default): every API route
   touching a canonical PII parameter carries ``@audit_pii``.

Run :func:`run_security_startup_checks` from the FastAPI lifespan. The
function honours ``SECURITY_STARTUP_STRICT`` (default ``"1"``): when
strict, a failing check aborts startup; when non-strict it logs and
continues (useful for ephemeral test/CI environments).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Callable

logger = logging.getLogger("waibao.security_startup")


class SecurityStartupError(RuntimeError):
    """Raised when a mandatory security check fails."""


def _is_strict() -> bool:
    val = os.getenv("SECURITY_STARTUP_STRICT", "1").strip().lower()
    return val not in ("0", "false", "no", "off")


def check_jwt_secret() -> str:
    """Ensure a valid JWT signing secret is configured.

    Returns the resolved secret on success. Raises
    :class:`SecurityStartupError` in strict mode; in non-strict mode
    re-raises ``JWTSecretError`` so :func:`run_security_startup_checks`
    can mark the check failed (rather than silently returning ``""``).
    """
    from services.auth.session import JWTSecretError, resolve_jwt_secret

    try:
        return resolve_jwt_secret()
    except JWTSecretError as exc:
        if _is_strict():
            raise SecurityStartupError(str(exc)) from exc
        logger.error("JWT secret check failed (non-strict, continuing): %s", exc)
        raise


def check_cryptography() -> None:
    """Ensure ``cryptography.fernet`` is importable."""
    from compliance.encryption import (
        CryptographyUnavailableError,
        assert_cryptography_available,
    )

    try:
        assert_cryptography_available()
    except CryptographyUnavailableError as exc:
        if _is_strict():
            raise SecurityStartupError(str(exc)) from exc
        logger.error("cryptography check failed (non-strict, continuing): %s", exc)


def check_saml_lib() -> bool:
    """When signed SAML responses are required, python3-saml must be present."""
    required = os.getenv("SAML_REQUIRE_SIGNED_RESPONSE", "").strip().lower() in (
        "1", "true", "yes", "on",
    )
    if not required:
        return True
    from services.auth.sso import _python3_saml_available

    if not _python3_saml_available():
        msg = (
            "SAML_REQUIRE_SIGNED_RESPONSE is enabled but python3-saml is not "
            "installed — SAML responses would not be signature-verified "
            "(T5014 fail-fast)."
        )
        if _is_strict():
            raise SecurityStartupError(msg)
        logger.error("%s (non-strict, continuing)", msg)
        return False
    return True


def check_audit_coverage(
    api_dir: str = "api",
    *,
    min_coverage_pct: float = 100.0,
) -> dict[str, Any]:
    """Report ``@audit_pii`` coverage of PII-touching API routes.

    Non-fatal by design: coverage gaps are surfaced as a warning so the
    team can drive them to 100% without blocking deploys. Set
    ``AUDIT_COVERAGE_STRICT=1`` to make sub-threshold coverage fatal.
    """
    from services.platform.audit_v2 import coverage_report

    report = coverage_report(api_dir=api_dir)
    pct = report.get("coverage_pct", 0.0)
    strict = os.getenv("AUDIT_COVERAGE_STRICT", "0").strip().lower() in (
        "1", "true", "yes", "on",
    )
    if pct < min_coverage_pct:
        msg = (
            f"PII audit decorator coverage {pct}% < required "
            f"{min_coverage_pct}% ({len(report.get('untracked_detail', []))} "
            f"untracked routes)"
        )
        if strict:
            raise SecurityStartupError(msg)
        logger.warning("%s — untracked: %s", msg, report.get("untracked_detail", []))
    return report


def run_security_startup_checks(
    *,
    checks: list[Callable[[], Any]] | None = None,
) -> dict[str, Any]:
    """Run every fail-fast security check, returning a summary.

    Raises :class:`SecurityStartupError` on the first mandatory failure
    when running strict.
    """
    checks = checks or [
        check_jwt_secret,
        check_cryptography,
        check_saml_lib,
    ]
    summary: dict[str, Any] = {"strict": _is_strict(), "checks": {}}
    for chk in checks:
        name = chk.__name__
        try:
            result = chk()
            summary["checks"][name] = {"ok": True, "result": result}
        except SecurityStartupError:
            raise
        except Exception as exc:  # noqa: BLE001
            if _is_strict():
                raise SecurityStartupError(f"{name} failed: {exc}") from exc
            summary["checks"][name] = {"ok": False, "error": str(exc)}
            logger.error("security check %s failed (non-strict): %s", name, exc)
    return summary


__all__ = [
    "SecurityStartupError",
    "run_security_startup_checks",
    "check_jwt_secret",
    "check_cryptography",
    "check_saml_lib",
    "check_audit_coverage",
]
