#!/usr/bin/env python3
"""Build __init__.py for each services/<domain>/ sub-package by inspecting
public symbols in the .py files.

Rules:
- Re-export top-level `class`, `def`, `async def`, UPPERCASE constants.
- Skip names starting with `_` (private).
- Include module-level assignments to UPPERCASE constants.
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "services"
DOMAINS = ["jobseeker", "employer", "matching", "billing", "observability",
           "integrations", "platform"]


def extract_public_symbols(path: Path) -> list[str]:
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    symbols: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not node.name.startswith("_"):
                symbols.append(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id.isupper() and not t.id.startswith("_"):
                    symbols.append(t.id)
    return symbols


def build_init(domain_dir: Path) -> None:
    parts: list[str] = [f'"""v5.0 services/{domain_dir.name}/ public API."""\n']
    parts.append("from __future__ import annotations\n\n")
    for py in sorted(domain_dir.glob("*.py")):
        if py.name == "__init__.py":
            continue
        syms = extract_public_symbols(py)
        if not syms:
            continue
        mod = py.stem
        joined = ", ".join(syms)
        parts.append(f"from .{mod} import {joined}  # noqa: F401,F403\n")
    parts.append("\n__all__: list[str] = [\n")
    for py in sorted(domain_dir.glob("*.py")):
        if py.name == "__init__.py":
            continue
        syms = extract_public_symbols(py)
        for s in syms:
            parts.append(f'    "{s}",\n')
    parts.append("]\n")
    (domain_dir / "__init__.py").write_text("".join(parts), encoding="utf-8")
    print(f"  built {domain_dir}/__init__.py with "
          f"{sum(1 for _ in domain_dir.glob('*.py') if _.name != '__init__.py')} modules")


def main() -> None:
    for d in DOMAINS:
        p = ROOT / d
        if not p.is_dir():
            print(f"skip {p} (not a directory)")
            continue
        build_init(p)
    print("done")


if __name__ == "__main__":
    main()