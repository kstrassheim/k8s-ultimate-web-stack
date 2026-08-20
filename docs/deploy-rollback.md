# Deploy rollback procedure

> Audience: the operator who needs to roll a bad deploy back without
> making it worse. This is the runbook for "we just shipped a bad
> release; what now?"

## TL;DR

This repo deploys via **mutable image tags + ArgoCD self-heal**
(`k8s/environments/<env>/kustomization.yaml` + `argocd/apps/<env>.yaml`).
That choice makes two commands you'd reach for by default — `kubectl
rollout undo` and `argocd app rollback` — ineffective (see
[Why `kubectl rollout undo` is not enough](#why-kubectl-rollout-undo-is-not-enough)).

The correct rollback path is **always to cut a new release that
reverts the bad change, and let CI rebuild the mutable image and
roll the pods**. There is also a dev-only shortcut that swaps the
image tag to an immutable `:sha-<sha>` reference — see
[Procedure B — image swap (dev only)](#procedure-b--image-swap-dev-only).

| Channel | What tracks | What reverts it |
|---------|-------------|-----------------|
| dev (`ultimate-web-stack-dev`) | latest commit on `main` | push a revert commit to `main` (CI rebuilds `:dev`); or swap `:sha-<sha>` (Option B) |
| test (`ultimate-web-stack-test`) | highest semver git tag (`vX.Y.Z`, `[0-9]*`) | push a new patch tag with the revert; CI rebuilds `:test` immediately |
| prod (`ultimate-web-stack`) | highest semver git tag (`vX.Y.Z`, `[0-9]*`) | push a new patch tag **and then approve the GitHub `prod` environment** so CI rebuilds `:prod` |

## What is NOT reverted by a rollback

A rollback in this repo only touches the `web` Deployment's pods. The
following are **not** reverted and require separate procedures:

- **MongoDB data.** The `mongodb-data` PVC in each env namespace
  (`ultimate-web-stack` / `-dev` / `-test`) holds the database the web
  pods read and write. Rolling the web pods back does not roll data
  back. The bad release's writes remain until you restore from a
  backup — see [Restoring data from a backup](#restoring-data-from-a-backup).
- **MongoDB schema (collection / document shape).** There are no
  formal migrations in this repo — the FastAPI backend reads
  collections via `pymongo` with no schema validation. If the bad
  release writes a new field, the rolled-back code will still see
  documents containing that field. If the bad release renamed or
  removed a field, the rolled-back code may 500 on documents written
  by the bad release. Diagnose with `mongosh` against
  `mongodb://mongodb:27017` (in-cluster) and the application logs;
  fix by editing data or restoring from backup.
- **Other Kubernetes resources.** MongoDB StatefulSet, the nightly
  backup CronJob, NetworkPolicies, RBAC, the namespaces themselves —
  none of these are touched by a deploy rollback. ArgoCD does
  reconcile them when it re-syncs (because the manifests move with
  the new tag), so a manifest-level bad change IS reverted by the
  procedure — but only as a side-effect of ArgoCD's manifest sync,
  not by anything this runbook does directly.
- **Entra ID App Reg.** Provisioned by Terraform (`terraform/`), out
  of band of the deploy. A bad Terraform change is reverted by
  running `terraform apply` against the previous state, not by a
  deploy rollback. Note that the GitHub `prod` environment gates
  CI's terraform-apply, so a revert+new-tag alone won't undo an App
  Reg change — that requires a manual `terraform apply` from the
  previous commit (or re-running CI's terraform job after reverting
  the terraform/ change).
