"""v10.0 T5016 — Privacy / data-protection compliance services.

This package hosts the **service-layer** logic for the multi-regime privacy
framework (GDPR + PIPL + CCPA/CPRA).  It is intentionally storage-agnostic —
each service accepts a thin store protocol so unit tests can drive it with an
in-memory dict while production wires a Supabase/Postgres implementation.

Modules
-------
* :mod:`services.compliance.ccpa`        — CCPA/CPRA opt-out (Do Not Sell /
  Share), right-to-know, right-to-delete, verification + agent flows.
* :mod:`services.compliance.data_export` — portable data export (Art. 20) with
  the PIPL cross-border transfer declaration stamped onto every bundle.
* :mod:`services.compliance.breach`      — Art. 33/34 breach register with the
  72-hour authority-notification clock + subject-notification policy.

The matching API surfaces live under :mod:`api.gdpr_v2` (existing) and the new
:mod:`api.breach` (Art. 33 workflow) and :mod:`api.ccpa` (CCPA endpoints).
"""
from __future__ import annotations

__all__ = [
    "ccpa",
    "data_export",
    "breach",
]
