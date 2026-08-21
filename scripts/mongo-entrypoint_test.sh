#!/usr/bin/env bash
# mongo-entrypoint_test.sh — smoke tests for scripts/mongo-entrypoint.sh.
#
# Exercises the shell logic of the entrypoint wrapper with shimmed mongod /
# mongosh binaries so each scenario runs in a temp workspace without needing a
# real mongod or a real /data/db. Mirrors the approach of mongo-backup_test.sh.
#
# Designed to be runnable in CI (no k8s / mongod required) and locally:
#
#   bash scripts/mongo-entrypoint_test.sh
#
# Exit 0 on full success, non-zero on the first failed assertion. Bash only —
# no dependency on pytest/jest.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_UNDER_TEST="${SCRIPT_DIR}/mongo-entrypoint.sh"

PASS=0
FAIL=0

pass() { PASS=$((PASS + 1)); printf '  \033[32m✓\033[0m %s\n' "$*"; }
fail() { FAIL=$((FAIL + 1)); printf '  \033[31m✗\033[0m %s\n' "$*" >&2; }

# Build a self-contained sandbox: temp dir + shim bin/ + shimmed mongod /
# mongosh that record how they were called and simulate state transitions
# without actually starting a database server.
make_sandbox() {
  local sb
  sb="$(mktemp -d -t mongo-entrypoint-test.XXXXXX)"
  mkdir -p "${sb}/bin" "${sb}/data"

  # mongod shim: does NOT actually start a server. Logs the call to a file
  # so tests can assert the args passed. Supports the flags this entrypoint
  # actually uses (--fork / --shutdown / --dbpath / --bind_ip / --port /
  # --logpath / --pidfilepath). Passwords are redacted from the log; --auth
  # is NOT (it is not sensitive and tests need to assert on it).
  cat >"${sb}/bin/mongod" <<'SHIM'
#!/usr/bin/env bash
logfile="${MONGOD_LOG:-/tmp/mongod-shim.log}"
{
  printf 'mongod '
  for arg in "$@"; do
    case "$arg" in
      --password*|--pwd=*) printf '[REDACT] ' ;;
      *) printf '%q ' "$arg" ;;
    esac
  done
  printf '\n'
} >>"${logfile}"

# Detect --shutdown and either succeed (pidfile present and not MOCK_SHUTDOWN_FAIL)
# or fail (no pidfile, or MOCK_SHUTDOWN_FAIL=1).
shutdown_seen=0
for arg in "$@"; do
  if [ "$arg" = "--shutdown" ]; then
    shutdown_seen=1
    pidfile="/tmp/mongod-bootstrap.pid"
    prev=""
    for a in "$@"; do
      if [ "$prev" = "--pidfilepath" ]; then
        pidfile="$a"
      elif [ "${a#--pidfilepath=}" != "$a" ]; then
        pidfile="${a#--pidfilepath=}"
      fi
      prev="$a"
    done
    if [ -f "${pidfile}" ] && [ "${MOCK_SHUTDOWN_FAIL:-0}" != "1" ]; then
      rm -f "${pidfile}"
      exit 0
    fi
    exit 1
  fi
done

# Detect --fork and create the pidfile so the script's stop logic finds it.
for arg in "$@"; do
  if [ "$arg" = "--fork" ]; then
    pidfile="/tmp/mongod-bootstrap.pid"
    prev=""
    for a in "$@"; do
      if [ "$prev" = "--pidfilepath" ]; then
        pidfile="$a"
      elif [ "${a#--pidfilepath=}" != "$a" ]; then
        pidfile="${a#--pidfilepath=}"
      fi
      prev="$a"
    done
    echo "$$" >"${pidfile}"
    # Write a placeholder log so the "did not become ready" fallback has
    # something to tail on the readiness-timeout branch.
    touch /tmp/mongod-bootstrap.log
  fi
done
exit 0
SHIM
  chmod +x "${sb}/bin/mongod"

  # mongosh shim: simulates a server that's reachable when MOCK_MONGO_READY=1
  # and unreachable otherwise. Logs the call so tests can assert what was
  # passed (in particular that --file was used and --host 127.0.0.1).
  cat >"${sb}/bin/mongosh" <<'SHIM'
