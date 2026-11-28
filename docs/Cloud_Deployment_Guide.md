# Standard Enterprise Cloud Deployment Guide (`docs/Cloud_Deployment_Guide.md`)

**Project:** `smartrx-safety-agents`  
**Runtime:** `python:3.13-slim` | Non-root user `smartrx` (UID `10001`) | Port `8080` | Memory Ceiling `2048MB`  
**Related Artifacts:** [`Dockerfile`](../Dockerfile), [`docker-compose.prod.yml`](../docker-compose.prod.yml), [`deploy/smartrx-safety-agents-deploy.sh`](../deploy/smartrx-safety-agents-deploy.sh), [`docs/Ephemeral_Ledger_Architecture.md`](Ephemeral_Ledger_Architecture.md)

---

## 1. Deployment Architecture & Invariants

`smartrx-safety-agents` runs as a stateless-compute, stateful-ledger container on port `8080` exposing FastAPI REST/SSE (`/health`, `/v1/health`, `/api/v1/reconcile`, `/api/v1/reconcile/stream`, `/api/v1/adjudicate`, `/api/v1/audit/verify`) and MCP (`smartrx://`) transports.

| Requirement | Production Configuration |
|---|---|
| **Container User & FS** | Non-root `smartrx` (UID `10001`), `read_only: true` root filesystem, `/tmp` mounted `tmpfs` (`64m`, `noexec,nosuid`) |
| **Memory & Payload Caps** | `mem_limit: 2048m`, `MAX_PAYLOAD_SIZE_BYTES=10485760` (10MB HTTP 413 guard) |
| **Mandatory Secrets** | `MCP_API_KEY`, `PLAN_SIGNING_SECRET`, `SMARTRX_SAFETY_AGENTS_WEBHOOK_SECRET` ($\ge 16$ chars, non-default), `GEMINI_API_KEY` |
| **Persistent Volumes** | POSIX block storage at `/app/data` (`smartrx_ledger.db` SQLite WAL) and `/app/audit_logs` (daily JSONL rotation) |
| **Health Probes** | `GET /health` (or `/v1/health`) returning HTTP `200` with `wal_mode`, `chain_valid`, and `catalog_rules` |

---

## 2. Cloud Target Topologies

### 2.1 AWS ECS / Fargate (`deploy/aws-ecs-task-definition.json`)
- **Manifest:** [`deploy/aws-ecs-task-definition.json`](../deploy/aws-ecs-task-definition.json) (`cpu: 1024`, `memory: 2048`, `readonlyRootFilesystem: true`, `user: "10001:10001"`, port `8080`, EFS volumes at `/app/data` and `/app/audit_logs`).
- **Deploy CLI Steps:**
  ```bash
  aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com
  docker build -t <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/smartrx-safety-agents:v1.0.0 .
  docker push <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/smartrx-safety-agents:v1.0.0
  aws ecs register-task-definition --cli-input-json file://deploy/aws-ecs-task-definition.json
  aws ecs update-service --cluster smartrx-prod --service smartrx-safety-agents --task-definition smartrx-safety-agents --force-new-deployment
  ```
- **Least-Privilege IAM Execution & Task Roles:**
  ```json
  {
    "Version": "2012-10-17",
    "Statement": [
      {
        "Sid": "SecretsReadOnly",
        "Effect": "Allow",
        "Action": ["secretsmanager:GetSecretValue"],
        "Resource": ["arn:aws:secretsmanager:us-east-1:<ACCOUNT_ID>:secret:smartrx/*"]
      },
      {
        "Sid": "AuditArchiveSync",
        "Effect": "Allow",
        "Action": ["s3:PutObject", "s3:AbortMultipartUpload"],
        "Resource": ["arn:aws:s3:::smartrx-audit-archive-<ENV>/*"]
      }
    ]
  }
  ```

### 2.2 Microsoft Azure Container Apps (`deploy/azure-container-app.yaml`)
- **Manifest:** [`deploy/azure-container-app.yaml`](../deploy/azure-container-app.yaml) (`cpu: 1.0`, `memory: 2.0Gi`, User-Assigned Managed Identity, Key Vault secret references, Azure Files NFSv4.1 mounts, `minReplicas: 1`, `maxReplicas: 1`).
- **Deploy CLI Steps:**
  ```bash
  az acr login --name <ACR_NAME>
  docker build -t <ACR_NAME>.azurecr.io/smartrx-safety-agents:v1.0.0 .
  docker push <ACR_NAME>.azurecr.io/smartrx-safety-agents:v1.0.0
  az containerapp create -g <RG> -n smartrx-safety-agents --yaml deploy/azure-container-app.yaml
  ```

