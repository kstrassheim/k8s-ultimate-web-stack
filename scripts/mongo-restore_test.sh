#!/usr/bin/env bash
# mongo-restore_test.sh — smoke tests for scripts/mongo-restore.sh.
#
# Runs the script with shimmed binaries in a temp workspace so each scenario
# exits cleanly with the expected code + log marker. Designed to be runnable
# in CI (no k8s / mongod required) and locally:
#
#   bash scripts/mongo-restore_test.sh
#
# Exit 0 on full success, non-zero on the first failed assertion. Uses bash
# only — no dependency on pytest/jest. Kept in scripts/ (next to the script
# under test) because the project doesn't otherwise have a bash test runner.
#
# Mirrors the approach of mongo-backup_test.sh — same sandbox layout,
# same pass/fail counters, same stderr-asserted log markers.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_UNDER_TEST="${SCRIPT_DIR}/mongo-restore.sh"
BACKUP_SCRIPT_UNDER_TEST="${SCRIPT_DIR}/mongo-backup.sh"

PASS=0
FAIL=0

pass() { PASS=$((PASS + 1)); printf '  \033[32m✓\033[0m %s\n' "$*"; }
fail() { FAIL=$((FAIL + 1)); printf '  \033[31m✗\033[0m %s\n' "$*" >&2; }

# Build a self-contained sandbox: temp dir + shim bin/ + shimmed mongosh,
# mongorestore, mongodump, df, tar.
#
# Why shim mongodump too? The round-trip scenario runs the actual
# scripts/mongo-backup.sh against a fake "source database" — the mongodump
# shim reads from a seed directory and lays out files in the same shape
# real mongodump would (out/dump/<db>/<file>), so the backup tar captures
# the right structure and the restore side can round-trip through it.
make_sandbox() {
  local sb
  sb="$(mktemp -d -t mongo-restore-test.XXXXXX)"
  mkdir -p "${sb}/bin" "${sb}/dest"

  # df shim: same shape as backup_test.sh's. Restore doesn't strictly need
  # it but the backup round-trip path uses df (via backup.sh) so we include
  # it for symmetry / to keep the round-trip test self-contained.
  cat >"${sb}/bin/df" <<'SHIM'
#!/usr/bin/env bash
free_kb="${MOCK_FREE_KB:-1048576}"
path="$*"
for arg in "$@"; do
  case "${arg}" in
    -*) ;;
    *)  path="${arg}" ;;
  esac
done
printf 'Filesystem 1024-blocks Used Available Capacity Mounted-on\n'
printf '/dev/shim 1048576 0 %s 0%% %s\n' "${free_kb}" "${path}"
SHIM
  chmod +x "${sb}/bin/df"

  # mongosh shim: parses --uri and --eval, answers the script's pre- and
  # post-flight `print(db.getSiblingDB('<DB>').getCollectionNames().length)`
  # query based on controllable env. State is per-sandbox via
  # MONGOSH_STATE_FILE so call counts don't leak between scenarios.
  #
  # The script calls mongosh exactly twice per invocation:
  #   * 1st call = pre-flight ("is the target DB empty enough to restore?")
  #   * 2nd call = post-flight ("did the restore actually produce anything?")
  # We answer them differently because the pre-flight and post-flight see
  # different DB states in a successful scenario (empty → non-empty).
  #
  #   MOCK_MONGO_CONNECT_FAIL=1          → simulate connection failure
  #                                        (exit non-zero, no stdout)
  #   MOCK_MONGO_COLLECTIONS_FIRST=<N>   → answer for the FIRST call only
  #                                        (i.e. the pre-flight). Falls
  #                                        back to MOCK_MONGO_COLLECTIONS.
  #   MOCK_MONGO_COLLECTIONS=<N>         → global answer (default 0). Used
  #                                        by the first call when FIRST
  #                                        is unset, and as the default
  #                                        for subsequent calls.
  #   MOCK_MONGO_COLLECTIONS_<DB>=<N>    → per-DB override for SUBSEQUENT
  #                                        calls (the post-flight), where
  #                                        the target DB name matters.
  cat >"${sb}/bin/mongosh" <<'SHIM'
