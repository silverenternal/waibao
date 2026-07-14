#!/usr/bin/env bash
# v10.0 T5019 — Regenerate the pip-tools dependency lock.
#
# Produces backend/requirements.lock — the fully-resolved, hash-pinned
# transitive closure of requirements.in.  CI installs from this file (when
# present) so every build is byte-for-byte reproducible and safety/bandit
# scan the exact versions that ship.
#
# Usage:
#   ./scripts/lock_requirements.sh          # regenerates requirements.lock
#   ./scripts/lock_requirements.sh --check   # CI: fail if lock is stale
#
# Requires Python 3.12 (matches the Dockerfile + CI).  Run in a clean venv.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$(cd "$HERE/.." && pwd)"
cd "$BACKEND"

CHECK=0
if [[ "${1:-}" == "--check" ]]; then
  CHECK=1
fi

python -m pip install --quiet --upgrade pip-tools

if [[ "$CHECK" -eq 1 ]]; then
  # Recompile to a temp file and diff; fail if the committed lock is stale.
  pip-compile --quiet --generate-hashes --no-header --no-annotate \
    --output-file requirements.lock.tmp requirements.in
  if ! diff -q requirements.lock requirements.lock.tmp >/dev/null 2>&1; then
    if [[ ! -f requirements.lock ]]; then
      echo "❌ requirements.lock is missing. Run ./scripts/lock_requirements.sh to generate it."
    else
      echo "❌ requirements.lock is stale. Run ./scripts/lock_requirements.sh and commit the result."
    fi
    rm -f requirements.lock.tmp
    exit 1
  fi
  rm -f requirements.lock.tmp
  echo "✅ requirements.lock is up to date."
  exit 0
fi

pip-compile --generate-hashes --output-file requirements.lock requirements.in
echo "✅ Wrote $BACKEND/requirements.lock"
echo "   Review the diff and commit it."
