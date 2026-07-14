"""v10.0 T5017 — SSRF guard for outbound webhook / fetch targets.

Server-Side Request Forgery is the highest-impact bug class on webhook
dispatchers: a tenant who can register an arbitrary callback URL can probe the
internal network (``169.254.169.254`` metadata, ``10.x``, ``127.x``, internal
admins).  This module provides a single, well-tested gate that every outbound
HTTP call site should use:

    >>> from services.security.ssrf import assert_safe_url
    >>> assert_safe_url("http://169.254.169.254/latest/meta-data/")  # raises
    >>> assert_safe_url("https://example.com/webhook")                # ok

Defence in depth (three layers, all must pass):

1. **Scheme allow-list** — only ``http``/``https``; no ``file://``, ``gopher://``,
   ``dict://``, ``ftp://``.
2. **Host allow/deny** — block obvious internal hostnames (``localhost``,
   ``metadata.google.internal``, ``*.internal``) and any host that *resolves*
   to a private / loopback / link-local / reserved address.
3. **Post-DNS re-resolve** — because DNS can flip between lookups (rebinding),
   the canonical helper :func:`resolve_safe_targets` resolves the host **once**
   and returns the validated IPs so the HTTP client can connect by IP with a
   forced ``Host`` header, eliminating the rebinding window.

The check uses :mod:`ipaddress` so it is correct for both v4 and v6, including
the IPv6-mapped-v4 and IPv6 loopback edge cases.
"""
from __future__ import annotations

import ipaddress
import logging
import os
import socket
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger("waibao.security.ssrf")

ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})

# Hostnames that are *textually* internal — caught before any DNS lookup.
BLOCKED_HOSTNAMES: frozenset[str] = frozenset({
    "localhost",
    "metadata.google.internal",          # GCP metadata
    "metadata.aws.internal",
    "169.254.169.254",                    # AWS/Azure/GCP metadata IP literal
    "metadata.azure.com",
})

# Suffixes that imply an internal/corporate host.
BLOCKED_HOST_SUFFIXES: tuple[str, ...] = (
    ".internal",
    ".local",
    ".localhost",
    ".corp",
    ".intra",
    ".lan",
)

# Optional allow-list of egress domains (comma-separated env).  When set, ONLY
# these domains are permitted (deny-list still applies).  Empty = allow any
# public host.
_egress_allow_env = os.getenv("WEBHOOK_EGRESS_ALLOWLIST", "").strip()
EGRESS_ALLOWLIST: frozenset[str] = frozenset(
    h.strip().lower() for h in _egress_allow_env.split(",") if h.strip()
) if _egress_allow_env else frozenset()

# When True (default), block link-local 169.254.0.0/16 hard — this is the
# cloud-metadata range and must never be reachable.
BLOCK_LINK_LOCAL = os.getenv("SSRF_BLOCK_LINK_LOCAL", "1") not in ("0", "false", "False")


class SSRFError(ValueError):
    """Raised when a URL targets a forbidden host / IP."""


@dataclass(frozen=True)
class ResolvedTarget:
    """Result of :func:`resolve_safe_targets` — connect by IP, set Host header."""
    original_host: str
    safe_ips: list[str]
    port: int


# ---------------------------------------------------------------------------
# IP classification
# ---------------------------------------------------------------------------
def is_private_ip(ip: str) -> bool:
    """True if the IP is loopback / private / link-local / reserved / multicast.

    Covers both IPv4 and IPv6 (including ``::1`` and IPv4-mapped ``::ffff:...``).
    """
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        # Not a parseable IP literal → treat as private to be safe.
        return True
    # ip_address.is_private covers most RFC1918 + loopback + link-local + etc.
    # We additionally hard-block link-local + multicast + reserved explicitly.
    if addr.is_loopback or addr.is_private or addr.is_reserved or addr.is_multicast:
        return True
    if BLOCK_LINK_LOCAL and addr.is_link_local:
        return True
    # IPv4-mapped IPv6 (e.g. ::ffff:127.0.0.1) — ipaddress handles this via the
    # underlying IPv4, but double-check the mapped form explicitly.
    if isinstance(addr, ipaddress.IPv6Address):
        if addr.ipv4_mapped is not None:
            return is_private_ip(str(addr.ipv4_mapped))
    return False