#!/usr/bin/env bash
uri=""
ev=""
prev=""
for arg in "$@"; do
  case "${arg}" in
    --uri=*) uri="${arg#--uri=}" ;;
    --eval=*) ev="${arg#--eval=}" ;;
    --uri) prev="--uri" ;;
    --eval) prev="--eval" ;;
    *)
      case "${prev}" in
        --uri) uri="${arg}"; prev="" ;;
        --eval) ev="${arg}"; prev="" ;;
        *) prev="" ;;
      esac
      ;;
  esac
done
if [ "${MOCK_MONGO_CONNECT_FAIL:-0}" = "1" ]; then
  echo "mongosh shim: simulated connection failure to ${uri}" >&2
  exit 1
fi
db=""
if [[ "${ev}" =~ getSiblingDB\([\'\"]([^\'\"]+)[\'\"]\) ]]; then
  db="${BASH_REMATCH[1]}"
fi
state_file="${MONGOSH_STATE_FILE:-/tmp/mongosh-shim-state-$$}"
call_num="$(cat "${state_file}" 2>/dev/null || echo 0)"
echo $((call_num + 1)) > "${state_file}"
# First call (pre-flight): MOCK_MONGO_COLLECTIONS_FIRST if set, else
# MOCK_MONGO_COLLECTIONS. Per-DB overrides intentionally do NOT apply
# here — the pre-flight is a refusal trigger that must be controllable
# uniformly across DBs.
if [ "${call_num}" = "0" ]; then
  if [ -n "${MOCK_MONGO_COLLECTIONS_FIRST:-}" ]; then
    printf '%s\n' "${MOCK_MONGO_COLLECTIONS_FIRST}"
    exit 0
  fi
  printf '%s\n' "${MOCK_MONGO_COLLECTIONS:-0}"
  exit 0
fi
# Subsequent calls (post-flight): per-DB override for the target DB name
# takes priority, then fall back to the global. This lets a scenario
# answer "the restore left 2 collections in targetdb" while leaving the
# pre-flight answer for targetdb at its FIRST setting.
per_db_var="MOCK_MONGO_COLLECTIONS_${db}"
if [ -n "${!per_db_var:-}" ]; then
  printf '%s\n' "${!per_db_var}"
  exit 0
fi
printf '%s\n' "${MOCK_MONGO_COLLECTIONS:-0}"
SHIM
  chmod +x "${sb}/bin/mongosh"

  # mongorestore shim: logs every call (with args quoted) to
  # MONGORESTORE_LOG so tests can assert --db / --drop / source_dir.
  # Behaviour:
  #   MOCK_MONGORESTORE_EXIT (default 0)  → exit code
  #   MOCK_MONGORESTORE_VERIFY=<file>     → assert last positional arg's
  #                                          directory contains <file>
  #                                          (the "compare" step of the
  #                                          round trip). Exits 2 if not.
  cat >"${sb}/bin/mongorestore" <<'SHIM'
#!/usr/bin/env bash
logfile="${MONGORESTORE_LOG:-/tmp/mongorestore-shim.log}"
{
  printf 'mongorestore'
  for arg in "$@"; do
    printf ' %q' "${arg}"
  done
  printf '\n'
} >>"${logfile}"
if [ -n "${MOCK_MONGORESTORE_VERIFY:-}" ]; then
  src_dir="${!#}"
  if [ -f "${src_dir}/${MOCK_MONGORESTORE_VERIFY}" ]; then
    printf 'verified file %s present in %s\n' "${MOCK_MONGORESTORE_VERIFY}" "${src_dir}" >>"${logfile}"
  else
    printf 'VERIFY FAILED: file %s missing in %s\n' "${MOCK_MONGORESTORE_VERIFY}" "${src_dir}" >>"${logfile}"
    exit 2
  fi
fi
exit "${MOCK_MONGORESTORE_EXIT:-0}"
SHIM
  chmod +x "${sb}/bin/mongorestore"

  # mongodump shim: when MOCK_SEED_DIR is set, copies <seed>/<db>/* into
  # <out>/dump/<db>/* (the layout real mongodump produces with
  # --out=path). When unset, falls back to writing a single byte file in
  # <out>/dump/<db>/ so plain shim-only tests still work.
  cat >"${sb}/bin/mongodump" <<'SHIM'
#!/usr/bin/env bash
out=""
db=""
prev=""
for arg in "$@"; do
  case "${arg}" in
    --out=*) out="${arg#--out=}" ;;
    --db=*) db="${arg#--db=}" ;;
    --out) prev="--out" ;;
    --db) prev="--db" ;;
    *)
      case "${prev}" in
        --out) out="${arg}"; prev="" ;;
        --db) db="${arg}"; prev="" ;;
        *) prev="" ;;
      esac
      ;;
  esac
