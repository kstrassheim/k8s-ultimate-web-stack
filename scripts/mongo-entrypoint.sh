#!/usr/bin/env bash
# mongo-entrypoint.sh — two-phase mongod startup: bootstrap users, then start with --auth.
#
# Drop-in entrypoint for the mongod container in k8s/mongodb/mongodb.yaml.
# Closes issue #104 by replacing the bare `mongod` command with this wrapper,
# which:
#
#   Phase 1 (only when MONGO_INITDB_ROOT_USERNAME is set):
#     - Start a temporary mongod in the background WITHOUT --auth, bound to
#       127.0.0.1 only (the in-pod bootstrap process reaches it via localhost;
#       no other pod can reach 127.0.0.1 inside another pod's network namespace).
#     - Wait for it to accept connections.
#     - Provision three users (idempotent — skip if exists):
#         * Root (MONGO_INITDB_ROOT_USERNAME) — role: root, db: admin.
#           Never used by the app or the backup. Exists so the bootstrap path
#           is reproducible if the operator needs to re-seed after a wipe.
#         * App (APP_DB_USERNAME) — role: readWriteAnyDatabase. Functionally
#           equivalent to readWrite on the env's single database (each env
#           has its own MongoDB instance with only one database) and avoids
#           per-env patches needing to know the database name at user-create
#           time.
#         * Backup (BACKUP_DB_USERNAME) — role: readAnyDatabase + backup.
#           mongodump needs read across all DBs and the `backup` role for
#           internal metadata access during a dump.
#     - Shut the temporary mongod down cleanly so the lock file on /data/db
#       is released before phase 2.
#
#   Phase 2:
#     - exec mongod "$@" — replace the script process with mongod itself so
#       kubelet sees mongod as the container's PID 1 and signal handling
#       works as expected (SIGTERM from kubelet on pod termination goes
#       straight to mongod, which shuts down cleanly).
#
# Why two phases instead of just running the users script after mongod starts
# with --auth? Because mongod with --auth and no users rejects EVERY
# connection — including any "create the first user" bootstrap connection.
# The only way out without operator intervention is to start mongod without
# --auth first, create users, then restart with --auth. This script does
# that restart internally so the operator only has to deploy the StatefulSet
# — no manual `kubectl exec mongosh` step in between.
#
# Idempotency on restarts: when the temporary mongod starts against an
# existing /data/db with the users already provisioned, `ensureUser` finds
# them via `adminDb.getUser()` and no-ops. Phase 2 then starts the main
# mongod with --auth as usual. No re-provisioning, no duplicated users, no
# password drift (a pre-existing user is NEVER updated — changing passwords
# in the Secret does not retroactively change them in MongoDB; the operator
# must use a separate rotation procedure for that).

set -euo pipefail

log() { printf '[%s] [mongo-entrypoint] %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*" >&2; }

# ---- Only do the bootstrap dance when MONGO_INITDB_ROOT_USERNAME is set. ----
# When unset (e.g. someone running the script by hand with the mongod image,
# or a future commit that removes auth from the StatefulSet), mongod is
# started with whatever flags the caller passed via "$@" — no user
# provisioning, no two-phase dance.
if [ -n "${MONGO_INITDB_ROOT_USERNAME:-}" ] && [ -n "${MONGO_INITDB_ROOT_PASSWORD:-}" ]; then
  log "starting user provisioning (MONGO_INITDB_ROOT_USERNAME=${MONGO_INITDB_ROOT_USERNAME})"

  # ---- Phase 1a: start temporary mongod in the background, no --auth ----
  log "starting temporary mongod (no --auth, bind 127.0.0.1 only)"
  mongod \
    --dbpath /data/db \
    --bind_ip 127.0.0.1 \
    --port 27017 \
    --fork \
    --logpath /tmp/mongod-bootstrap.log \
    --pidfilepath /tmp/mongod-bootstrap.pid

  # ---- Phase 1b: wait for temporary mongod to accept connections ----
  log "waiting for temporary mongod"
  ready=""
  for i in $(seq 1 60); do
    if mongosh --host 127.0.0.1:27017 --quiet --eval "db.adminCommand({ping: 1})" >/dev/null 2>&1; then
      ready="yes"
      log "temporary mongod ready after ${i}s"
      break
    fi
    sleep 1
  done
  if [ -z "${ready}" ]; then
    log "ERROR: temporary mongod did not become ready within 60s"
    log "----- /tmp/mongod-bootstrap.log -----"
    cat /tmp/mongod-bootstrap.log >&2 || true
    log "----- end of log -----"
    exit 1
  fi

  # ---- Phase 1c: provision users via mongosh, idempotently ----
  log "provisioning users"

  # JS lives in a temp file so special characters in usernames / passwords
  # don't need shell-escaping. process.env.* is read inside the script so
  # the password never appears in argv or /proc/PID/cmdline.
  USER_PROVISION_JS="$(mktemp -t mongo-provision-XXXXXX.js)"
  trap 'rm -f "${USER_PROVISION_JS}"' EXIT

  cat >"${USER_PROVISION_JS}" <<'JS'
const adminDb = db.getSiblingDB('admin');

function ensureUser(username, password, roles) {
  let exists = false;
  try {
    if (adminDb.getUser(username)) {
      exists = true;
    }
  } catch (e) {
    // adminDb.getUser throws on missing user; treat as not-exists.
  }
  if (exists) {
    print('user ' + username + ' already exists, skipping');
    return false;
  }
  adminDb.createUser({
    user: username,
    pwd: password,
    roles: roles,
  });
  print('created user ' + username);
  return true;
}

ensureUser(
  process.env.MONGO_INITDB_ROOT_USERNAME,
  process.env.MONGO_INITDB_ROOT_PASSWORD,
  [{ role: 'root', db: 'admin' }]
);

ensureUser(
  process.env.APP_DB_USERNAME,
  process.env.APP_DB_PASSWORD,
  [{ role: 'readWriteAnyDatabase', db: 'admin' }]
);

ensureUser(
  process.env.BACKUP_DB_USERNAME,
  process.env.BACKUP_DB_PASSWORD,
  [
    { role: 'readAnyDatabase', db: 'admin' },
    { role: 'backup', db: 'admin' },
  ]
);
JS

  mongosh --host 127.0.0.1:27017 --quiet --file "${USER_PROVISION_JS}"

  rm -f "${USER_PROVISION_JS}"
  trap - EXIT

  # ---- Phase 1d: stop temporary mongod cleanly ----
  log "stopping temporary mongod"
  if ! mongod --dbpath /data/db --shutdown; then
    log "WARN: mongod --shutdown returned non-zero, sending SIGTERM to pidfile"
    if [ -f /tmp/mongod-bootstrap.pid ]; then
      kill -TERM "$(cat /tmp/mongod-bootstrap.pid)" 2>/dev/null || true
      sleep 2
    fi
  fi
fi

# ---- Phase 2: start main mongod with --auth (foreground, exec replaces script) ----
log "starting main mongod with --auth"
exec mongod "$@"