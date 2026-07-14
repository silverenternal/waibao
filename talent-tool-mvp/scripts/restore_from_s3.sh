#!/usr/bin/env bash
# ============================================================================
# restore_from_s3.sh — T5013
# Restores a database dump produced by backup_to_s3.sh into a target Postgres.
#
# Usage
# -----
#   restore_from_s3.sh s3://bucket/path/to/file.dump
#   restore_from_s3.sh latest            # restore the most recent dump
#
# Safety
# ------
#   * Refuses to restore into a database that already contains relations unless
#     --confirm-destructive is passed (avoids wiping prod by accident).
#   * Drops + recreates the target DB's objects via pg_restore --clean
#     --if-exists (so it is idempotent on an empty or half-restored DB).
#   * Streams from S3 (no local disk).
#
# Required env
# ------------
#   DATABASE_URL        postgres://...   (the restore target)
#   AWS_REGION
#   S3_BUCKET           (only needed when arg = "latest")
#   S3_PREFIX           default: backups (only needed for "latest")
# ============================================================================

set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL (restore target) is required}"
: "${AWS_REGION:?AWS_REGION is required}"

CONFIRM_DESTRUCTIVE=0
SRC=""

while [ $# -gt 0 ]; do
  case "$1" in
    --confirm-destructive) CONFIRM_DESTRUCTIVE=1; shift ;;
    latest|*.dump|s3://*) SRC="$1"; shift ;;
    -h|--help)
      cat >&2 <<'EOF'
restore_from_s3.sh [--confirm-destructive] (s3://bucket/key.dump | latest)
EOF
      exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 64 ;;
  esac
done

[ -n "$SRC" ] || { echo "ERROR: supply an s3:// URI or 'latest'" >&2; exit 64; }

TS="$(date -u +%Y%m%dT%H%M%SZ)"
log() { printf '[restore %s] %s\n' "$TS" "$*" >&2; }

command -v pg_restore >/dev/null 2>&1 || { log "ERROR: pg_restore not found"; exit 127; }
command -v aws        >/dev/null 2>&1 || { log "ERROR: aws CLI not found"; exit 127; }

# ---------------------------------------------------------------------------
# 1. Resolve the source object
# ---------------------------------------------------------------------------
if [ "$SRC" = "latest" ]; then
  : "${S3_BUCKET:?S3_BUCKET required for 'latest'}"
  S3_PREFIX="${S3_PREFIX:-backups}"
  log "resolving latest dump under s3://${S3_BUCKET}/${S3_PREFIX}/"
  SRC="$(aws s3api list-objects-v2 \
           --bucket "$S3_BUCKET" \
           --prefix "${S3_PREFIX}/" \
           --region "$AWS_REGION" \
           --query 'reverse(sort_by(Contents,&LastModified))[0].Key' \
           --output text)"
  if [ -z "$SRC" ] || [ "$SRC" = "None" ]; then
    log "ERROR: no backups found in s3://${S3_BUCKET}/${S3_PREFIX}/"
    exit 5
  fi
  SRC="s3://${S3_BUCKET}/${SRC}"
fi
log "source: ${SRC}"

# ---------------------------------------------------------------------------
# 2. Destructive-restore guard
# ---------------------------------------------------------------------------
# Count existing user tables in the target DB. >0 means there is data we would
# clobber with --clean.
TABLE_COUNT="$(psql "$DATABASE_URL" -t -A -c \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';" \
  2>/dev/null || echo 0)"
if [ "${TABLE_COUNT:-0}" -gt 0 ] && [ "$CONFIRM_DESTRUCTIVE" -ne 1 ]; then
  log "ERROR: target DB already has ${TABLE_COUNT} table(s) in public."
  log "       Pass --confirm-destructive to allow dropping them."
  exit 6
fi

# ---------------------------------------------------------------------------
# 3. Restore (stream from S3 → pg_restore)
# ---------------------------------------------------------------------------
# --clean --if-exists : drop then recreate (idempotent)
# --no-owner --no-privileges : portable across accounts
# --exit-on-error      : stop on the first real error (do not mask failures)
log "starting pg_restore ..."
if ! aws s3 cp "$SRC" - --region "$AWS_REGION" \
    | pg_restore \
        --dbname "$DATABASE_URL" \
        --clean --if-exists \
        --no-owner --no-privileges \
        --exit-on-error \
        --verbose; then
  log "ERROR: restore failed"
  exit 7
fi

log "OK: restored ${SRC} → ${DATABASE_URL}"