done
[ -n "${out}" ] || { echo "mongodump shim: no --out given" >&2; exit 2; }
[ -n "${db}" ]  || { echo "mongodump shim: no --db given" >&2; exit 2; }
if [ -n "${MOCK_SEED_DIR:-}" ] && [ -d "${MOCK_SEED_DIR}/${db}" ]; then
  mkdir -p "${out}/dump/${db}"
  cp -R "${MOCK_SEED_DIR}/${db}/." "${out}/dump/${db}/"
else
  mkdir -p "${out}/dump/${db}"
  bytes="${MONGODUMP_DUMP_BYTES:-1}"
  head -c "${bytes}" /dev/urandom >"${out}/dump/${db}/dump.bin"
fi
exit "${MONGODUMP_EXIT:-0}"
SHIM
  chmod +x "${sb}/bin/mongodump"

  # tar shim: respects MOCK_TAR_FAIL; otherwise defers to system tar.
  cat >"${sb}/bin/tar" <<'SHIM'
#!/usr/bin/env bash
if [ "${MOCK_TAR_FAIL:-0}" = "1" ]; then
  echo "tar shim: simulated failure" >&2
  exit 1
fi
exec /usr/bin/env -i PATH="/usr/bin:/bin" /usr/bin/tar "$@"
SHIM
  chmod +x "${sb}/bin/tar"

  printf '%s\n' "${sb}"
}

# Run one scenario. Args: label; sandbox; expected exit; ARCHIVE used;
# TARGET_DB used; extra env=value pairs.
#
# Always passes MONGORESTORE_LOG and MONGOSH_STATE_FILE inside env -i
# pointing into the sandbox, so the shims write to per-sandbox paths and
# call counts stay isolated from other scenarios.
run_scenario() {
  local label="$1" sb="$2" expected_exit="$3" archive="$4" target_db="$5"
  shift 5
  local env_args=("$@")

  local out_file err_file actual_exit
  out_file="$(mktemp)"
  err_file="$(mktemp)"

  env -i \
    HOME="${HOME}" \
    PATH="${sb}/bin:/usr/bin:/bin" \
    MONGO_URI="mongodb://mongodb:27017" \
    ARCHIVE="${archive}" \
    TARGET_DB="${target_db}" \
    SOURCE_DB="${target_db}" \
    MONGORESTORE_LOG="${sb}/mongorestore.log" \
    MONGOSH_STATE_FILE="${sb}/mongosh_state" \
    "${env_args[@]}" \
    bash "${SCRIPT_UNDER_TEST}" >"${out_file}" 2>"${err_file}"
  actual_exit=$?

  if [ "${actual_exit}" -eq "${expected_exit}" ]; then
    pass "[${label}] exited ${actual_exit} as expected"
  else
    fail "[${label}] expected exit ${expected_exit}, got ${actual_exit}; stderr=$(tr '\n' ' ' < "${err_file}")"
  fi

  # Acceptance criterion #2: failures must name the archive AND the reason.
  if [ "${expected_exit}" -ne 0 ]; then
    if grep -q "archive=${archive}" "${err_file}" \
       && grep -q "reason=" "${err_file}" \
       && grep -q "RESTORE FAILED" "${err_file}"; then
      pass "[${label}] error log names archive and reason"
    else
      fail "[${label}] error log missing archive/reason marker; stderr=$(tr '\n' ' ' < "${err_file}")"
    fi
  fi

  # Acceptance criterion #3: success path must end with the success marker.
  if [ "${expected_exit}" -eq 0 ]; then
    if grep -q "RESTORE SUCCEEDED" "${err_file}" && grep -q "archive=${archive}" "${err_file}"; then
      pass "[${label}] success log distinguishable + names archive"
    else
      fail "[${label}] success log missing marker; stderr=$(tr '\n' ' ' < "${err_file}")"
    fi
  fi

  rm -f "${out_file}" "${err_file}"
}