- **Container image history.** The previous `:dev` / `:test` / `:prod`
  image is overwritten on each release (mutable tag). It is not
  recoverable from the registry after a new release lands unless
  you also kept an immutable `:sha-<sha>` reference (CI only
  creates this for dev — see [Immutable references](#immutable-references)).

## Why `kubectl rollout undo` is not enough

`kubectl rollout undo deployment/web -n <ns>` rolls the Deployment's
pod template back to an earlier ReplicaSet. But:

- `imagePullPolicy: Always` on the `web` container (see
  `k8s/web/web.yaml`) makes the new pod re-pull the current image,
  which is the same mutable tag (`web:dev` / `web:test` / `web:prod`)
  pointing at the same broken image.
- ArgoCD's `syncPolicy.automated.selfHeal: true` (see
  `argocd/apps/<env>.yaml`) re-syncs the Deployment back to
  whatever manifest the Application's `targetRevision` resolves to —
  which is unchanged after a `kubectl rollout undo`, so selfHeal
  reverts the rollback within seconds.

`argocd app rollback` has the same problem: it rolls the *manifest*
back, but the manifest's `image:` field still says `:prod` and the
`:prod` tag still points at the broken image.

The only thing that changes the live image is the mutable tag being
overwritten by a new build — which only happens when CI rebuilds
the image. So the rollback path has to go through git + CI, not
through kubectl.

## Pre-flight

1. Confirm cluster reachability and current state:
   ```bash
   kubectl cluster-info
   kubectl get pods -n ultimate-web-stack      -l app=web
   kubectl get pods -n ultimate-web-stack-test -l app=web
   kubectl get pods -n ultimate-web-stack-dev  -l app=web
   ```

2. Identify the bad release and the last known-good release:
   ```bash
   git fetch --tags
   git tag --sort=-v:refname | grep -E '^[0-9]+\.' | head -10
   git log --oneline -20
   ```

3. Check ArgoCD's view of each app (requires `argocd` CLI to be
   installed and logged in — the cluster-local CLI works from any
   node with kubeconfig + the `argocd-server` Service):
   ```bash
   argocd app list
   argocd app history ultimate-web-stack      --revision 0
   argocd app history ultimate-web-stack-test --revision 0
   argocd app history ultimate-web-stack-dev  --revision 0
   ```
   The output tells you:
   - The source revision ArgoCD is currently synced to (the "what
     git says" state).
   - The revision the cluster actually has (the "what's running"
     state).
   - Whether the app is `Synced` / `OutOfSync` / `Healthy` /
     `Degraded` / `Progressing`.

4. Sanity-check the registry actually has the broken image (it
   should — if it doesn't, the bad release never landed and you
   have a different problem):
   ```bash
   podman pull mainpi.local:5000/ultimate-web-stack/web:prod  # or :test / :dev
   ```

## Procedure A — revert + new tag (recommended)

This is the only option that works for test and prod, and the
preferred option for dev because it leaves the repo in a coherent
state.

### A.1 — Revert the bad change on `main`

```bash
git checkout main
git pull origin main
git revert <bad-commit-sha>
# If the bad change was a merge commit (squash merges look like
# regular commits, so this only applies to a true merge with two
# parents), pass -m 1 to keep the mainline:
#   git revert -m 1 <merge-commit-sha>
git push origin main
```

If the bad change is on a non-`main` branch, branch off `main`,
cherry-pick the revert there, and tag from that branch.

### A.2 — Tag the new release

```bash
# Pick the next semver. If the bad tag was v0.8.2, push v0.8.3.
# Bare semver tags are accepted by the workflow trigger
# (.github/workflows/build-images.yml).
git tag v0.8.3            # annotated or lightweight both work
git push origin v0.8.3
```

For dev, this step is optional: dev tracks `main` (not tags), so
step A.1 alone is enough — the next CI run on `main` rebuilds
`:dev` + `:sha-<sha>` and rolls the dev Deployment.

### A.3 — Watch CI roll the affected environments

```bash
# Find the workflow runs triggered by the push:
gh run list --workflow=build-images.yml --limit=5
# Watch the one(s) still running:
gh run watch <run-id>
```

What each job does (see `.github/workflows/build-images.yml` +
`.github/workflows/_build-env.yml`):

- **`dev` job** — triggered by `push` to `main`. Builds
  `web:dev` + `web:sha-<sha>` and `kubectl rollout restart
  deployment/web -n ultimate-web-stack-dev` to pull them. No
  approval.
- **`test` job** — triggered by `refs/tags/v*` or
  `refs/tags/[0-9]*`. Builds `web:test` and rolls the test
  Deployment. No approval.
- **`prod` job** — triggered by the tag, but the entire
  `_build-env.yml` pipeline binds to the GitHub `prod` environment
  (`environment: ${{ inputs.gh_environment }}`), so it blocks
  until a reviewer approves that environment. Until approved, CI
  has not rebuilt `:prod` and the prod Deployment keeps serving
  the old (broken) image. Approve the `prod` environment in the
  GitHub UI (Settings → Environments → prod → "Required reviewers"
  → approve the pending run) to unblock the build.

### A.4 — Verify each environment

```bash
# Watch each rollout to completion (timeout matches the CI runner):
kubectl rollout status deployment/web -n ultimate-web-stack      --timeout=300s
kubectl rollout status deployment/web -n ultimate-web-stack-test --timeout=300s
kubectl rollout status deployment/web -n ultimate-web-stack-dev  --timeout=300s

# Per PR #100, the readiness probe hits /ready which checks MongoDB.
# Confirm the new pod is serving:
kubectl exec -n ultimate-web-stack      deploy/web -- curl -sf http://localhost:8000/ready
kubectl exec -n ultimate-web-stack-test deploy/web -- curl -sf http://localhost:8000/ready
kubectl exec -n ultimate-web-stack-dev  deploy/web -- curl -sf http://localhost:8000/ready

# Confirm ArgoCD sees the app as Synced + Healthy:
argocd app get ultimate-web-stack
argocd app get ultimate-web-stack-test
argocd app get ultimate-web-stack-dev

# From outside the cluster, hit the public URL (Cloudflare Access)
# or the internal LAN URL (canonical for the tester):
curl -sf https://datapi.galaxus.box/ultimate-web-stack-dev/ready
curl -sf https://datapi.galaxus.box/ultimate-web-stack-test/ready
curl -sf https://datapi.galaxus.box/ultimate-web-stack/ready
```

### A.5 — Post-mortem

- If the bad release was a security incident, follow the
  incident-response runbook (separate; not in this repo).
- If the bad release is reproducible, write a regression test
  before re-merging the next change.
- If you had to revert a manifest-level change (e.g., a wrong env
  var or NetworkPolicy), confirm in ArgoCD's diff view that the
  synced manifests actually differ from the bad release's — ArgoCD
  reports `Synced` when manifests match even if the *image* hasn't
  rolled yet.

## Procedure B — image swap (dev only)

For dev, the previous `:dev` image is also kept at `:sha-<sha>` (CI's
`build-images.yml` pushes both tags). You can roll dev back to that
immutable tag without touching git history:

### B.1 — Confirm the previous image is in the registry

```bash
# Pick the last good SHA — the previous commit's :sha-<sha> tag.
podman pull mainpi.local:5000/ultimate-web-stack/web:sha-<good-sha>
```

### B.2 — Patch the dev kustomization

In `k8s/environments/dev/kustomization.yaml`, change:

```yaml
images:
  - name: mainpi.local:5000/ultimate-web-stack/web
    newTag: dev
```

to:

```yaml
images:
  - name: mainpi.local:5000/ultimate-web-stack/web
    newTag: sha-<good-sha>
```

Commit and push. ArgoCD auto-syncs the change and rolls the pod
back.

> ⚠️ ArgoCD's `selfHeal: true` reverts any kubectl-only edit within
> seconds. You MUST change git, not the live cluster, or the
> rollback will be undone immediately.

### B.3 — Restore the kustomization

**Restore `newTag: dev` and push again as soon as the rollback is
verified.** Otherwise:

- The next push to `main` triggers CI which rebuilds `:dev` and
  `:sha-<new-sha>` — but the Deployment manifest keeps pointing at
  `:sha-<good-sha>`, so the new code lands on the registry but not
  in the cluster.
- Anyone who later investigates "why isn't dev picking up commits?"
  has to dig through git history to find this rollback commit.

The cleanest sequence is **one revert commit + one restore commit**,
both pushed together:

```bash
git checkout main
# Make the revert change + commit + push (step B.2)
git push origin main
# ... wait for ArgoCD to roll back and you to verify ...
# Make the restore change + commit + push
git push origin main
```

This option does **not** work for test or prod because CI only
pushes `:sha-<sha>` for dev; for test/prod the previous image is
gone after the next release overwrites the mutable `:test` / `:prod`
tag.

## Restoring data from a backup

A deploy rollback does not roll data back. If the bad release
corrupted MongoDB, restore from the nightly backup:

- Backups run nightly at 03:00 UTC and are retained for 7 days
  (see `k8s/mongodb/backup-cronjob.yaml`).
- Format: `${MONGO_DB}-<UTC-timestamp>.tar.gz`, written to the
  `mongo-backup-data` PVC mounted at `/backup` in the backup pod.
  `MONGO_DB` is `future_gadget_lab` in prod,
  `future_gadget_lab_dev` in dev, `future_gadget_lab_test` in test
  (the env overlays set it — see `k8s/environments/<env>/patch-backup-env.yaml`).
- To inspect what's in the backup volume without running a backup:
  ```bash
  # Spawn a one-shot inspection pod that mounts the same PVC.
  # (Replace <env-namespace> with the right one for your env.)
  # The volume mount can't be expressed via kubectl run flags, so we
  # use --overrides to add the PVC volume to the generated Pod spec.
  kubectl run -n <env-namespace> backup-inspect \
    --rm -it --restart=Never \
    --image=mongo:8.0 \
    --overrides='{
      "apiVersion": "v1",
      "spec": {
        "containers": [{
          "name": "inspect",
          "image": "mongo:8.0",
          "command": ["ls", "-la", "/backup"],
          "volumeMounts": [{"name": "b", "mountPath": "/backup"}]
        }],
        "volumes": [{
          "name": "b",
          "persistentVolumeClaim": {"claimName": "mongo-backup-data"}
        }]
      }
    }'
  ```
- The actual restore-from-backup procedure (download the archive,
  extract it, run `mongorestore`) is intentionally scoped out of
  this runbook — it is a separate procedure tied to the backup
  format in `scripts/mongo-backup.sh`. The script's output
  (`BACKUP SUCCEEDED archive=... size=...`) names the archive;
  `tar -tzf <archive>` lists the contents; `mongorestore --uri=...
  --archive=<archive>` restores them.

## Immutable references

CI pushes one immutable reference alongside the mutable tags:

| Env | Image refs pushed by CI |
|-----|-------------------------|
| dev | `web:dev` + `web:sha-<sha>` |
| test | `web:test` only (mutable) |
| prod | `web:prod` only (mutable) |

For test/prod, the only way to keep an immutable reference is to
build the image yourself with:

```bash
docker build -t mainpi.local:5000/ultimate-web-stack/web:vX.Y.Z-immutable \
  -f backend/Dockerfile .
docker push mainpi.local:5000/ultimate-web-stack/web:vX.Y.Z-immutable
```

CI does not currently do this. If you need an immutable trail for
test/prod (e.g. for compliance), file an issue and reference this
runbook.

## Verification

This runbook was assembled by walking every command against the
manifests in this repo:

- `k8s/environments/dev/kustomization.yaml`,
  `k8s/environments/test/kustomization.yaml`,
  `k8s/environments/prod/kustomization.yaml`
- `argocd/apps/dev.yaml`, `argocd/apps/test.yaml`,
  `argocd/apps/prod.yaml`, `argocd/app-of-apps.yaml`
- `.github/workflows/build-images.yml`,
  `.github/workflows/_build-env.yml`
- `k8s/web/web.yaml` (imagePullPolicy + mutable tags)
- `k8s/mongodb/backup-cronjob.yaml` (backup cadence / retention /
  format)

and `kubectl kustomize k8s/environments/<env>` to confirm the image
tags resolve to `web:dev` / `web:test` / `web:prod` as documented.

No commands were executed against a live cluster — the agent
authoring this PR does not have cluster RBAC (the `openclaw`
ServiceAccount in `claw-code-local` is permission-less by design).
**Before relying on this runbook in anger, run Procedure A
end-to-end in dev** (the cheapest env), confirm CI rolls, ArgoCD
re-syncs, and `/ready` returns 200 on the new pod. Then re-verify
the same in test, and only then in prod (which also exercises the
GitHub `prod` environment approval gate).
