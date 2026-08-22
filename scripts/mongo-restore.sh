#!/usr/bin/env bash
# mongo-restore.sh — MongoDB restore that fails loudly on any error.
#
# Reads one tar.gz archive produced by scripts/mongo-backup.sh and restores
# it into a target MongoDB database. Designed to be invoked by an operator
# via a one-shot Job (see the README restore runbook for the kubectl invocation
# and `k8s/mongodb/restore-job.yaml` for the manifest that wraps it).
#
# Meets the acceptance criteria of issue #105:
#   1. A restore that cannot read its archive or write to MongoDB exits non-zero.
#   2. The failure names the archive AND the reason.
#   3. A successful restore exits 0 and is distinguishable in the logs.
#   4. Refuses to overwrite an existing non-empty target database unless
#      explicitly told to (FORCE=1). Restoring is the one operation here
#      that destroys data, so the safe path is the default and the
#      destructive path is opt-in and obvious.
#
# All config is environment-driven so the same script works across the
# dev / test / prod overlays and can be exercised by tests with shimmed
# binaries (see scripts/mongo-restore_test.sh).

set -euo pipefail

# ---- Configuration (env-overridable) ----
MONGO_URI="${MONGO_URI:-mongodb://mongodb:27017}"
ARCHIVE="${ARCHIVE:-}"
TARGET_DB="${TARGET_DB:-}"
# SOURCE_DB is the database name INSIDE the archive (mongodump writes a
# `dump/<SOURCE_DB>/` directory). Defaults to TARGET_DB so a same-named
# source/target is the easy case; override when the archive was taken
# from a differently-named DB (e.g. restoring dev's archive into a
# scratch DB).
SOURCE_DB="${SOURCE_DB:-${TARGET_DB}}"
# FORCE=1 permits overwriting an existing non-empty target DB. Without it,
# the script exits non-zero if the target already has any collections.
FORCE="${FORCE:-0}"

# ---- Redact the password segment of MONGO_URI for logging ----
# As of issue #104, MONGO_URI is sourced from the `mongodb-credentials`
# Secret and now carries credentials. Without this redaction the
# RESTORE STARTING log line below would write the password verbatim to
# stderr on every run, where it is captured by `kubectl logs` and shipped
# to any log aggregator scraping kubelet logs (Loki / Elasticsearch /
# journald). The actual MONGO_URI is unchanged — only the log-time string
# is masked. The no-auth URI default (`mongodb://mongodb:27017`) has no
# match and passes through unchanged.
REDACTED_URI="$(printf '%s' "${MONGO_URI}" | sed -E 's|(://[^:]+:)[^@]+(@)|\1***\2|')"