# Build a synthetic archive that the restore script will accept: a
# mongodump-style `dump/<SOURCE_DB>/` directory containing one marker file.
# Used by every scenario that needs a valid archive without going through
# the real mongo-backup.sh round trip.
make_synthetic_archive() {
  local sb="$1" source_db="$2"
  local archive="${sb}/dest/${source_db}-20250822T030000Z.tar.gz"
  local seed="${sb}/seed_${source_db}"
  mkdir -p "${seed}/dump/${source_db}"
  echo "fake bson data for ${source_db}" > "${seed}/dump/${source_db}/collection1.bson"
  echo '{"indexes":[]}' > "${seed}/dump/${source_db}/collection1.metadata.json"
  tar -C "${seed}" -czf "${archive}" .
  printf '%s\n' "${archive}"
}

# ---- happy path: valid archive, empty target DB, restore proceeds ----
echo "==> scenario: happy path (valid archive, empty target db)"
sb="$(make_sandbox)"
archive="$(make_synthetic_archive "${sb}" "future_gadget_lab")"
run_scenario "happy path" "${sb}" 0 "${archive}" "future_gadget_lab" \
  MOCK_MONGO_COLLECTIONS_FIRST=0 MOCK_MONGO_COLLECTIONS=3
if grep -q -- "--db=future_gadget_lab" "${sb}/mongorestore.log" 2>/dev/null; then
  pass "[happy path] mongorestore invoked with --db=target_db"
else
  fail "[happy path] mongorestore log missing --db=target_db; log=$(cat "${sb}/mongorestore.log" 2>/dev/null || echo 'missing')"
fi
if grep -q -- "dump/future_gadget_lab" "${sb}/mongorestore.log" 2>/dev/null; then
  pass "[happy path] mongorestore pointed at the dump/<db> directory"
else
  fail "[happy path] mongorestore log missing dump/<db> source path; log=$(cat "${sb}/mongorestore.log" 2>/dev/null || echo 'missing')"
fi
rm -rf "${sb}"

# ---- archive does not exist ----
echo "==> scenario: archive does not exist"
sb="$(make_sandbox)"
run_scenario "missing archive" "${sb}" 1 "${sb}/dest/does-not-exist.tar.gz" "future_gadget_lab"
rm -rf "${sb}"

# ---- archive is empty (0 bytes) ----
echo "==> scenario: archive is empty (0 bytes)"
sb="$(make_sandbox)"
archive="${sb}/dest/empty.tar.gz"
: >"${archive}"
run_scenario "empty archive" "${sb}" 1 "${archive}" "future_gadget_lab"
rm -rf "${sb}"

# ---- archive is corrupt (not a valid gzip) ----
echo "==> scenario: archive is corrupt (not a valid gzip)"
sb="$(make_sandbox)"
archive="${sb}/dest/corrupt.tar.gz"
echo "this is not a tar.gz at all" >"${archive}"
run_scenario "corrupt archive" "${sb}" 1 "${archive}" "future_gadget_lab"
rm -rf "${sb}"

# ---- target db is non-empty, no FORCE → refused ----
# Pre-flight reports 3 collections; script aborts before mongorestore runs.
echo "==> scenario: target db non-empty + no FORCE → refused"
sb="$(make_sandbox)"
archive="$(make_synthetic_archive "${sb}" "future_gadget_lab")"
run_scenario "refuse overwrite" "${sb}" 1 "${archive}" "future_gadget_lab" \
  MOCK_MONGO_COLLECTIONS=3
# Refusal must NOT have run mongorestore (the safe default).
if [ ! -s "${sb}/mongorestore.log" ]; then
  pass "[refuse overwrite] mongorestore NOT invoked when target non-empty + no FORCE"
else
  fail "[refuse overwrite] mongorestore ran despite refusal; log=$(cat "${sb}/mongorestore.log")"
