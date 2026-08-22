# k8s-ultimate-web-stack

A Kubernetes deployment implementation of the **ultimate-web-stack** project — the same FastAPI backend and React frontend you know from [ultimate-web-stack](https://github.com/kstrassheim/ultimate-web-stack), now running on a self-hosted k8s cluster managed via ArgoCD and GitOps.

This is not a reimplementation of the application logic — the app code is identical to ultimate-web-stack. The goal is to port the infrastructure from Azure App Service + CosmosDB + App Insights to a self-hosted Kubernetes environment with MongoDB, OpenTelemetry, and ArgoCD.

## What changed from ultimate-web-stack

| Concern | ultimate-web-stack | k8s-ultimate-web-stack |
|---------|-------------------|------------------------|
| **Runtime platform** | Azure App Service (F1 Free Plan) | Self-hosted k8s (Orange Pi, OpenClaw) |
| **Database** | Azure CosmosDB (serverless NoSQL) | MongoDB StatefulSet in-cluster |
| **Auth** | Entra ID + OpenTofu-provisioned App Reg | Same Entra ID App Reg; OpenTofu still handles App Reg creation |
| **Observability** | Azure App Insights | OpenTelemetry (otel-collector, Prometheus/Grafana ready) |
| **Secrets** | None (managed identity, no keys) | Sealed Secrets (cryptographically sealed K8s Secrets) |
| **IaC** | OpenTofu provisions everything | OpenTofu handles App Reg only; k8s manifests handle runtime infra |
| **Deployment method** | `az webapp up` / CI → Azure | ArgoCD app-of-apps → k8s cluster |
| **Environments** | dev / test / prod (Azure App Service slots) | dev / test / prod (k8s namespaces, kustomize overlays) |
| **Container registry** | Azure Container Apps registry | Self-hosted container registry |

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     mainpi k3s cluster                       │
│                                                              │
│  ┌─────────────┐        ┌───────────────────────────┐      │
│  │ MongoDB     │◄───────│  web  (FastAPI + SPA)      │      │
│  │ StatefulSet│        │  ×2 pods, port 8000        │      │
│  │  replSet   │        │  serves /api + the React   │      │
│  └─────────────┘        │  build from ./dist         │      │
│                          └─────────────┬─────────────┘      │
│                                        │                     │
│                                 ┌──────┴──────┐              │
│                                 │  web        │              │
│                                 │  Service    │              │
│                                 └─────────────┘              │
└───────────────────────────────────────────────┼──────────────┘
                                                │
                                    ┌───────────┴───────────┐
                                    │   ArgoCD (in-cluster) │
                                    │   app-of-apps        │
                                    └─────────────────────┘

The app is a SPA, so there is a single deployable: the FastAPI backend serves
both the API and the built React frontend (no separate frontend container).

GitOps flow:
  git push → ArgoCD detects drift → syncs k8s manifests → cluster updated
```

## Project structure

```
k8s-ultimate-web-stack/
├── backend/              # FastAPI app — serves the API and the built SPA
├── frontend/             # React app source (built into the web image)
├── k8s/                  # Kubernetes manifests
│   ├── web/              # web Deployment + Service (backend + SPA)
│   ├── mongodb/          # MongoDB StatefulSet
│   ├── common/           # namespaces (for manual apply)
│   └── environments/     # kustomize overlays (dev / test / prod) + per-env patches
├── argocd/               # ArgoCD app-of-apps + per-env Application manifests
│   ├── project.yaml      # AppProject (ultimate-web-stack)
│   ├── app-of-apps.yaml  # root Application
│   └── apps/             # dev.yaml / test.yaml / prod.yaml
├── terraform/            # Entra ID App Reg only
│   ├── app_reg.tf        # App registration + permissions
│   └── main.tf / outputs.tf
├── start-backend.js      # Backend launcher (mock & prod modes)
└── .github/workflows/   # CI (CodeQL + pytest + jest + cypress)
```

## Setup

### Prerequisites

- **Self-hosted k8s** cluster (Orange Pi + OpenClaw)
- **kubectl** configured for the cluster
- **ArgoCD** installed in-cluster
- **Container registry** — self-hosted registry
- **Entra ID** tenant (for App Reg — same as ultimate-web-stack)
- **OpenTofu** (>= 1.9, for App Reg provisioning only). **Not** HashiCorp Terraform: the state is encrypted with an Azure Key Vault key using OpenTofu's `azure_vault` key provider, and Terraform cannot read it.

### 1. Provision Entra ID App Reg

```bash
cd terraform
# terraform.tfvars is checked in and sets app_name. Do NOT set env there:
# backend.key is "${var.env}.tfstate" and a tfvars value outranks TF_VAR_env,
# which would make every environment use dev's state.
tofu init                       # defaults to dev
TF_VAR_env=test tofu init -reconfigure   # or test / prod
tofu plan
tofu apply
```

This creates the App Registration in Entra ID. The app code (backend/frontend) reads auth config from `terraform.config.json` or environment variables — same as ultimate-web-stack.

### 2. Build and push container images

Images live in the in-cluster registry. CI handles this automatically — the
`.github/workflows/build-images.yml` workflow runs on the in-cluster
self-hosted runner (`arc-runner-scale-k8s-ultimate-web-stack`, docker-in-docker)
and builds + pushes the `web` image on every push. The runner already trusts
the registry CA and gets credentials from the `registry-creds` secret, so no
setup is needed.

`main` is the dev channel; releases are **git tags / GitHub Releases**. Each env
has a mutable channel tag; CI builds it from the release commit and restarts the
deployment to pull it (ArgoCD can't roll a same-tag image, so the build job does
a `kubectl rollout restart`).

| Trigger | Image tag(s) | Environment | Gate |
|---------|--------------|-------------|------|
| push `main`         | `:dev` (+ `:sha-<sha>`) | `ultimate-web-stack-dev`  | — |
| create release `vX.Y.Z` | `:test` | `ultimate-web-stack-test` | none — rolls at once |
| create release `vX.Y.Z` | `:prod` | `ultimate-web-stack`      | GitHub `prod` environment approval |

Images come from `mainpi.local:5000` (nodes trust this host via the cluster
`registries.yaml`, so no pull secret is needed).

**Cutting a release:** create a GitHub Release (or push a tag) `vX.Y.Z` — no
script. CI builds `web:test` from that commit and rolls `ultimate-web-stack-test`
immediately; `web:prod` is built and rolled only after the `prod` GitHub
environment is approved (until then prod keeps serving the current image). The
build runner restarts the deployment via a narrow Role granted in
`k8s/rbac/runner-rollout-rbac.yaml`.

To build an image by hand:

```bash
# Single image: the Dockerfile builds the SPA and bundles it into the backend.
docker build -t mainpi.local:5000/ultimate-web-stack/web:dev -f backend/Dockerfile .
docker push mainpi.local:5000/ultimate-web-stack/web:dev
# dev's tag is mutable, so roll it out:  kubectl rollout restart deploy/web -n ultimate-web-stack-dev
```

### 3. Apply k8s manifests directly (one-shot)

```bash
kubectl apply -f k8s/common/namespaces.yaml
kubectl apply -k k8s/environments/dev
```

### 4. Or use ArgoCD GitOps (recommended)

Bootstrap once — apply the project, then the app-of-apps root. The root
watches `argocd/apps/` and creates the dev / test / prod Applications:

```bash
kubectl apply -f argocd/project.yaml
kubectl apply -f argocd/app-of-apps.yaml
```

Thereafter ArgoCD watches the git repo and syncs automatically. To force a sync:

```bash
argocd app sync ultimate-web-stack-dev
```

### 5. Environment configuration

Each environment (dev / test / prod) has a `kustomization.yaml` overlay that combines base manifests with per-env patches:

```bash
# Dev
kubectl apply -k k8s/environments/dev
# Test
kubectl apply -k k8s/environments/test
# Prod
kubectl apply -k k8s/environments/prod
```

Environment-specific settings (MongoDB URI, MOCK mode, etc.) are set via `k8s/environments/<env>/patch-web-env.yaml`.

### 6. Deployment model (namespaces + GitOps promotion)

Each environment maps to its own namespace. ArgoCD (running in-cluster on the
`mainpi` k3s cluster) reconciles each one. dev tracks `main`; **test and prod
both track the latest semver tag**, so one tag promotes through both:

| Environment | Namespace | Git ref (`targetRevision`) | Sync |
|-------------|-----------|----------------------------|------|
| **dev**  | `ultimate-web-stack-dev`  | `main` branch | automated (prune + self-heal) |
| **test** | `ultimate-web-stack-test` | latest semver tag (`*`) | automated (prune + self-heal) |
| **prod** | `ultimate-web-stack`      | latest semver tag (`*`) | automated; image gated by `prod` approval |

Promotion flow:

```
push to main             → dev rolls out
create GitHub Release vX → test rolls out immediately, prod after the
                           GitHub `prod`-environment approval on its image build
```

The ArgoCD Application definitions live in `argocd/apps/` — one file per
environment (`dev.yaml`, `test.yaml`, `prod.yaml`) — managed by the
`argocd/app-of-apps.yaml` root.

#### Access URLs

Each environment is reachable two ways:

| Environment | Internal (LAN) — **canonical for automated testing** | Public (Cloudflare Access, humans) |
|-------------|------------------------------------------------------|------------------------------------|
| **dev**  | `https://datapi.galaxus.box/ultimate-web-stack-dev/`  | `https://ultimate-web-stack-dev.futuristic.science/` |
| **test** | `https://datapi.galaxus.box/ultimate-web-stack-test/` | `https://ultimate-web-stack-test.futuristic.science/` |
| **prod** | `https://datapi.galaxus.box/ultimate-web-stack/`      | `https://ultimate-web-stack.futuristic.science/` |

The `*.futuristic.science` URLs sit behind **Cloudflare Access (Google SSO)** and
are for human browsers only. Automated tooling (the `claw-code-local` tester) has
no Google identity, so it must use the internal `datapi.galaxus.box` URLs — these
are also the registered Entra redirect URIs, so the bot can complete the Microsoft
login. The canonical dev test URL is published as `WEBAPP_URL` in
`.github/workflows/build-images.yml`.

## Running locally (mock mode)

```bash
# Backend (mock mode — no MongoDB required)
MOCK=true MONGODB_URI="" node start-backend.js

# Frontend
cd frontend
npm install
MOCK=true npm run dev
```

The mock mode uses TinyDB-backed mock data service, same as ultimate-web-stack.

## Test runs

```bash
# Backend (pytest)
cd backend && pytest -v --cov=. --cov-report=xml

# Frontend (Jest)
cd frontend && npm run test:coverage

# E2E (Cypress)
cd frontend && npm run test:e2e:headless
```

CI runs on every push to `main` / `prod` and on all PRs via `.github/workflows/ci.yml`:
- **CodeQL** security scan (Python + JavaScript)
- **pytest** backend unit tests with coverage
- **Jest** frontend unit tests with coverage
- **Cypress** e2e tests (headless, no intercepts — mock backend mode)

`.github/workflows/build-images.yml` builds + pushes the single `web` image
(backend + bundled SPA) to the in-cluster registry on every push to
`main` / `prod` and on `v*` tags
(see [Build and push container images](#2-build-and-push-container-images)).

## Secrets

No raw Secrets in git. Credentials are managed via the **Sealed Secrets** pattern:

1. Create a Secret manually once: `kubectl create secret generic my-secret --dry-run=client -o yaml`
2. Seal it: `kubeseal -o yaml > sealed-secret.yaml`
3. Commit `sealed-secret.yaml` to git
4. ArgoCD syncs the Sealed Secret; the sealed-secrets controller decrypts it in-cluster

MongoDB connection uses the Kubernetes-internal Service DNS (`mongodb://mongodb:27017`), so no credentials cross the cluster boundary.

## Key differences for developers

- **No Azure dependency** after App Reg is provisioned — all runtime infra is in the k8s cluster
- **MongoDB replaces CosmosDB** — same pymongo API, connection URI differs
- **OpenTelemetry replaces App Insights** — same structured logging, different exporter
- **ArgoCD replaces Azure App Service deployments** — GitOps sync instead of `az webapp up`
- **Self-hosted registry** — push with `--insecure` flag for Docker/Podman

## Operations

- **Rolling back a bad deploy** — see [`docs/deploy-rollback.md`](docs/deploy-rollback.md). Covers the `git revert + new tag` procedure, why `kubectl rollout undo` does not work here, what is NOT reverted (data, schema, Entra App Reg), and how to restore MongoDB from the nightly backup if the bad release corrupted data.
- **Restoring from a backup** — see [Restoring from a backup](#restoring-from-a-backup) below. The `scripts/mongo-restore.sh` script + `k8s/mongodb/restore-job-template.yaml` Job template give you a one-shot restore: pick an archive, fill in three env vars, apply the Job, watch the logs.

## Restoring from a backup

The nightly backup CronJob ([`k8s/mongodb/backup-cronjob.yaml`](k8s/mongodb/backup-cronjob.yaml)) writes `tar.gz` archives to the `mongo-backup-data` PVC mounted at `/backup` in the backup pod. Restoring one is a one-shot operation, not a scheduled one — you fill in [`k8s/mongodb/restore-job-template.yaml`](k8s/mongodb/restore-job-template.yaml) for the incident and apply it.

**Archive layout** (what `scripts/mongo-backup.sh` produces, what `scripts/mongo-restore.sh` reads):

- Format: `${MONGO_DB}-<UTC-timestamp>.tar.gz` (e.g. `future_gadget_lab-20260821T030000Z.tar.gz`).
- Content: `dump/<MONGO_DB>/<collection>.bson` + `dump/<MONGO_DB>/<collection>.metadata.json`. The `dump/` wrapper is mongodump's default with `--out=path`; the restore script tolerates the legacy flat layout (no `dump/`) too.
- Location: `mongo-backup-data` PVC, mounted at `/backup` in the backup pod.

**Pick an archive** — spawn a one-shot inspection pod with the PVC mounted (replace `<env-namespace>` with `ultimate-web-stack`, `ultimate-web-stack-dev`, or `ultimate-web-stack-test`):

```bash
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

Inside that pod, `tar -tzf /backup/<archive-name>.tar.gz` lists the contents (one row per BSON file) so you can confirm it actually has the data you expect before triggering a restore.

**Run the restore** — copy [`k8s/mongodb/restore-job-template.yaml`](k8s/mongodb/restore-job-template.yaml) to a per-incident file (e.g. `restore-2026-08-22.yaml`) and fill in:

| Field | Example | Notes |
|-------|---------|-------|
| `metadata.namespace` | `ultimate-web-stack-dev` | Match the env whose backup PVC you want to read. |
| `metadata.name` | `mongo-restore-2026-08-22` | Job names must be unique within a namespace. |
| `env[ARCHIVE].value` | `/backup/future_gadget_lab_dev-20260821T030000Z.tar.gz` | Absolute path on the PVC. |
| `env[TARGET_DB].value` | `scratch_restore_2026_08_22` | A scratch DB by default — restore into a live DB only after stopping traffic. |
| `env[SOURCE_DB].value` | `future_gadget_lab_dev` | The DB name *inside* the archive (matches `MONGO_DB` in the backup CronJob for this env: prod `future_gadget_lab`, dev `future_gadget_lab_dev`, test `future_gadget_lab_test`). Defaults to `TARGET_DB` if unset. |
| `env[FORCE].value` | `0` | `1` to overwrite an existing non-empty target DB. **Destructive** — only set after confirming the target is expendable. |

Apply:

```bash
kubectl apply -f restore-2026-08-22.yaml
kubectl logs -f job/mongo-restore-2026-08-22 -n <env-namespace>
```

The script exits non-zero on any problem with a `RESTORE FAILED archive=… reason=…` log line naming the archive and the cause. On success it logs `RESTORE SUCCEEDED archive=… target_db=… collections=N`.

**Check the result** — verify the target DB now has the expected collections:

```bash
kubectl run -n <env-namespace> mongosh-verify --rm -it --restart=Never --image=mongo:8.0 \
  --command -- mongosh "mongodb://mongodb:27017/$(yq '.env[1].value' restore-2026-08-22.yaml)" \
  --eval "db.getCollectionNames()"
```

(That one's a mouthful; the practical version is `kubectl exec -it <some-pod> -- mongosh ... --eval ...` against any pod with `mongo:8.0` in the namespace.)

When the restore is verified, delete the one-shot Job:

```bash
kubectl delete job -n <env-namespace> mongo-restore-2026-08-22
```

**Safety notes:**

- The script **refuses** to overwrite a non-empty target DB by default. You must set `FORCE=1` to proceed against a target that already has collections — and `FORCE=1` adds `--drop` to `mongorestore`, which deletes the existing collections before restoring.
- Restoring into the live application DB (`future_gadget_lab` in prod) while the web pods are serving traffic is a recipe for races between the restore and incoming writes. Either restore into a scratch DB and then rename/swap, OR stop the web Deployment first (scale to 0), restore, then scale back.
- The restore script redacts the password segment of `MONGO_URI` before logging (same as the backup script, closes issue #104) — `kubectl logs` on a restore Job is safe to share for debugging.

## Reference

- Parent project: [ultimate-web-stack](https://github.com/kstrassheim/ultimate-web-stack)

## State encryption

State lives in the `k8s-ultimate-web-stack` blob container of the `mytofustates`
storage account and is **encrypted by OpenTofu itself**, on top of Azure's
storage encryption. A fresh AES-GCM data key is generated per run and wrapped
with the RSA key `k8s-ultimate-web-stack` in the `kv-mytofustates` Key Vault, so
key material never leaves the vault.

- **HashiCorp Terraform cannot read this state.** Use `tofu`.
- The backend derives its own values — `container_name = var.app_name` and
  `key = "${var.env}.tfstate"` — via OpenTofu early evaluation, resolved at
  `tofu init` before state exists. That syntax is not parseable by Terraform.
- `deploy-k8s-ultimate-web-stack` holds `Key Vault Crypto User` scoped to that
  **single key object**, not to the vault, so it cannot decrypt another
  project's state.
- `tofu init -backend=false` and `tofu validate` never contact the vault, which
  is why the credential-free validate job in `ci.yml` still works.

Locally the key provider authenticates through your `az login` session. CI uses
GitHub OIDC, which needs `TF_VAR_use_oidc=true` plus `TF_VAR_arm_client_id` /
`TF_VAR_arm_tenant_id`. Those are separate from `ARM_USE_OIDC`, which configures
the backend and the azurerm provider — the key provider does not read `ARM_*` at
all. The pipelines set both; if only one is set, that consumer falls back to the
Azure CLI credential and fails with *"Please specify only one of subscription
and tenant, not both"*.

The state blobs are named `dev.tfstate` / `test.tfstate` / `prod.tfstate`. The
older `app-reg-*.tfstate` blobs are the pre-migration copies and are no longer
read.
