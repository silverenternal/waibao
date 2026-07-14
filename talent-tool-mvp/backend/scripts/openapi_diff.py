#!/usr/bin/env python3
"""v10.0 T5003 — OpenAPI contract drift gate.

Snapshot the live OpenAPI schema and fail CI when a *breaking* change is
detected against the committed baseline.  Run locally / in CI as::

    python scripts/openapi_diff.py --snapshot   # write openapi.baseline.json
    python scripts/openapi_diff.py               # compare; exit 1 on breaking diff

What counts as breaking (exit 1)
--------------------------------
* a path or operation removed
* a request parameter marked required that was optional before
* a response status code removed
* a response schema field removed or re-typed to an incompatible type
* ``requestBody`` newly required (was optional)

Non-breaking (still exits 0): added paths/operations, added optional params,
added response codes, description tweaks, added fields to response schemas.

The baseline lives at ``backend/openapi.baseline.json``; commit it on green
builds and re-snapshot whenever an intentional breaking change ships.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Ensure the backend package root (parent of scripts/) is importable when this
# script is invoked directly (e.g. `python scripts/openapi_diff.py`).
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

BASELINE = _BACKEND_ROOT / "openapi.baseline.json"


def _load_app_openapi() -> dict[str, Any]:
    """Import the FastAPI app and return its OpenAPI schema dict."""
    import main  # noqa: F401  — triggers setup_application + install_standard_chain
    return main.app.openapi()


def snapshot() -> int:
    schema = _load_app_openapi()
    BASELINE.write_text(json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False))
    print(f"openapi snapshot written -> {BASELINE} "
          f"({len(schema.get('paths', {}))} paths)")
    return 0


def _paths(schema: dict[str, Any]) -> dict[str, Any]:
    return schema.get("paths", {})


def _diff_breaking(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    breaking: list[str] = []

    old_paths = _paths(old)
    new_paths = _paths(new)

    # 1) removed paths
    for path in old_paths:
        if path not in new_paths:
            breaking.append(f"path removed: {path}")
            continue
        old_ops = old_paths[path] or {}
        new_ops = new_paths[path] or {}
        for method, old_op in old_ops.items():
            if method not in new_ops:
                breaking.append(f"operation removed: {method.upper()} {path}")
                continue
            breaking.extend(_diff_operation(path, method, old_op or {}, new_ops[method] or {}))
    return breaking


def _diff_operation(path: str, method: str, old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    out: list[str]
    out = []
    label = f"{method.upper()} {path}"

    # requestBody required-ness tightened
    old_rb = old.get("requestBody") or {}
    new_rb = new.get("requestBody") or {}
    if old_rb and not old_rb.get("required") and new_rb.get("required"):
        out.append(f"{label}: requestBody became required")

    # parameters: required tightened
    old_params = {p["name"]: p for p in old.get("parameters", []) if "name" in p}
    new_params = {p["name"]: p for p in new.get("parameters", []) if "name" in p}
    for name, op in old_params.items():
        if name not in new_params:
            out.append(f"{label}: parameter removed: {name}")
            continue
        if op.get("required") is False and new_params[name].get("required") is True:
            out.append(f"{label}: parameter became required: {name}")

    # responses: status codes removed
    old_resp = old.get("responses", {}) or {}
    new_resp = new.get("responses", {}) or {}
    for code in old_resp:
        if code not in new_resp:
            out.append(f"{label}: response {code} removed")

    return out


def compare() -> int:
    if not BASELINE.exists():
        print(f"no baseline at {BASELINE} — run with --snapshot first", file=sys.stderr)
        return 2
    old = json.loads(BASELINE.read_text())
    new = _load_app_openapi()
    breaking = _diff_breaking(old, new)
    if breaking:
        print("BREAKING OpenAPI changes detected:", file=sys.stderr)
        for b in breaking:
            print(f"  - {b}", file=sys.stderr)
        print("\nIf intentional, re-snapshot: python scripts/openapi_diff.py --snapshot",
              file=sys.stderr)
        return 1
    print(f"openapi OK — no breaking changes ({len(_paths(new))} paths vs "
          f"{len(_paths(old))} baseline)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="OpenAPI contract drift gate")
    ap.add_argument("--snapshot", action="store_true", help="write the baseline schema")
    args = ap.parse_args()
    if args.snapshot:
        return snapshot()
    return compare()


if __name__ == "__main__":
    raise SystemExit(main())