fi
rm -rf "${sb}"

# ---- target db is non-empty, FORCE=1 → overwrite proceeds with --drop ----
# Pre-flight reports 3 collections; FORCE=1 → script proceeds; post-flight
# reports 5 (proves the restore ran, not the pre-flight count leaking through).
echo "==> scenario: target db non-empty + FORCE=1 → overwrite proceeds with --drop"
sb="$(make_sandbox)"
archive="$(make_synthetic_archive "${sb}" "future_gadget_lab")"
run_scenario "force overwrite" "${sb}" 0 "${archive}" "future_gadget_lab" \
  MOCK_MONGO_COLLECTIONS_FIRST=3 MOCK_MONGO_COLLECTIONS=5 FORCE=1
if grep -q -- "--drop" "${sb}/mongorestore.log" 2>/dev/null; then
  pass "[force overwrite] mongorestore invoked with --drop when FORCE=1"
else
  fail "[force overwrite] expected --drop flag in mongorestore args; log=$(cat "${sb}/mongorestore.log" 2>/dev/null || echo 'missing')"
fi
rm -rf "${sb}"

# ---- empty target + no FORCE → mongorestore called WITHOUT --drop ----
echo "==> scenario: empty target + no FORCE → restore proceeds WITHOUT --drop"
sb="$(make_sandbox)"
archive="$(make_synthetic_archive "${sb}" "future_gadget_lab")"
run_scenario "empty target no drop" "${sb}" 0 "${archive}" "future_gadget_lab" \
  MOCK_MONGO_COLLECTIONS_FIRST=0 MOCK_MONGO_COLLECTIONS=2
if ! grep -q -- "--drop" "${sb}/mongorestore.log" 2>/dev/null; then
  pass "[empty target no drop] mongorestore invoked WITHOUT --drop (safe default)"
else
  fail "[empty target no drop] unexpected --drop flag in mongorestore args; log=$(cat "${sb}/mongorestore.log" 2>/dev/null || echo 'missing')"
fi
rm -rf "${sb}"

# ---- ARCHIVE env var missing ----
echo "==> scenario: missing ARCHIVE env var"
sb="$(make_sandbox)"
run_scenario "missing archive var" "${sb}" 1 "" "future_gadget_lab"
rm -rf "${sb}"

# ---- TARGET_DB env var missing ----
echo "==> scenario: missing TARGET_DB env var"
sb="$(make_sandbox)"
archive="$(make_synthetic_archive "${sb}" "future_gadget_lab")"
run_scenario "missing target db var" "${sb}" 1 "${archive}" ""
rm -rf "${sb}"

# ---- mongosh pre-flight fails (MongoDB unreachable) ----
echo "==> scenario: mongosh pre-flight fails (MongoDB unreachable)"
sb="$(make_sandbox)"
archive="$(make_synthetic_archive "${sb}" "future_gadget_lab")"
run_scenario "mongosh unreachable" "${sb}" 1 "${archive}" "future_gadget_lab" \
  MOCK_MONGO_CONNECT_FAIL=1
rm -rf "${sb}"

# ---- mongorestore returns non-zero ----
# Only the pre-flight runs (it passes) before mongorestore is invoked; the
# shim's failure short-circuits the post-flight so MOCK_MONGO_COLLECTIONS_FIRST
# is all we need to set.
echo "==> scenario: mongorestore returns non-zero"
sb="$(make_sandbox)"
archive="$(make_synthetic_archive "${sb}" "future_gadget_lab")"
run_scenario "mongorestore fail" "${sb}" 1 "${archive}" "future_gadget_lab" \
  MOCK_MONGO_COLLECTIONS_FIRST=0 MOCK_MONGORESTORE_EXIT=1
rm -rf "${sb}"

# ---- SOURCE_DB != TARGET_DB (cross-database restore) ----
# mongorestore is called with --db=targetdb but pointed at dump/sourcedb.
echo "==> scenario: SOURCE_DB != TARGET_DB (cross-db restore)"
sb="$(make_sandbox)"
seed="${sb}/seed_cross"
mkdir -p "${seed}/dump/sourcedb"
echo "sourcedb content" > "${seed}/dump/sourcedb/c.bson"
archive="${sb}/dest/sourcedb-20250822T030000Z.tar.gz"
tar -C "${seed}" -czf "${archive}" .
run_scenario "cross-db restore" "${sb}" 0 "${archive}" "targetdb" \
  SOURCE_DB=sourcedb MOCK_MONGO_COLLECTIONS_FIRST=0 MOCK_MONGO_COLLECTIONS_targetdb=2
