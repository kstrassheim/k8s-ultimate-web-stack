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
| **Container registry** | Azure Container Apps registry | Self-hosted `mainpi.local:30500` registry on Orange Pi |

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     Self-hosted k8s cluster                  │
│                                                              │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐   │
│  │ MongoDB     │  │  Backend    │  │   Frontend      │   │
│  │ StatefulSet│  │  (FastAPI)  │  │   (React/Vite)  │   │
│  │  replSet   │  │  ×2 pods    │  │   ×2 pods        │   │
│  └─────────────┘  └──────┬──────┘  └────────┬────────┘   │
│                           │                    │              │
│                    ┌──────┴──────┐            │              │
│                    │  backend   │            │              │
│                    │  Service   │            │              │
│                    └──────┬──────┘            │              │
│                           │                    │              │
│                    ┌──────┴──────┐     ┌───────┴────────┐   │
│                    │  frontend  │     │  ingress-nginx  │   │
│                    │  Service   │     │  (nginx-ingress│   │
│                    └────────────┘     └───────┬────────┘   │
└───────────────────────────────────────────────┼──────────────┘
                                                │
                                    ┌───────────┴───────────┐
                                    │   ArgoCD (in-cluster) │
                                    │   app-of-apps        │
                                    └─────────────────────┘

GitOps flow:
  git push → ArgoCD detects drift → syncs k8s manifests → cluster updated
```

## Project structure

```
k8s-ultimate-web-stack/
├── backend/              # FastAPI app (identical to ultimate-web-stack)
├── frontend/             # React app (identical to ultimate-web-stack)
├── k8s/                  # Kubernetes manifests
│   ├── backend/          # backend Deployment + Service
│   ├── frontend/         # frontend Deployment + Service
│   ├── mongodb/          # MongoDB StatefulSet
│   ├── common/           # namespaces
│   ├── environments/     # kustomize overlays (dev / test / prod)
│   └── patches/         # per-env env var patches
├── argocd/               # ArgoCD Application manifests (app-of-apps)
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
- **Container registry** at `mainpi.local:30500`
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

```bash
# Backend
cd backend
docker build -t mainpi.local:30500/future-gadget-dev/backend:latest .
docker push mainpi.local:30500/future-gadget-dev/backend:latest

# Frontend
cd frontend
docker build -t mainpi.local:30500/future-gadget-dev/frontend:latest .
docker push mainpi.local:30500/future-gadget-dev/frontend:latest
```

### 3. Apply k8s manifests directly (one-shot)

```bash
kubectl apply -f k8s/common/namespaces.yaml
kubectl apply -k k8s/environments/dev
```

### 4. Or use ArgoCD GitOps (recommended)

```bash
argocd app sync default/future-gadget-dev
```

ArgoCD watches the git repo and syncs automatically on push.

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

Environment-specific settings (MongoDB URI, MOCK mode, etc.) are set via `k8s/patches/<env>-backend-env.yaml` and `k8s/patches/<env>-frontend-env.yaml`.

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

## Secrets

No raw Secrets in git. Credentials are managed via the **Sealed Secrets** pattern from [k8s-openclaw](https://github.com/kstrassheim/k8s-openclaw):

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
- **Self-signed registry** (`mainpi.local:30500`) — push with `--insecure` flag for Docker/Podman

## Reference

- Parent project: [ultimate-web-stack](https://github.com/kstrassheim/ultimate-web-stack)
- Cluster management: [k8s-openclaw](https://github.com/kstrassheim/k8s-openclaw)