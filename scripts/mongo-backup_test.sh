#!/usr/bin/env bash
# mongo-backup_test.sh — smoke tests for scripts/mongo-backup.sh.
#
# Runs the script with shimmed binaries in a temp workspace so each scenario
# exits cleanly with the expected code + log marker. Designed to be runnable
# in CI (no k8s / mongod required) and locally:
#
#   bash scripts/mongo-backup_test.sh
#
# Exit 0 on full success, non-zero on the first failed assertion. Uses bash
# only — no dependency on pytest/jest. Kept in scripts/ (next to the script
# under test) because the project doesn't otherwise have a bash test runner.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_UNDER_TEST="${SCRIPT_DIR}/mongo-backup.sh"

PASS=0
FAIL=0

pass() { PASS=$((PASS + 1)); printf '  \033[32m✓\033[0m %s\n' "$*"; }
fail() { FAIL=$((FAIL + 1)); printf '  \033[31m✗\033[0m %s\n' "$*" >&2; }

# Build a self-contained sandbox: temp dir + shim bin/ + shimmed mongodump / df / tar.
make_sandbox() {
  local sb
  sb="$(mktemp -d -t mongo-backup-test.XXXXXX)"
  mkdir -p "${sb}/bin" "${sb}/dest"

  # df shim: reports a free-space value controllable by ${MOCK_FREE_KB}.
  cat >"${sb}/bin/df" <<'SHIM'
#!/usr/bin/env bash
# Output the standard `df -Pk <path>` two-line block. Reads free KB from
# MOCK_FREE_KB so each scenario can simulate a different volume state.
free_kb="${MOCK_FREE_KB:-1048576}"
path="$*"
# Strip flags we don't care about for the shim
for arg in "$@"; do
  case "${arg}" in
    -*) ;;
    *)  path="${arg}" ;;
  esac
done
# Match the real `df -Pk` layout: header + one data row.
printf 'Filesystem 1024-blocks Used Available Capacity Mounted-on\n'
printf '/dev/shim 1048576 0 %s 0%% %s\n' "${free_kb}" "${path}"
SHIM
  chmod +x "${sb}/bin/df"

  # mongodump shim: creates a tiny file in the out dir, exits per MONGODUMP_EXIT.
  cat >"${sb}/bin/mongodump" <<'SHIM'
#!/usr/bin/env bash
# Args ignored. Behaviour controlled by env:
#   MONGODUMP_EXIT  -> exit code (default 0 = success)
#   MONGODUMP_DUMP_BYTES -> how many bytes of "dump" to write (default 1)
out=""
for arg in "$@"; do
  case "${arg}" in
    --out=*) out="${arg#--out=}" ;;
    --out)   shift_next=1 ;;
    *)       [ "${shift_next:-0}" = "1" ] && out="${arg}" && shift_next=0 ;;
  esac
done
[ -n "${out}" ] || { echo "mongodump shim: no --out given" >&2; exit 2; }
mkdir -p "${out}"
bytes="${MONGODUMP_DUMP_BYTES:-1}"
head -c "${bytes}" /dev/urandom >"${out}/dump.bin"
exit "${MONGODUMP_EXIT:-0}"
SHIM
  chmod +x "${sb}/bin/mongodump"

  # tar shim: respects MOCK_TAR_FAIL; otherwise creates a real gzip-compressed
  # file so the post-flight `tar -tzf` check passes.
  cat >"${sb}/bin/tar" <<'SHIM'
#!/usr/bin/env bash
if [ "${MOCK_TAR_FAIL:-0}" = "1" ]; then
  echo "tar shim: simulated ENOSPC" >&2
  exit 1
fi
exec /usr/bin/env -i PATH="/usr/bin:/bin" /usr/bin/tar "$@"
SHIM
  chmod +x "${sb}/bin/tar"

  printf '%s\n' "${sb}"
}