if grep -q -- "--db=targetdb" "${sb}/mongorestore.log" 2>/dev/null \
   && grep -q -- "dump/sourcedb" "${sb}/mongorestore.log" 2>/dev/null; then
  pass "[cross-db restore] mongorestore pointed at dump/sourcedb with --db=targetdb"
else
  fail "[cross-db restore] expected --db=targetdb + dump/sourcedb; log=$(cat "${sb}/mongorestore.log" 2>/dev/null || echo 'missing')"
fi
rm -rf "${sb}"

# ---- archive uses the legacy layout (no dump/ subdir) ----
# mongodump's default puts the dump under a `dump/` subdir, but a hand-rolled
# archive (or older mongodump with --out=.) might be just `<dbname>/...`.
# The restore script tolerates both layouts.
echo "==> scenario: archive uses legacy layout (no dump/ subdir)"
sb="$(make_sandbox)"
seed="${sb}/seed_legacy"
mkdir -p "${seed}/future_gadget_lab"
echo "legacy layout content" > "${seed}/future_gadget_lab/c.bson"
archive="${sb}/dest/legacy-20250822T030000Z.tar.gz"
tar -C "${seed}" -czf "${archive}" .
run_scenario "legacy layout" "${sb}" 0 "${archive}" "future_gadget_lab" \
  MOCK_MONGO_COLLECTIONS_FIRST=0 MOCK_MONGO_COLLECTIONS=1
# Log line ends with the source_dir path (which ends with the db name
# itself when the archive has the legacy layout).
if grep -qE "future_gadget_lab'?\s*\$" "${sb}/mongorestore.log" 2>/dev/null; then
  pass "[legacy layout] mongorestore pointed at the legacy <db> directory (source_dir ends with db name)"
else
  fail "[legacy layout] mongorestore not pointed at legacy layout; log=$(cat "${sb}/mongorestore.log" 2>/dev/null || echo 'missing')"
fi
rm -rf "${sb}"

# ---- archive does not contain the expected directory ----
echo "==> scenario: archive does not contain expected source_db directory"
sb="$(make_sandbox)"
seed="${sb}/seed_other"
mkdir -p "${seed}/dump/someotherdb"
echo "wrong db content" > "${seed}/dump/someotherdb/c.bson"
archive="${sb}/dest/wrong-20250822T030000Z.tar.gz"
tar -C "${seed}" -czf "${archive}" .
# SOURCE_DB defaults to TARGET_DB which doesn't exist in this archive.
run_scenario "wrong source_db" "${sb}" 1 "${archive}" "future_gadget_lab" \
  MOCK_MONGO_COLLECTIONS=0
rm -rf "${sb}"

# ---- ROUND TRIP: seed → back up (mongo-backup.sh) → restore (mongo-restore.sh) → compare ----
# Acceptance criterion #3: prove that an archive produced by the backup
# script can be successfully read back by the restore script, and that
# the seed data survives the trip.
echo "==> scenario: round trip (seed → backup → restore → compare)"
sb="$(make_sandbox)"
SEED_FILE="collection1.bson"
SEED_CONTENT='round-trip seed marker v1'
seed_dir="${sb}/round_trip_seed/future_gadget_lab"
mkdir -p "${seed_dir}"
printf '%s' "${SEED_CONTENT}" > "${seed_dir}/${SEED_FILE}"
DEST_DIR="${sb}/backup_dir"

# Step 1: run mongo-backup.sh against the seed.
out_file="$(mktemp)"
err_file="$(mktemp)"
env -i \
  HOME="${HOME}" \
  PATH="${sb}/bin:/usr/bin:/bin" \
  MONGO_URI="mongodb://mongodb:27017" \
  MONGO_DB="future_gadget_lab" \
  DEST_DIR="${DEST_DIR}" \
  MOCK_SEED_DIR="${sb}/round_trip_seed" \
  bash "${BACKUP_SCRIPT_UNDER_TEST}" >"${out_file}" 2>"${err_file}"
