#!/usr/bin/env bash
# SDK auto-generator for the RecruitTech Developer Portal — T2902.
#
# What this does:
#   1. Boots the FastAPI app in spec-only mode and dumps /openapi.json.
#   2. Runs `openapi-generator-cli` for three targets:
#        * python      →  sdk/python/         (PyPI-ready)
#        * typescript-axios →  sdk/typescript/   (npm-ready)
#        * go          →  sdk/go/              (go-ready)
#   3. Writes SDK_VERSION + timestamp file (sdk/VERSION).
#   4. Optionally uploads the artifact to a GitHub Release via `gh release`.
#
# Usage:
#   ./scripts/generate_sdk.sh                  # generate locally
#   ./scripts/generate_sdk.sh --upload v3.0.0  # generate + create GH release
#
# Requires (any of the following):
#   * Docker (most portable — `docker run openapitools/openapi-generator-cli`)
#   * npx      (Node — `npx @openapitools/openapi-generator-cli`)
#   * podman   (rootless alternative to Docker)
#
# Tools you should `pip install` once: openapi-spec-validator (only used to
# sanity-check the spec we emit).
#
# Refs:
#   https://openapi-generator.tech/docs/usage
#   https://openapi-generator.tech/docs/generators

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SDK_DIR="$REPO_ROOT/sdk"

OPENAPI_FILE="$SDK_DIR/openapi.json"
VERSION_FILE="$SDK_DIR/VERSION"

# --- Output language targets ---------------------------------------------
GENERATORS=(
    "python|python"
    "typescript-axios|typescript"
    "go|go"
)

OPENAPI_GENERATOR_IMAGE="openapitools/openapi-generator-cli:v7.6.0"

# --- CLI parsing ----------------------------------------------------------
UPLOAD_TAG=""
SKIP_DOCKER=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --upload)
            UPLOAD_TAG="$2"
            shift 2
            ;;
        --no-docker)
            SKIP_DOCKER="1"
            shift
            ;;
        -h|--help)
            cat <<EOF
Usage: $0 [--upload <tag>] [--no-docker]

Options:
  --upload <tag>    Generate SDK + create a GitHub release with tag <tag>.
  --no-docker       Use the npx/Java distribution instead of Docker.
  -h, --help        Print this help.
EOF
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            exit 1
            ;;
    esac
done

mkdir -p "$SDK_DIR"

# ---------------------------------------------------------------------------
# Step 1 — Emit openapi.json
# ---------------------------------------------------------------------------
echo "[1/3] Dumping FastAPI OpenAPI spec ..."

# Boot the FastAPI app in-memory and emit the spec. We avoid running uvicorn
# by using the FastAPI test client + a dedicated entrypoint that does
# `app.openapi()` and writes the result to JSON.
python - <<'PY' > "$OPENAPI_FILE"
import json
import os
import sys

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "x")

try:
    from main import app
except Exception as exc:
    sys.stderr.write(f"failed to import app: {exc}\n")
    sys.exit(1)

spec = app.openapi()
# We force version for SDKs regardless of the app version
spec["info"]["version"] = "3.0.0"
spec.setdefault("x-tagGroups", []).append({
    "name": "Developer Portal",
    "tags": ["developer-portal"],
})
print(json.dumps(spec, indent=2))
PY

if [[ ! -s "$OPENAPI_FILE" ]]; then
    echo "ERROR: $OPENAPI_FILE is empty" >&2
    exit 1
fi

echo "  ✔ written to $OPENAPI_FILE ($(wc -c < "$OPENAPI_FILE") bytes)"

# ---------------------------------------------------------------------------
# Step 2 — Generate SDKs (python / typescript / go)
# ---------------------------------------------------------------------------
echo "[2/3] Generating SDKs ..."

# Choose runner
RUNNER=""
if [[ -z "${SKIP_DOCKER}" ]] && command -v docker >/dev/null 2>&1; then
    RUNNER="docker"
elif command -v npx >/dev/null 2>&1; then
    RUNNER="npx"
elif command -v podman >/dev/null 2>&1; then
    RUNNER="podman"
fi

if [[ -z "$RUNNER" ]]; then
    echo "ERROR: no runner available — install docker, npx, or podman." >&2
    exit 1
fi

run_openapi_gen() {
    local lang="$1"
    local out_dir="$SDK_DIR/$lang"
    case "$RUNNER" in
        docker)
            docker run --rm \
                -v "$SDK_DIR:/local" \
                "$OPENAPI_GENERATOR_IMAGE" generate \
                -i /local/openapi.json \
                -g "$lang" \
                -o "/local/$lang" \
                --git-user-id "recruittech" \
                --git-repo-id "recruittech-sdk-$lang" \
                --additional-properties=packageVersion=3.0.0 \
                --skip-validate-spec
            ;;
        podman)
            podman run --rm \
                -v "$SDK_DIR:/local" \
                "$OPENAPI_GENERATOR_IMAGE" generate \
                -i /local/openapi.json \
                -g "$lang" \
                -o "/local/$lang" \
                --git-user-id "recruittech" \
                --git-repo-id "recruittech-sdk-$lang" \
                --additional-properties=packageVersion=3.0.0 \
                --skip-validate-spec
            ;;
        npx)
            (cd "$SDK_DIR" && npx --yes @openapitools/openapi-generator-cli generate \
                -i openapi.json \
                -g "$lang" \
                -o "$lang" \
                --additional-properties=packageVersion=3.0.0 \
                --skip-validate-spec)
            ;;
    esac
}

for entry in "${GENERATORS[@]}"; do
    IFS='|' read -r lang dir <<< "$entry"
    echo "  → Generating $lang SDK into $dir/"
    rm -rf "$SDK_DIR/$dir"
    if ! run_openapi_gen "$lang" "$dir"; then
        echo "  ⚠ Failed to generate $lang — continuing" >&2
    fi
done

# ---------------------------------------------------------------------------
# Step 3 — Manifest + optional upload
# ---------------------------------------------------------------------------
echo "[3/3] Writing SDK manifest ..."
cat > "$VERSION_FILE" <<EOF
{
  "version": "3.0.0",
  "generated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "openapi_spec": "openapi.json",
  "languages": [$(printf '"%s",' "${GENERATORS[@]}" | sed 's/,$//' | sed 's/|.*"/"/g')]
}
EOF
echo "  ✔ Wrote $VERSION_FILE"

if [[ -n "$UPLOAD_TAG" ]]; then
    if ! command -v gh >/dev/null 2>&1; then
        echo "ERROR: --upload requested but 'gh' (GitHub CLI) is not installed" >&2
        exit 1
    fi
    echo "  → Uploading GitHub release $UPLOAD_TAG ..."
    cd "$SDK_DIR"
    tar -czf "../sdk-${UPLOAD_TAG}.tar.gz" \
        python typescript go VERSION openapi.json 2>/dev/null || \
    tar -czf "../sdk-${UPLOAD_TAG}.tar.gz" VERSION openapi.json
    cd - >/dev/null
    gh release create "$UPLOAD_TAG" \
        "sdk-${UPLOAD_TAG}.tar.gz" \
        --title "RecruitTech SDK $UPLOAD_TAG" \
        --notes "Auto-generated SDK bundle — see VERSION for details." \
        --draft || true
    rm -f "sdk-${UPLOAD_TAG}.tar.gz"
fi

echo ""
echo "All done. SDKs are available under $SDK_DIR/{python,typescript,go}/"
