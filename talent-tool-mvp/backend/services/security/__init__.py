"""v10.0 T5017 — security primitives package.

* :mod:`services.security.rate_limiter` — 3-tier (L1 per-IP / L2 per-user /
  L3 per-tenant) rate limiting layered on top of the existing slowapi limiter.
* :mod:`services.security.ssrf` — SSRF guard used by the webhook dispatcher
  (block private / link-local / loopback + re-resolve after DNS).
* :mod:`services.security.csrf` — double-submit CSRF token middleware.
"""
from __future__ import annotations

__all__ = ["rate_limiter", "ssrf", "csrf"]