backup_exit=$?
if [ "${backup_exit}" -ne 0 ]; then
  fail "[round trip] backup step exited ${backup_exit}; stderr=$(tr '\n' ' ' < "${err_file}")"
else
  pass "[round trip] backup step succeeded"
fi
# Locate the produced archive (the only file ending in .tar.gz in DEST_DIR).
archive="$(ls -1 "${DEST_DIR}/"*.tar.gz 2>/dev/null | head -1 || true)"
if [ -z "${archive}" ] || [ ! -f "${archive}" ]; then
  fail "[round trip] backup did not produce an archive in ${DEST_DIR}"
  rm -f "${out_file}" "${err_file}"
  rm -rf "${sb}"
  echo "==> summary: ${PASS} passed, ${FAIL} failed"
  [ "${FAIL}" -eq 0 ]
  exit 1
fi
pass "[round trip] backup produced archive ${archive##*/}"

# Confirm the seed file is actually inside the archive (intermediate check).
if tar -tzf "${archive}" | grep -q "dump/future_gadget_lab/${SEED_FILE}"; then
  pass "[round trip] archive contains dump/future_gadget_lab/${SEED_FILE}"
else
  fail "[round trip] archive missing seed file; contents=$(tar -tzf "${archive}" | head -10)"
fi

# Step 2: run mongo-restore.sh on the archive into a scratch target DB.
# MOCK_MONGORESTORE_VERIFY makes the mongorestore shim exit 2 unless the
# seed file is present in the source_dir it was given — this is the
# "compare" half of the round trip.
rm -f "${out_file}" "${err_file}"
out_file="$(mktemp)"
err_file="$(mktemp)"
env -i \
  HOME="${HOME}" \
  PATH="${sb}/bin:/usr/bin:/bin" \
  MONGO_URI="mongodb://mongodb:27017" \
  ARCHIVE="${archive}" \
  TARGET_DB="scratch_db" \
  SOURCE_DB="future_gadget_lab" \
  MONGORESTORE_LOG="${sb}/mongorestore.log" \
  MONGOSH_STATE_FILE="${sb}/mongosh_state" \
  MOCK_MONGO_COLLECTIONS_FIRST=0 \
  MOCK_MONGO_COLLECTIONS_scratch_db=2 \
  MOCK_MONGORESTORE_VERIFY="${SEED_FILE}" \
  bash "${SCRIPT_UNDER_TEST}" >"${out_file}" 2>"${err_file}"
restore_exit=$?
if [ "${restore_exit}" -eq 0 ]; then
  pass "[round trip] restore step succeeded (seed file survived the trip)"
else
  fail "[round trip] restore step exited ${restore_exit}; stderr=$(tr '\n' ' ' < "${err_file}")"
fi
# Assert the mongorestore shim received --db=scratch_db (the scratch target).
if grep -q -- "--db=scratch_db" "${sb}/mongorestore.log" 2>/dev/null; then
  pass "[round trip] restore pointed at scratch_db (proves restore honors TARGET_DB)"
else
  fail "[round trip] restore did not pass --db=scratch_db; log=$(cat "${sb}/mongorestore.log" 2>/dev/null || echo 'missing')"
fi
# Assert the mongorestore shim received the dump/future_gadget_lab path
# (proves the restore extracted the same layout mongo-backup.sh produced).
if grep -q -- "dump/future_gadget_lab" "${sb}/mongorestore.log" 2>/dev/null; then
  pass "[round trip] restore received dump/future_gadget_lab (proves round-trip layout match)"
else
  fail "[round trip] restore did not see dump/future_gadget_lab path; log=$(cat "${sb}/mongorestore.log" 2>/dev/null || echo 'missing')"
fi
rm -f "${out_file}" "${err_file}"
rm -rf "${sb}"