### 2.3 Google Cloud Run (`Dockerfile.serverless` & `deploy/serverless-container.yaml`)
- **Manifest & Image:** [`Dockerfile.serverless`](../Dockerfile.serverless) (dynamic `${PORT:-8080}`, UID `10001` `smartrx`) + [`deploy/serverless-container.yaml`](../deploy/serverless-container.yaml) (Knative gen2, `2048Mi`, Secret Manager `secretKeyRef`, Cloud Filestore PVC / GCS archive).
- **Deploy CLI Steps:**
  ```bash
  gcloud auth configure-docker us-central1-docker.pkg.dev
  docker build -f Dockerfile.serverless -t us-central1-docker.pkg.dev/<PROJECT_ID>/smartrx/smartrx-safety-agents:v1.0.0 .
  docker push us-central1-docker.pkg.dev/<PROJECT_ID>/smartrx/smartrx-safety-agents:v1.0.0
  gcloud run services replace deploy/serverless-container.yaml --region us-central1
  ```

### 2.4 Kubernetes (EKS / AKS / GKE)
- **Workload:** Deploy as a `StatefulSet` (`replicas: 1` per ledger shard) with `securityContext`:
  - `runAsNonRoot: true`, `runAsUser: 10001`, `runAsGroup: 10001`
  - `readOnlyRootFilesystem: true`, `allowPrivilegeEscalation: false`, `capabilities.drop: ["ALL"]`
- **Resources & Probes:**
  - `requests: { cpu: "500m", memory: "1024Mi" }`, `limits: { cpu: "1000m", memory: "2048Mi" }`
  - `readinessProbe` & `livenessProbe`: `httpGet: { path: /health, port: 8080 }`, `initialDelaySeconds: 10`, `periodSeconds: 15`
- **Volumes:** `PersistentVolumeClaim` (`ReadWriteOnce`, e.g., `gp3` / `managed-csi`) mounted at `/app/data` and `/app/audit_logs`, plus `emptyDir` (`medium: Memory`, `sizeLimit: 64Mi`) at `/tmp`.
- **Secrets:** Sync via External Secrets Operator (ESO) from AWS Secrets Manager / Azure Key Vault into a namespace-scoped `Secret` with RBAC restricted to `get` on that exact secret name.

---

## 3. GitHub Actions OIDC CI/CD Pipeline

1. **Pre-Deploy Quality Gate (`.github/workflows/ci.yml`):** Every push/PR runs Python 3.13/3.14 matrix with `ruff check`, `ruff format --check`, `mypy src/`, `pytest --cov-fail-under=90`, `pip-audit`, PEP 639 license audit, and scoped secret scanning.
2. **Keyless OIDC Authentication:** Configure `permissions: { id-token: write, contents: read }` in release workflows and use `aws-actions/configure-aws-credentials@v4` (or `azure/login@v2` with federated credentials) to assume a scoped deploy role without storing long-lived cloud access keys in GitHub Secrets.
3. **Immutable Image Build & Push:** Build from [`Dockerfile`](../Dockerfile), tag with `${{ github.sha }}` (never `:latest` alone in production), and push to ECR / ACR / GHCR.

---

## 4. Blue/Green Deployment & Rollback Runbook

### Pre-Cutover Checklist
1. Verify `ENVIRONMENT=production` and `REQUIRE_AUTH=true` are set in target environment.
2. Confirm `/app/data` and `/app/audit_logs` PVCs/volumes are backed up or snapshotted before schema migrations.
3. Deploy Green revision and verify `GET /health` returns HTTP `200` (`{"status":"ok","wal_mode":true,"chain_valid":true,"catalog_rules":4}`).

### Immediate Rollback Procedure
1. **Traffic Shift:** Repoint load balancer / Ingress / ECS target group weight from Green back to the prior Blue task/revision.
2. **Graceful Drain:** Send `SIGTERM` to Green containers; `FastAPI` lifespan handler sets active SSE `stop_event`s and executes `audit_ledger.checkpoint("TRUNCATE")` before exit.
3. **Ledger Integrity Verification:** Run `smartrx-safety-agents verify-audit` (or `GET /api/v1/audit/verify`) against the Blue volume to confirm `chain_valid: true` and zero uncheckpointed WAL drift.
4. **Incident Capture:** Export `/app/audit_logs/audit-YYYY-MM-DD.jsonl` and OpenTelemetry traces for post-mortem review.