# ---------------------------------------------------------------------------
# URL validation (no DNS yet)
# ---------------------------------------------------------------------------
def _is_ip_literal(host: str) -> bool:
    """True iff ``host`` is a parseable IPv4/IPv6 literal."""
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def assert_safe_url(url: str, *, allow_private: bool = False) -> None:
    """Validate ``url``'s scheme + host textually.  Raises :class:`SSRFError`.

    This is the **first** gate — cheap, no network.  For the full defence
    (including DNS rebinding) use :func:`resolve_safe_targets`.
    """
    if not url or not isinstance(url, str):
        raise SSRFError("empty url")
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        raise SSRFError(f"forbidden scheme: {scheme!r} (allowed: {sorted(ALLOWED_SCHEMES)})")
    host = (parsed.hostname or "").lower()
    if not host:
        raise SSRFError("missing host")
    # If the host is already an IP literal, classify it directly.
    # NOTE: is_ip_literal must be checked separately so the ``except`` below
    # never swallows the SSRFError we raise (SSRFError subclasses ValueError).
    is_ip_literal = _is_ip_literal(host)
    if is_ip_literal:
        if not allow_private and is_private_ip(host):
            raise SSRFError(f"target IP is private/loopback: {host}")
    else:
        # hostname rules
        if host in BLOCKED_HOSTNAMES:
            raise SSRFError(f"blocked hostname: {host}")
        if any(host.endswith(suf) for suf in BLOCKED_HOST_SUFFIXES):
            raise SSRFError(f"blocked internal hostname suffix: {host}")
        if EGRESS_ALLOWLIST and host not in EGRESS_ALLOWLIST:
            raise SSRFError(f"host not in egress allowlist: {host}")


# ---------------------------------------------------------------------------
# DNS resolution + post-resolve check (defeats rebinding)
# ---------------------------------------------------------------------------
def resolve_safe_targets(url: str, *, allow_private: bool = False) -> ResolvedTarget:
    """Resolve ``url``'s host to IP(s) and verify **every** address is public.

    Returns a :class:`ResolvedTarget` so the caller can connect by IP (avoiding a
    second DNS lookup that could rebound).  Raises :class:`SSRFError` if any
    resolved address is private/loopback/link-local, or if resolution fails.
    """
    assert_safe_url(url, allow_private=allow_private)
    parsed = urlparse(url)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SSRFError(f"DNS resolution failed for {host}: {exc}") from exc
    safe_ips: list[str] = []
    for family, _stype, _proto, _canon, sockaddr in infos:
        ip = sockaddr[0]
        # IPv6 sockaddr may carry scope id; strip it.
        if "%" in ip:
            ip = ip.split("%", 1)[0]
        if not allow_private and is_private_ip(ip):
            raise SSRFError(f"host {host} resolves to private IP {ip}")
        safe_ips.append(ip)
    if not safe_ips:
        raise SSRFError(f"host {host} resolved to no addresses")
    return ResolvedTarget(original_host=host, safe_ips=safe_ips, port=port)


def is_safe_url(url: str, *, allow_private: bool = False) -> bool:
    """Non-raising variant of :func:`assert_safe_url` (textual check only)."""
    try:
        assert_safe_url(url, allow_private=allow_private)
        return True
    except SSRFError:
        return False


__all__ = [
    "ALLOWED_SCHEMES",
    "BLOCKED_HOSTNAMES",
    "BLOCKED_HOST_SUFFIXES",
    "EGRESS_ALLOWLIST",
    "SSRFError",
    "ResolvedTarget",
    "is_private_ip",
    "assert_safe_url",
    "resolve_safe_targets",
    "is_safe_url",
]
