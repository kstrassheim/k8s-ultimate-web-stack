# k8s-ultimate-web-stack

A Kubernetes deployment implementation of the **ultimate-web-stack** project — the same FastAPI backend and React frontend you know from [ultimate-web-stack](https://github.com/kstrassheim/ultimate-web-stack), now running on a self-hosted k8s cluster managed via ArgoCD and GitOps.

This is not a reimplementation of the application logic — the app code is identical to ultimate-web-stack. The goal is to port the infrastructure from Azure App Service + CosmosDB + App Insights to a self-hosted Kubernetes environment with MongoDB, OpenTelemetry, and ArgoCD.

## What changed from ultimate-web-stack

| Concern | ultimate-web-stack | k8s-ultimate-web-stack |
|---------|-------------------|------------------------|
| **Runtime platform** | Azure App Service (F1 Free Plan) | Self-hosted k8s (Orange Pi, OpenClaw) |
| **Database** | Azure CosmosDB (serverless NoSQL) | MongoDB StatefulSet in-cluster |
| **Auth** | Entra ID + Terraform-provisioned App Reg | Same Entra ID App Reg; Terraform still handles App Reg creation |
| **Observability** | Azure App Insights | OpenTelemetry (otel-collector, Prometheus/Grafana ready) |
| **Secrets** | None (managed identity, no keys) | Sealed Secrets (cryptographically sealed K8s Secrets) |
| **IaC** | Terraform provisions everything | Terraform handles App Reg only; k8s manifests handle runtime infra |
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
- **Terraform** (for App Reg provisioning only)

### 1. Provision Entra ID App Reg

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars — set app_name, tenant_id, subscription_id
terraform init
terraform plan
terraform apply
```

This creates the App Registration in Entra ID. The app code (backend/frontend) reads auth config from `terraform.output.json` or environment variables — same as ultimate-web-stack.

### 2. Build and push container images

Images live in the in-cluster registry. CI handles this automatically — the
`.github/workflows/build-images.yml` workflow runs on the in-cluster
self-hosted runner (`arc-runner-scale-k8s-ultimate-web-stack`, docker-in-docker)
and builds + pushes the `web` image on every push. The runner already trusts
the registry CA and gets credentials from the `registry-creds` secret, so no
setup is needed.

`main` is the dev channel; releases are **git tags**. test and prod both track
the latest semver tag (ArgoCD `targetRevision: "*"`), so one tag promotes through
both — test immediately, prod after approval:

| Trigger | Image tag(s) | Environment | Gate |
|---------|--------------|-------------|------|
| push `main`       | `:dev` (+ `:sha-<sha>`) | `ultimate-web-stack-dev`  | — |
| create tag `vX.Y.Z` | `:vX.Y.Z-test` (immutable) | `ultimate-web-stack-test` | none — rolls at once |
| create tag `vX.Y.Z` | `:vX.Y.Z-prod` (immutable) | `ultimate-web-stack`      | GitHub `prod` environment approval |

dev uses a mutable `:dev` tag (a rebuild needs a pod restart to pull). test/prod
use **immutable** per-tag tags pinned into the tagged commit's overlay, so ArgoCD
rolls each new build automatically — prod once the gated `:vX.Y.Z-prod` image is
published. Images come from `mainpi.local:5000` (nodes trust this host via the
cluster `registries.yaml`, so no pull secret is needed).

**Cutting a release:**

```bash
scripts/release.sh 0.9.0
```

This pins `web:v0.9.0-test` / `web:v0.9.0-prod` into the test/prod overlays of a
release commit, creates tag `v0.9.0`, and pushes the tag (main is left untouched
— the tag is the source of truth for test/prod). CI then builds the test image
and rolls test; the prod image builds and rolls only after the `prod` GitHub
environment is approved. Until then the prod app keeps serving the previous
image (the rolling update waits on the unbuilt image — no downtime).

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
push to main          → dev rolls out
scripts/release.sh X  → tag vX rolls out test immediately, prod after the
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

## Reference

- Parent project: [ultimate-web-stack](https://github.com/kstrassheim/ultimate-web-stack)