#!/usr/bin/env bash
logfile="${MONOSH_LOG:-/tmp/mongosh-shim.log}"
{
  printf 'mongosh '
  for arg in "$@"; do
    case "$arg" in
      --password*|--pwd=*) printf '[REDACT] ' ;;
      *) printf '%q ' "$arg" ;;
    esac
  done
  printf '\n'
} >>"${logfile}"

# Ping check (the entrypoint's readiness loop) — every --eval is treated as a
# ping in this shim; if MOCK_MONGO_READY=0 we report the server as down.
saw_eval=0
for arg in "$@"; do
  if [ "$arg" = "--eval" ]; then
    saw_eval=1
  fi
done
if [ "${saw_eval}" = "1" ]; then
  if [ "${MOCK_MONGO_READY:-1}" = "1" ]; then
    exit 0
  fi
  exit 1
fi

# --file invocation: simulate ensureUser succeeding (or failing).
if [ "${MOCK_MONGO_READY:-1}" = "0" ]; then
  echo "mongosh shim: server not ready" >&2
  exit 1
fi
if [ "${MOCK_PROVISION_FAIL:-0}" = "1" ]; then
  echo "mongosh shim: simulated provision failure" >&2
  exit 1
fi
echo "user ${MONGO_INITDB_ROOT_USERNAME:-root} created user"
echo "user ${APP_DB_USERNAME:-app} created user"
echo "user ${BACKUP_DB_USERNAME:-backup} created user"
exit 0
SHIM
  chmod +x "${sb}/bin/mongosh"

  printf '%s\n' "${sb}"
}

# Cleanup helper.
cleanup() {
  local sb="$1"
  rm -rf "${sb}"
  rm -f /tmp/mongod-bootstrap.log /tmp/mongod-bootstrap.pid
}

# Run one scenario: invoke the entrypoint with shimmed binaries and a
# controlled env, then assert the recorded behaviour. The script-under-test
# is invoked as the k8s container's command would invoke it:
#   bash /scripts/mongo-entrypoint.sh --dbpath /data/db --bind_ip 0.0.0.0 --auth
# so "$@" inside the script contains the final mongod flags.
run_scenario() {
  local label="$1" sb="$2"
  shift 2
  local env_args=("$@")

  local out_file err_file actual_exit
  out_file="$(mktemp)"
  err_file="$(mktemp)"

  env -i \
    HOME="${HOME}" \
    PATH="${sb}/bin:/usr/bin:/bin" \
    MONGOD_LOG="${sb}/mongod.log" \
    MONOSH_LOG="${sb}/mongosh.log" \
    "${env_args[@]}" \
    bash "${SCRIPT_UNDER_TEST}" \
      --dbpath /data/db \
      --bind_ip 0.0.0.0 \
      --auth \
      >"${out_file}" 2>"${err_file}"
  actual_exit=$?

  printf '%s\n' "---- stderr for ${label} ----" >&2
  cat "${err_file}" >&2
  printf '%s\n' "---- end stderr ----" >&2
  printf '%s\n' "---- mongod log ----" >&2
  cat "${sb}/mongod.log" >&2 || true
  printf '%s\n' "---- end mongod log ----" >&2
  printf '%s\n' "Exit code: ${actual_exit}" >&2

  SCEN_OUT_FILE="${out_file}"
  SCEN_ERR_FILE="${err_file}"
  SCEN_EXIT="${actual_exit}"
  SCEN_SB="${sb}"
}

assert_exit_0() {
  local label="$1"
  if [ "${SCEN_EXIT}" -eq 0 ]; then
    pass "[${label}] exit 0"
  else
    fail "[${label}] expected exit 0, got ${SCEN_EXIT}"
  fi
}

assert_exit_nonzero() {
  local label="$1"
  if [ "${SCEN_EXIT}" -ne 0 ]; then
    pass "[${label}] non-zero exit (${SCEN_EXIT})"
  else
    fail "[${label}] expected non-zero exit, got 0"
  fi
}