# Run one scenario. Args: label; sandbox; expected exit; DEST_DIR used;
# extra env=value pairs.
run_scenario() {
  local label="$1" sb="$2" expected_exit="$3" dest_dir="$4"
  shift 4
  local env_args=("$@")

  local out_file err_file actual_exit
  out_file="$(mktemp)"
  err_file="$(mktemp)"

  # Invoke the script with the shim PATH and the scenario's env overrides.
  env -i \
    HOME="${HOME}" \
    PATH="${sb}/bin:/usr/bin:/bin" \
    MONGO_URI="mongodb://mongodb:27017" \
    MONGO_DB="future_gadget_lab" \
    DEST_DIR="${dest_dir}" \
    "${env_args[@]}" \
    bash "${SCRIPT_UNDER_TEST}" >"${out_file}" 2>"${err_file}"
  actual_exit=$?

  if [ "${actual_exit}" -eq "${expected_exit}" ]; then
    pass "[${label}] exited ${actual_exit} as expected"
  else
    fail "[${label}] expected exit ${expected_exit}, got ${actual_exit}; stderr=$(tr '\n' ' ' < "${err_file}")"
  fi

  # Acceptance criterion 2: failures must name the destination AND the reason.
  if [ "${expected_exit}" -ne 0 ]; then
    if grep -q "destination=${dest_dir}" "${err_file}" \
       && grep -q "reason=" "${err_file}" \
       && grep -q "BACKUP FAILED" "${err_file}"; then
      pass "[${label}] error log names destination and reason"
    else
      fail "[${label}] error log missing destination/reason marker; stderr=$(tr '\n' ' ' < "${err_file}")"
    fi
  fi

  # Acceptance criterion 3: success path must end with the success marker.
  if [ "${expected_exit}" -eq 0 ]; then
    if grep -q "BACKUP SUCCEEDED" "${err_file}" && grep -q "archive=${dest_dir}" "${err_file}"; then
      pass "[${label}] success log distinguishable + names archive"
    else
      fail "[${label}] success log missing marker; stderr=$(tr '\n' ' ' < "${err_file}")"
    fi
  fi

  rm -f "${out_file}" "${err_file}"
}

echo "==> scenario: successful backup"
sb="$(make_sandbox)"
run_scenario "happy path" "${sb}" 0 "${sb}/dest"
rm -rf "${sb}"

echo "==> scenario: destination volume full"
sb="$(make_sandbox)"
run_scenario "volume full" "${sb}" 1 "${sb}/dest" MOCK_FREE_KB=10
rm -rf "${sb}"

echo "==> scenario: mongodump fails"
sb="$(make_sandbox)"
run_scenario "mongodump exit 1" "${sb}" 1 "${sb}/dest" MONGODUMP_EXIT=1
rm -rf "${sb}"

echo "==> scenario: mongodump produces zero bytes"
sb="$(make_sandbox)"
run_scenario "mongodump empty dump" "${sb}" 1 "${sb}/dest" MONGODUMP_DUMP_BYTES=0
rm -rf "${sb}"

echo "==> scenario: tar compression fails (ENOSPC mid-write)"
sb="$(make_sandbox)"
run_scenario "tar fails" "${sb}" 1 "${sb}/dest" MOCK_TAR_FAIL=1
rm -rf "${sb}"

echo "==> scenario: destination directory is read-only"
sb="$(make_sandbox)"
# Point DEST_DIR at an existing, non-writable directory inside the sandbox.
mkdir -p "${sb}/ro"
chmod 555 "${sb}/ro" 2>/dev/null || true
# We expect either the mkdir-or-create failure or the write-check failure;
# both surface a non-zero exit and a named-destination error.
run_scenario "dest read-only" "${sb}" 1 "${sb}/ro"
rm -rf "${sb}"

echo "==> summary: ${PASS} passed, ${FAIL} failed"
[ "${FAIL}" -eq 0 ]
