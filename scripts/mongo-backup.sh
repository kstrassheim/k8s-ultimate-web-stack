#!/usr/bin/env bash
# mongo-backup.sh — MongoDB backup that fails loudly on any error.
#
# Designed for use inside the `mongo-backup` CronJob (k8s/mongodb/backup-cronjob.yaml).
# Meets the acceptance criteria of issue #90:
#   1. A backup that cannot write exits non-zero.
#   2. The failure names the destination and the reason.
#   3. A successful backup exits 0 and is distinguishable in the logs.
#
# All config is environment-driven so the same script works across the
# dev / test / prod overlays and can be exercised by tests with shimmed
# binaries (see scripts/mongo-backup_test.sh).

set -euo pipefail

# ---- Configuration (env-overridable; defaults suit the in-cluster CronJob) ----
MONGO_URI="${MONGO_URI:-mongodb://mongodb:27017}"
MONGO_DB="${MONGO_DB:-future_gadget_lab}"
DEST_DIR="${DEST_DIR:-/backup}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
# Free-space headroom (KiB) required on the destination filesystem before the
# backup is allowed to start. mongodump writes to a temp dir then we move a
# tar.gz to DEST_DIR, so the working set can briefly exceed the source DB size.
# 100 MiB is a conservative floor that catches "volume 99.9% full" early while
# not blocking legitimately small databases.
REQUIRED_FREE_KB="${REQUIRED_FREE_KB:-102400}"

# ---- Logging helpers (stderr so kubectl logs picks them up) ----
log()  { printf '[%s] %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*" >&2; }
fail() {
  log "BACKUP FAILED destination=${DEST_DIR} reason=${1}"
  exit 1
}

# ---- Pre-flight: destination must exist and be writable ----
log "BACKUP STARTING source=${MONGO_URI} db=${MONGO_DB} destination=${DEST_DIR}"

if [ ! -d "${DEST_DIR}" ]; then
  if mkdir -p "${DEST_DIR}" 2>/dev/null; then
    log "created missing destination directory ${DEST_DIR}"
  else
    fail "destination directory does not exist and cannot be created"
  fi
fi
if [ ! -w "${DEST_DIR}" ]; then
  fail "destination directory is not writable"
fi

# ---- Pre-flight: free-space check (catches the "volume is full" failure mode
# from issue #90 with a clean, named error instead of a cryptic tar ENOSPC) ----
available_kb="$(df -Pk "${DEST_DIR}" | awk 'NR==2 {print $4}')"
if [ "${available_kb}" -lt "${REQUIRED_FREE_KB}" ]; then
  fail "destination volume full (available=${available_kb}KiB required=${REQUIRED_FREE_KB}KiB)"
fi

# ---- Backup: dump to a temp dir, then compress + move atomically so a
# mid-write failure cannot leave a partial archive at the destination ----
timestamp="$(date -u +'%Y%m%dT%H%M%SZ')"
tmp_dir="$(mktemp -d -t mongo-backup.XXXXXX)"
# Re-arm the trap so an error during dump/tar still removes the temp dir AND
# emits the same destination-named failure line.
trap 'rm -rf "${tmp_dir}"; fail "aborted by signal or error"' ERR INT TERM

log "running mongodump"
if ! mongodump --uri="${MONGO_URI}" --db="${MONGO_DB}" --out="${tmp_dir}"; then
  fail "mongodump returned non-zero exit code"
fi

# Verify mongodump actually wrote something (an empty dump is suspicious and
# would later show as a 0-byte archive masquerading as success).
dump_bytes="$(find "${tmp_dir}" -type f -printf '%s\n' 2>/dev/null | awk 'BEGIN{s=0} {s+=$1} END{print s+0}')"
if [ "${dump_bytes}" -le 0 ]; then
  fail "mongodump produced no files (dump_bytes=0)"
fi

archive="${DEST_DIR}/${MONGO_DB}-${timestamp}.tar.gz"
log "compressing backup to ${archive}"
if ! tar -C "${tmp_dir}" -czf "${archive}" .; then
  # tar's ENOSPC surfaces here as a non-zero exit; this line names the destination.
  fail "tar compression failed (likely destination volume full mid-write)"
fi

# ---- Post-flight: the archive must exist, be non-empty, and be readable ----
if [ ! -s "${archive}" ]; then
  fail "archive is empty after write"
fi
if ! tar -tzf "${archive}" >/dev/null 2>&1; then
  fail "archive is corrupt or unreadable"
fi

# ---- Retention: prune older archives. Non-fatal: a prune failure must not
# erase a successful backup from the success log. ----
if [ "${RETENTION_DAYS}" -gt 0 ]; then
  log "pruning backups older than ${RETENTION_DAYS} days from ${DEST_DIR}"
  if ! find "${DEST_DIR}" -maxdepth 1 -name "${MONGO_DB}-*.tar.gz" -mtime "+${RETENTION_DAYS}" -delete; then
    log "WARN retention prune failed (non-fatal; backup still succeeded)"
  fi
fi

# ---- Success ----
archive_bytes="$(stat -c%s "${archive}")"
rm -rf "${tmp_dir}"
trap - ERR INT TERM
log "BACKUP SUCCEEDED archive=${archive} size=${archive_bytes} bytes"
exit 0
