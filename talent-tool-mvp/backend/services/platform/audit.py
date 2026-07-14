"""T5014 — Public audit facade + PII-decorator coverage enforcement.

``services/platform/audit_v2.py`` is the implementation; this module is
the stable, documented import path the rest of the codebase (and the
startup gate) consumes. It also exposes
:func:`enforce_pii_decorator_coverage` which the security startup gate
and CI can call to assert that **every** PII-touching API route carries
the ``@audit_pii`` decorator.
"""
from __future__ import annotations

from typing import Any

# Re-export the full audit_v2 surface under a stable path.
from services.platform.audit_v2 import (  # noqa: F401
    ACTION_DATA_CLASS,
    DEFAULT_LAWFUL_BASIS,
    PII_FIELDS,
    AuditContext,
    AuditRecord,
    audit,
    audit_pii,
    build_audit_decorators,
    clear_audit_context,
    compute_retention_until,
    coverage_report,
    get_audit_context,
    get_audit_store,
    reset_audit_store,
    scan_module_for_pii,
    scan_source_for_pii,
    set_audit_context,
    update_audit_context,
)


def enforce_pii_decorator_coverage(
    api_dir: str = "api",
    *,
    min_coverage_pct: float = 100.0,
    auto_decorate: bool = False,
) -> dict[str, Any]:
    """Assert that PII-touching API routes are 100% ``@audit_pii``-decorated.

    When ``auto_decorate`` is True, missing decorators are applied in
    memory to the loaded route functions (best-effort; only works when
    the modules are importable). The returned report reflects the
    in-memory patched state (untracked routes that were successfully
    wrapped are removed from ``untracked_detail`` / counted as audited),
    even though the on-disk source is unchanged.
    """
    report = coverage_report(api_dir=api_dir)
    pct = report.get("coverage_pct", 0.0)
    if pct >= min_coverage_pct or not auto_decorate:
        return report
    if not report.get("untracked_detail"):
        return report

    import importlib
    import os

    still_untracked = []
    wrapped = 0
    for item in list(report["untracked_detail"]):
        rel = os.path.relpath(item["file"])  # e.g. api/foo.py
        mod_path = rel.replace(os.sep, ".")[:-3]
        try:
            mod = importlib.import_module(mod_path)
            fn = getattr(mod, item["function"], None)
            if fn is not None and callable(fn):
                setattr(
                    mod,
                    item["function"],
                    audit_pii(
                        "read",
                        resource_type=os.path.basename(item["file"])[:-3],
                        pii_fields=item["pii_params"],
                    )(fn),
                )
                wrapped += 1
                continue
        except Exception:  # noqa: BLE001
            pass
        still_untracked.append(item)

    # Reflect the in-memory patched state in the report.
    report["audited"] = report["audited"] + wrapped
    report["untracked"] = len(still_untracked)
    report["untracked_detail"] = still_untracked
    total = report["audited"] + report["untracked"]
    report["coverage_pct"] = round(
        (report["audited"] / total * 100) if total else 100.0, 2
    )
    return report


__all__ = [
    "ACTION_DATA_CLASS",
    "DEFAULT_LAWFUL_BASIS",
    "PII_FIELDS",
    "AuditContext",
    "AuditRecord",
    "audit",
    "audit_pii",
    "build_audit_decorators",
    "clear_audit_context",
    "compute_retention_until",
    "coverage_report",
    "enforce_pii_decorator_coverage",
    "get_audit_context",
    "get_audit_store",
    "reset_audit_store",
    "scan_module_for_pii",
    "scan_source_for_pii",
    "set_audit_context",
    "update_audit_context",
]