# Asserts that `needle` appears in any of the three recorded logs.
assert_log_contains() {
  local label="$1" needle="$2"
  if grep -q -- "${needle}" "${SCEN_SB}/mongod.log" 2>/dev/null \
     || grep -q -- "${needle}" "${SCEN_ERR_FILE}" 2>/dev/null \
     || grep -q -- "${needle}" "${SCEN_SB}/mongosh.log" 2>/dev/null; then
    pass "[${label}] log contains: ${needle}"
  else
    fail "[${label}] log missing: ${needle}"
  fi
}

# Asserts that `needle` appears in the mongod invocation log specifically
# (i.e. one of the mongod calls actually received this argument).
assert_mongod_arg() {
  local label="$1" needle="$2"
  if grep -q -- "${needle}" "${SCEN_SB}/mongod.log" 2>/dev/null; then
    pass "[${label}] mongod invocation contains: ${needle}"
  else
    fail "[${label}] mongod invocation missing: ${needle}"
  fi
}

# Asserts that `needle` does NOT appear in any of the recorded logs.
assert_log_not_contains() {
  local label="$1" needle="$2"
  if grep -q -- "${needle}" "${SCEN_SB}/mongod.log" 2>/dev/null \
     || grep -q -- "${needle}" "${SCEN_ERR_FILE}" 2>/dev/null \
     || grep -q -- "${needle}" "${SCEN_SB}/mongosh.log" 2>/dev/null; then
    fail "[${label}] log unexpectedly contains: ${needle}"
  else
    pass "[${label}] log correctly does NOT contain: ${needle}"
  fi
}

# ---- Scenario 1: full happy path ----
# User-provisioning env vars set, mongod fork + ready + provision + shutdown +
# final exec all succeed. mongod log should show: temp fork on 127.0.0.1,
# shutdown, and the final exec with the args from "$@" (--auth + --bind_ip
# 0.0.0.0).
echo "==> scenario: happy path"
sb="$(make_sandbox)"
run_scenario "happy" "${sb}" \
  MONGO_INITDB_ROOT_USERNAME=root MONGO_INITDB_ROOT_PASSWORD=rootpw \
  APP_DB_USERNAME=app APP_DB_PASSWORD=apppw \
  BACKUP_DB_USERNAME=backup BACKUP_DB_PASSWORD=backuppw
assert_exit_0 "happy"
assert_log_contains "happy" "starting user provisioning"
assert_mongod_arg "happy" "--fork"
assert_mongod_arg "happy" "--bind_ip"
assert_mongod_arg "happy" "127.0.0.1"
assert_mongod_arg "happy" "--shutdown"
# Final mongod invocation must include --auth (the whole point of phase 2).
assert_mongod_arg "happy" "--auth"
# Passwords must not leak into any recorded log.
assert_log_not_contains "happy" "rootpw"
assert_log_not_contains "happy" "apppw"
assert_log_not_contains "happy" "backuppw"
assert_log_contains "happy" "ready after"
assert_log_contains "happy" "provisioning users"
cleanup "${sb}"

# ---- Scenario 2: temp mongod never becomes ready ----
# The readiness loop hits its 60-iteration cap; the script must exit non-zero
# and surface the bootstrap log so the operator sees WHY it didn't come up.
echo "==> scenario: temp mongod never becomes ready"
sb="$(make_sandbox)"
run_scenario "not ready" "${sb}" \
  MONGO_INITDB_ROOT_USERNAME=root MONGO_INITDB_ROOT_PASSWORD=rootpw \
  APP_DB_USERNAME=app APP_DB_PASSWORD=apppw \
  BACKUP_DB_USERNAME=backup BACKUP_DB_PASSWORD=backuppw \
  MOCK_MONGO_READY=0
assert_exit_nonzero "not ready"
assert_log_contains "not ready" "ERROR"
assert_log_contains "not ready" "60s"
# No shutdown because the temp mongod never came up.
assert_log_not_contains "not ready" "--shutdown"
cleanup "${sb}"