# ---- Logging helpers (stderr so kubectl logs picks them up) ----
log()  { printf '[%s] %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*" >&2; }
fail() {
  log "RESTORE FAILED archive=${ARCHIVE} reason=${1}"
  exit 1
}

# ---- Argument validation ----
if [ -z "${ARCHIVE}" ]; then
  fail "ARCHIVE env var is required (path to the tar.gz to restore)"
fi
if [ -z "${TARGET_DB}" ]; then
  fail "TARGET_DB env var is required (database name to restore into)"
fi

# ---- Pre-flight: archive must exist, be readable, be non-empty, and parse
# as a valid gzip-compressed tar. ----
log "RESTORE STARTING source=${REDACTED_URI} archive=${ARCHIVE} target_db=${TARGET_DB} source_db=${SOURCE_DB} force=${FORCE}"

if [ ! -f "${ARCHIVE}" ]; then
  fail "archive does not exist"
fi
if [ ! -r "${ARCHIVE}" ]; then
  fail "archive is not readable"
fi
if [ ! -s "${ARCHIVE}" ]; then
  fail "archive is empty"
fi
if ! tar -tzf "${ARCHIVE}" >/dev/null 2>&1; then
  fail "archive is corrupt or unreadable"
fi

# ---- Pre-flight: refuse to overwrite a non-empty target unless FORCE=1 ----
# mongosh prints the result of the final expression to stdout; we capture
# stdout and parse. The check is intentionally tolerant of a MISSING DB
# (returns 0 collections, restore proceeds) — only an EXISTING non-empty
# target triggers the refusal. If the eval fails (empty output), we treat
# that as a connectivity error rather than a successful "0 collections"
# so a misconfigured MONGO_URI surfaces as a named failure instead of a
# silent "looks empty, restore proceeds into nothing".
coll_count="$(mongosh --uri="${MONGO_URI}" --quiet --eval \
  "print(db.getSiblingDB('${TARGET_DB}').getCollectionNames().length);" 2>/dev/null || true)"
if [ -z "${coll_count}" ]; then
  fail "could not query target database '${TARGET_DB}' via mongosh (check MONGO_URI / connectivity)"
fi
# coll_count is a non-negative integer; the -gt guard handles the empty /
# non-numeric case (already filtered above) so this is safe.
if [ "${coll_count}" -gt 0 ] 2>/dev/null; then
  if [ "${FORCE}" != "1" ]; then
    fail "target database '${TARGET_DB}' already contains ${coll_count} collection(s); set FORCE=1 to overwrite"
  fi
  log "WARN: overwriting target database '${TARGET_DB}' with ${coll_count} existing collection(s) (FORCE=1)"
fi

# ---- ERR/INT/TERM trap registered BEFORE the first potentially-failing
# call (mktemp) so every error path — including a /tmp EROFS, a tar
# extraction failure, anything between `set -e` and mongorestore —
# funnels through fail() and emits the archive-named error line required
# by issue #105's acceptance criterion #2. Same pattern as
# scripts/mongo-backup.sh. ----
tmp_dir=""
on_error() {
  if [ -n "${tmp_dir}" ] && [ -d "${tmp_dir}" ]; then
    rm -rf "${tmp_dir}"
  fi
  fail "aborted by signal or error"
}
trap on_error ERR INT TERM

tmp_dir="$(mktemp -d -t mongo-restore.XXXXXX)"
# Re-arm the trap so it carries the actual tmp_dir path now that we know it.
trap on_error ERR INT TERM

# ---- Extract archive. mongodump's default --out writes to <out>/dump/<db>/,
# so a backup archive contains a top-level `dump/` directory; that is what
# we extract and what mongorestore reads from. ----
log "extracting archive to ${tmp_dir}"
if ! tar -xzf "${ARCHIVE}" -C "${tmp_dir}"; then
  fail "tar extraction failed"
fi

# ---- Locate the dump directory inside the extracted archive. Tolerates
# the two layouts produced by real mongodump:
#   1. <tmp>/dump/<SOURCE_DB>/...  (mongodump's default with --out=path)
#   2. <tmp>/<SOURCE_DB>/...       (legacy / hand-rolled archives)
# mongorestore's directory mode reads the database name from the top-level
# directory under the dump root, so we point it at whichever path exists. ----
src_dir=""
for candidate in "${tmp_dir}/dump/${SOURCE_DB}" "${tmp_dir}/${SOURCE_DB}"; do
  if [ -d "${candidate}" ]; then
    src_dir="${candidate}"
    break
  fi
done
if [ -z "${src_dir}" ]; then
  fail "extracted archive does not contain expected directory dump/${SOURCE_DB}/ (or ${SOURCE_DB}/)"
fi

# ---- mongorestore. --drop is only used when FORCE=1 — without FORCE the
# pre-flight refused, and an empty target has nothing to drop anyway.
# Using an array assignment + "${arr[@]}" expansion so an empty array
# passes no extra args (avoids a trailing empty arg that some versions of
# mongorestore reject). ----
mongorestore_args=(--uri="${MONGO_URI}" --db="${TARGET_DB}")
if [ "${FORCE}" = "1" ]; then
  mongorestore_args+=(--drop)
fi
mongorestore_args+=("${src_dir}")

log "running mongorestore (source_dir=${src_dir} drop=${FORCE})"
if ! mongorestore "${mongorestore_args[@]}"; then
  fail "mongorestore returned non-zero exit code"
fi

# ---- Post-flight: the target DB must now have at least one collection. An
# empty restore against a real-looking archive is suspicious and would
# otherwise masquerade as success (e.g. archive was for a different DB). ----
post_count="$(mongosh --uri="${MONGO_URI}" --quiet --eval \
  "print(db.getSiblingDB('${TARGET_DB}').getCollectionNames().length);" 2>/dev/null || echo "0")"
if [ "${post_count}" -le 0 ] 2>/dev/null; then
  fail "post-restore: target database '${TARGET_DB}' has 0 collections (restore silently produced nothing)"
fi

rm -rf "${tmp_dir}"
trap - ERR INT TERM
log "RESTORE SUCCEEDED archive=${ARCHIVE} target_db=${TARGET_DB} collections=${post_count}"
exit 0
