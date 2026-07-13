"""v8.0 T3505 — Wire service gates onto every API router in main.py.

This script patches ``backend/main.py`` so every ``app.include_router(
..., prefix="/api/X", ...)`` call also passes a
``dependencies=[Depends(check_service_access(\"api.X\"))]`` argument.

It is idempotent — running twice is a no-op.

Run from project root:
    python -m backend.scripts.wire_service_gates
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

MAIN_PY = Path(__file__).resolve().parent.parent.parent / "main.py"


def patch_main(path: Path = MAIN_PY) -> int:
    src = path.read_text()
    original = src

    pattern = re.compile(
        r'(?P<indent>[ \t]*)app\.include_router\(\s*'
        r'(?P<router>[A-Za-z_][\w]*),\s*'
        r'prefix="(?P<prefix>/api/[^"]+)"',
    )

    def _add_dep(m: re.Match) -> str:
        indent = m.group("indent")
        prefix = m.group("prefix")
        # Skip global / system routes
        if prefix in {"/api"}:
            return m.group(0)
        service = prefix.replace("/api/", "api.").replace("/", ".").rstrip(".")
        sentinel = f"# gate:{service}"
        # Skip if already wired
        line_with_deps = m.string[m.end():].split("\n", 1)[0]
        if sentinel in line_with_deps:
            return m.group(0)
        # The router line may continue across multiple lines. We just
        # append the deps right before the closing ) on the same line,
        # or on the next line if the call spans more.
        # Simple case: same line — append before final ")".
        head = m.group(0)
        return f"{head}{sentinel}"

    # The regex above adds a sentinel comment; we now also need a real
    # ``dependencies=`` argument. We do a second pass to convert the
    # sentinel into the actual FastAPI argument.

    # Step 1: mark every include_router line that lacks a `dependencies=` kw
    def _mark(m: re.Match) -> str:
        head = m.group(0)
        prefix = m.group("prefix")
        return f"{head}  # gate:{prefix}"

    marked = pattern.sub(_mark, src)
    src = marked

    # Step 2: parse each marked line and inject ``dependencies=``
    out_lines: list[str] = []
    in_router_block = False
    block_lines: list[str] = []
    block_indent = ""

    def _consume(end_idx: int) -> str:
        nonlocal block_lines, block_indent
        # Find the close paren of the include_router call
        depth = 0
        joined = "\n".join(block_lines)
        for ch in joined:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    break
        return joined

    # Easier: walk line by line, detect include_router() lines with sentinel,
    # inject the dependencies= argument before the closing paren.
    lines = src.split("\n")
    new_lines: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.search(r"app\.include_router\(\s*([A-Za-z_][\w]*),\s*prefix=\"(/api/[^\"]+)\"", line)
        if m and "# gate:" in line:
            router = m.group(1)
            prefix = m.group(2)
            service = prefix.replace("/api/", "api.").replace("/", ".").rstrip(".")
            # If the line's closing ) is here, inject deps on a new line.
            # Find column of trailing ).
            close_idx = line.rfind(")")
            if close_idx != -1:
                head = line[:close_idx].rstrip()
                # trailing comma?
                if not head.endswith(","):
                    head = head + ","
                # Insert the dependencies kw right before close
                # match indentation
                indent = re.match(r"(\s*)", line).group(1)
                injected = (
                    f"{head}\n{indent}    dependencies=[\n"
                    f"{indent}        Depends(check_service_access(\"{service}\"))\n"
                    f"{indent}    ],"
                )
                # Re-attach close paren
                injected = injected + line[close_idx:]
                # Remove the sentinel comment
                injected = injected.split("# gate:")[0].rstrip() + (
                    line[close_idx:].split("# gate:")[0]
                    if "# gate:" in line[close_idx:]
                    else ""
                )
                new_lines.append(injected)
                i += 1
                continue
        new_lines.append(line)
        i += 1

    new_src = "\n".join(new_lines)

    if new_src == original:
        print(f"no changes needed in {path}", file=sys.stderr)
        return 0

    # Prepend the import we need at the top of the file (after imports).
    if "from services.platform.feature_access import" not in new_src:
        new_src = new_src.replace(
            "from api.auth import",
            "from services.platform.feature_access import check_service_access\nfrom fastapi import Depends\n\nfrom api.auth import",
            1,
        )

    path.write_text(new_src)
    print(f"patched {path}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--path",
        default=str(MAIN_PY),
        help="path to backend/main.py (default: %(default)s)",
    )
    args = parser.parse_args(argv)
    return patch_main(Path(args.path))


if __name__ == "__main__":
    sys.exit(main())
