#!/usr/bin/env bash
# ============================================================================
# backup_to_s3.sh — T5013
# Dumps the Supabase / Postgres database to a compressed, timestamped file and
# uploads it to S3 (versioned, lifecycle-managed by infra/backup/s3-lifecycle.yml).
#
# Design
# ------
#   * Uses ``pg_dump --format=custom`` (parallel-restore friendly, compressed).
#   * Streams through ``aws s3 cp -`` so we never land a large file on the
#     local disk (works on tiny CI runners).
#   * Object key includes UTC timestamp + hostname so backups never collide
#     and are trivially sortable.
#   * Exits non-zero on any failure so CI / cron alerts fire.
#
# Required env
# ------------
#   DATABASE_URL       postgres://...   (or PG* vars)
#   AWS_REGION         e.g. ap-southeast-1
#   S3_BUCKET          e.g. waibao-db-backups
# Optional env
#   S3_PREFIX          default: backups/
#   RETENTION_DAYS     default: 30  ( informational; real expiry via lifecycle )
#   PG_DUMP_EXTRA      extra pg_dump flags
# ============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# 0. Configuration & validation
# ---------------------------------------------------------------------------
: "${DATABASE_URL:?DATABASE_URL is required (postgres://user:pass@host:5432/db)}"
: "${AWS_REGION:?AWS_REGION is required}"
: "${S3_BUCKET:?S3_BUCKET is required}"

S3_PREFIX="${S3_PREFIX:-backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
PG_DUMP_EXTRA="${PG_DUMP_EXTRA:-}"

TS="$(date -u +%Y%m%dT%H%M%SZ)"
HOST="$(hostname -s 2>/dev/null || echo host)"
DB_NAME="$(printf '%s' "$DATABASE_URL" | sed -E 's#.*/([^/?]+)(\?.*)?$#\1#')"
OBJECT_KEY="${S3_PREFIX}/${DB_NAME}/${DB_NAME}-${HOST}-${TS}.dump"

log() { printf '[backup %s] %s\n' "$TS" "$*" >&2; }

log "database: ${DB_NAME}"
log "target:   s3://${S3_BUCKET}/${OBJECT_KEY}"

# ---------------------------------------------------------------------------
# 1. Preflight checks — fail fast with a clear message
# ---------------------------------------------------------------------------
command -v pg_dump >/dev/null 2>&1 || { log "ERROR: pg_dump not found"; exit 127; }
command -v aws    >/dev/null 2>&1 || { log "ERROR: aws CLI not found"; exit 127; }

# Verify S3 credentials are configured (does NOT require the bucket to exist
# yet — we only probe the caller identity).
if ! aws sts get-caller-identity --region "$AWS_REGION" >/dev/null 2>&1; then
  log "ERROR: AWS credentials invalid or missing"
  exit 2
fi

# ---------------------------------------------------------------------------
# 2. Dump (custom format, compressed) streamed straight to S3
# ---------------------------------------------------------------------------
# --no-owner --no-privileges: restore on any account / environment.
# ${PG_DUMP_EXTRA} lets callers inject e.g. --schema=public on demand.
log "starting pg_dump ..."
if ! pg_dump \
      --format=custom \
      --no-owner \
      --no-privileges \
      --verbose \
      ${PG_DUMP_EXTRA} \
      "$DATABASE_URL" \
    | aws s3 cp - "s3://${S3_BUCKET}/${OBJECT_KEY}" \
        --expected-size 5368709120 \
        --region "$AWS_REGION"; then
  log "ERROR: pg_dump or s3 upload failed"
  exit 3
fi

# ---------------------------------------------------------------------------
# 3. Verify the upload landed (HEAD the object, require non-zero size)
# ---------------------------------------------------------------------------
SIZE="$(aws s3api head-object \
          --bucket "$S3_BUCKET" \
          --key "$OBJECT_KEY" \
          --region "$AWS_REGION" \
          --query ContentLength \
          --output text 2>/dev/null || echo 0)"

if [ "${SIZE:-0}" -le 0 ]; then
  log "ERROR: uploaded object is empty or missing (${SIZE} bytes)"
  exit 4
fi

# Human-readable size for the log
HR_SIZE="$(awk -v b="$SIZE" 'BEGIN{
  split("B KB MB GB TB",u);
  i=1; while(b>=1024 && i<5){b/=1024; i++}
  printf "%.1f%s", b, u[i]
}')"
log "OK: uploaded ${HR_SIZE} (${SIZE} bytes) → s3://${S3_BUCKET}/${OBJECT_KEY}"

# ---------------------------------------------------------------------------
# 4. Emit the object URI on stdout so callers can capture it
# ---------------------------------------------------------------------------
echo "s3://${S3_BUCKET}/${OBJECT_KEY}"

# ---------------------------------------------------------------------------
# 5. Prune local-scope note (real expiry is enforced by the bucket lifecycle
#    policy — see infra/backup/s3-lifecycle.yml — so we only log the intent).
# ---------------------------------------------------------------------------
log "retention: ${RETENTION_DAYS}d (enforced by S3 lifecycle, not this script)"
