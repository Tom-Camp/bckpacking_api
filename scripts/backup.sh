#!/usr/bin/env bash
# PostgreSQL backup script — dumps from a native PostgreSQL instance and uploads to Linode Object Storage.
# Usage: ./backup.sh [/path/to/backup.env]
set -euo pipefail

ENV_FILE="${1:-$(dirname "$0")/backup.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: env file not found: $ENV_FILE" >&2
  echo "Copy scripts/backup.env.example to scripts/backup.env and fill in your values." >&2
  exit 1
fi

# shellcheck source=/dev/null
source "$ENV_FILE"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
FILENAME="${POSTGRES_DB}_${TIMESTAMP}.sql.gz"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/postgres}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
ENDPOINT="https://${LINODE_REGION}.linodeobjects.com"

mkdir -p "$BACKUP_DIR"

echo "[$(date -Iseconds)] Starting backup of '${POSTGRES_DB}' from ${POSTGRES_HOST}:${POSTGRES_PORT}"

# Dump and compress in one pass
PGPASSWORD="$POSTGRES_PASS" pg_dump \
  -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" \
  -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  | gzip > "${BACKUP_DIR}/${FILENAME}"

BACKUP_SIZE=$(du -sh "${BACKUP_DIR}/${FILENAME}" | cut -f1)
echo "[$(date -Iseconds)] Dump complete: ${FILENAME} (${BACKUP_SIZE})"

# Upload to Linode Object Storage
AWS_ACCESS_KEY_ID="$LINODE_ACCESS_KEY" \
AWS_SECRET_ACCESS_KEY="$LINODE_SECRET_KEY" \
  aws s3 cp \
    "${BACKUP_DIR}/${FILENAME}" \
    "s3://${LINODE_BUCKET}/${FILENAME}" \
    --endpoint-url "$ENDPOINT" \
    --region "$LINODE_REGION"

echo "[$(date -Iseconds)] Uploaded to s3://${LINODE_BUCKET}/${FILENAME}"

# Remove local backups older than retention period
find "$BACKUP_DIR" -name "${POSTGRES_DB}_*.sql.gz" -mtime "+${RETENTION_DAYS}" -delete
echo "[$(date -Iseconds)] Pruned local backups older than ${RETENTION_DAYS} days"

echo "[$(date -Iseconds)] Backup complete."