# ---- Scenario 3: user provisioning fails (mongosh non-zero) ----
# mongosh --file exits non-zero mid-provision; subsequent steps must NOT
# silently continue. set -e + trap should make the script exit non-zero.
echo "==> scenario: mongosh provision fails"
sb="$(make_sandbox)"
run_scenario "provision fail" "${sb}" \
  MONGO_INITDB_ROOT_USERNAME=root MONGO_INITDB_ROOT_PASSWORD=rootpw \
  APP_DB_USERNAME=app APP_DB_PASSWORD=apppw \
  BACKUP_DB_USERNAME=backup BACKUP_DB_PASSWORD=backuppw \
  MOCK_PROVISION_FAIL=1
assert_exit_nonzero "provision fail"
# The shutdown must NOT have happened (no users, lock still held).
assert_log_not_contains "provision fail" "--shutdown"
# The final mongod exec must NOT have happened.
assert_log_not_contains "provision fail" "starting main mongod"
cleanup "${sb}"

# ---- Scenario 4: MONGO_INITDB_ROOT_USERNAME unset — pure pass-through ----
# When the operator hasn't created the Secret yet (or runs the image by
# hand without auth), the script must NOT do any provisioning and just
# `exec mongod "$@"`. mongod fork / mongosh / --shutdown must not appear.
echo "==> scenario: no MONGO_INITDB_ROOT_USERNAME — pure passthrough"
sb="$(make_sandbox)"
run_scenario "no bootstrap" "${sb}"
assert_exit_0 "no bootstrap"
assert_log_not_contains "no bootstrap" "--fork"
assert_log_not_contains "no bootstrap" "--shutdown"
# mongod must NOT have been forked.
assert_log_not_contains "no bootstrap" "127.0.0.1"
assert_log_contains "no bootstrap" "starting main mongod with --auth"
# Final mongod invocation should still include --auth.
assert_mongod_arg "no bootstrap" "--auth"
cleanup "${sb}"

# ---- Scenario 5: temp mongod fork succeeds, mongod --shutdown returns non-zero ----
# The script's SIGTERM fallback path. The script must NOT exit non-zero
# here — it logs a WARN and proceeds to phase 2.
echo "==> scenario: mongod --shutdown non-zero (SIGTERM fallback)"
sb="$(make_sandbox)"
run_scenario "shutdown fail" "${sb}" \
  MONGO_INITDB_ROOT_USERNAME=root MONGO_INITDB_ROOT_PASSWORD=rootpw \
  APP_DB_USERNAME=app APP_DB_PASSWORD=apppw \
  BACKUP_DB_USERNAME=backup BACKUP_DB_PASSWORD=backuppw \
  MOCK_SHUTDOWN_FAIL=1
assert_exit_0 "shutdown fail"
assert_log_contains "shutdown fail" "WARN"
assert_log_contains "shutdown fail" "starting main mongod with --auth"
# Final mongod invocation should still include --auth.
assert_mongod_arg "shutdown fail" "--auth"
cleanup "${sb}"

# ---- Scenario 6: idempotency on restart ----
# When the script runs against an existing /data/db with users already
# provisioned, it must NOT fail. The shim treats this as "everything works
# first try" — the same behaviour the entrypoint relies on for restarts
# (the real mongosh's getUser() returns the existing user and the
# ensureUser helper is a no-op).
echo "==> scenario: idempotent restart (users already exist)"
sb="$(make_sandbox)"
run_scenario "idempotent" "${sb}" \
  MONGO_INITDB_ROOT_USERNAME=root MONGO_INITDB_ROOT_PASSWORD=rootpw \
  APP_DB_USERNAME=app APP_DB_PASSWORD=apppw \
  BACKUP_DB_USERNAME=backup BACKUP_DB_PASSWORD=backuppw
assert_exit_0 "idempotent"
assert_mongod_arg "idempotent" "--fork"
assert_mongod_arg "idempotent" "--shutdown"
assert_mongod_arg "idempotent" "--auth"
cleanup "${sb}"

echo "==> summary: ${PASS} passed, ${FAIL} failed"
[ "${FAIL}" -eq 0 ]