# ---- Regression: TMPDIR unwritable (readOnlyRootFilesystem: true, no /tmp mount) ----
# Same shape as backup_test.sh's coverage for issue #90's review finding #1.
echo "==> scenario: TMPDIR unwritable (readOnlyRootFilesystem: true, no /tmp mount)"
sb="$(make_sandbox)"
archive="$(make_synthetic_archive "${sb}" "future_gadget_lab")"
echo not-a-directory >"${sb}/notdir"
out_file="$(mktemp)"
err_file="$(mktemp)"
env -i \
  HOME="${HOME}" \
  PATH="${sb}/bin:/usr/bin:/bin" \
  TMPDIR="${sb}/notdir" \
  MONGO_URI="mongodb://mongodb:27017" \
  ARCHIVE="${archive}" \
  TARGET_DB="future_gadget_lab" \
  SOURCE_DB="future_gadget_lab" \
  MONGOSH_STATE_FILE="${sb}/mongosh_state" \
  MOCK_MONGO_COLLECTIONS_FIRST=0 \
  bash "${SCRIPT_UNDER_TEST}" >"${out_file}" 2>"${err_file}"
actual_exit=$?
if [ "${actual_exit}" -ne 0 ] \
   && grep -q "archive=${archive}" "${err_file}" \
   && grep -q "reason=" "${err_file}" \
   && grep -q "RESTORE FAILED" "${err_file}"; then
  pass "[EROFS on /tmp] exited ${actual_exit} AND emitted RESTORE FAILED archive=… reason=…"
else
  fail "[EROFS on /tmp] expected non-zero exit + named-archive failure; got exit=${actual_exit}; stderr=$(tr '\n' ' ' < "${err_file}")"
fi
rm -f "${out_file}" "${err_file}"
rm -rf "${sb}"

# ---- Regression: credentialed MONGO_URI is redacted in logs ----
# Mirrors backup_test.sh's coverage for issue #104: the password segment
# of MONGO_URI must not appear in stderr.
echo "==> scenario: credentialed MONGO_URI is redacted in logs"
sb="$(make_sandbox)"
archive="$(make_synthetic_archive "${sb}" "future_gadget_lab")"
out_file="$(mktemp)"
err_file="$(mktemp)"
env -i \
  HOME="${HOME}" \
  PATH="${sb}/bin:/usr/bin:/bin" \
  MONGO_URI='mongodb://backup:supersecretpw@mongodb:27017/?authSource=admin' \
  ARCHIVE="${archive}" \
  TARGET_DB="future_gadget_lab" \
  SOURCE_DB="future_gadget_lab" \
  MONGOSH_STATE_FILE="${sb}/mongosh_state" \
  MOCK_MONGO_COLLECTIONS_FIRST=0 \
  MOCK_MONGO_COLLECTIONS=2 \
  bash "${SCRIPT_UNDER_TEST}" >"${out_file}" 2>"${err_file}"
actual_exit=$?
if [ "${actual_exit}" -eq 0 ]; then
  pass "[redact credentials] happy-path restore still succeeds with credentialed URI"
else
  fail "[redact credentials] expected exit 0, got ${actual_exit}; stderr=$(tr '\n' ' ' < "${err_file}")"
fi
if ! grep -q 'supersecretpw' "${err_file}" 2>/dev/null; then
  pass "[redact credentials] password literal absent from stderr"
else
  fail "[redact credentials] password literal leaked into stderr: $(tr '\n' ' ' < "${err_file}")"
fi
if grep -q 'backup:\*\*\*@' "${err_file}" 2>/dev/null; then
  pass "[redact credentials] redacted marker present in stderr"
else
  fail "[redact credentials] expected 'backup:***@' marker missing in stderr: $(tr '\n' ' ' < "${err_file}")"
fi
if grep -q 'RESTORE STARTING' "${err_file}" 2>/dev/null \
   && grep -q "archive=${archive}" "${err_file}" 2>/dev/null; then
  pass "[redact credentials] RESTORE STARTING + archive still present"
else
  fail "[redact credentials] RESTORE STARTING or archive missing: $(tr '\n' ' ' < "${err_file}")"
fi
rm -f "${out_file}" "${err_file}"
rm -rf "${sb}"

echo "==> summary: ${PASS} passed, ${FAIL} failed"
[ "${FAIL}" -eq 0 ]
