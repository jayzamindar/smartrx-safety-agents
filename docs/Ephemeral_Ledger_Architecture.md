# Ephemeral Ledger Architecture Guide (`docs/Ephemeral_Ledger_Architecture.md`)

## 1. Overview

`smartrx-safety-agents` persists two complementary audit artifacts:

1. **SQLite WAL Hash-Chained Ledger (`smartrx_ledger.db`):** Stores tamper-evident, SHA-256 hash-chained `audit_events` rows with idempotency deduplication (`plan_id`, `idempotency_key`), `PRAGMA journal_mode=WAL;`, `PRAGMA busy_timeout=5000;`, and per-operation `filelock.FileLock` write isolation (`src/smartrx_safety_agents/persistence/ledger.py`).
2. **Rotating Daily JSONL Audit Logs (`audit-YYYY-MM-DD.jsonl`):** Emitted by `JsonlAuditExporter` with a 50 MB per-file rotation ceiling and automated retention pruning (`AUDIT_LOG_MAX_RETENTION_DAYS=30`, `AUDIT_LOG_MAX_SIZE_MB=500`).

---

## 2. Ephemeral Filesystem Risks in Serverless Runtimes

Serverless container platforms (AWS ECS Fargate, Azure Container Apps, Google Cloud Run) provision an ephemeral writable root/overlay or `/tmp` filesystem per revision instance:

- **Scale-to-Zero & Eviction Loss:** When a container scales to zero or is replaced during a rolling deploy, any SQLite database stored on `/tmp` or container overlay storage is permanently discarded, breaking hash-chain continuity across restarts.
- **Multi-Replica Split-Brain:** If two serverless replicas write to separate local `/tmp/smartrx_ledger.db` files, each replica maintains an independent genesis chain, preventing global idempotency deduplication.

---

## 3. Why SQLite WAL Requires POSIX Storage (Not Object Mounts)

SQLite in Write-Ahead Logging (`WAL`) mode creates three coordinated files:
- `smartrx_ledger.db` (main database)
- `smartrx_ledger.db-wal` (append-only write-ahead log)
- `smartrx_ledger.db-shm` (memory-mapped shared-memory index)

`smartrx_ledger.db-shm` and `filelock.FileLock` rely on **POSIX advisory byte-range locking (`fcntl`) and coherent `mmap` page semantics**:

| Storage Backend | POSIX `fcntl` + `mmap` | Recommended for `smartrx_ledger.db`? |
|---|---|---|
| **Kubernetes `ReadWriteOnce` PVC** (EBS / Azure Disk / PD) | Full POSIX | **Yes** (single-writer pod / StatefulSet) |
| **AWS EFS / Azure Files (NFSv4.1)** | POSIX locking supported | **Yes** (with `FileLock` write serialization) |
| **Object Storage FUSE** (`s3fs`, `gcsfuse`, `blobfuse`) | Partial / non-coherent `mmap` | **No — strictly prohibited for SQLite WAL** |
| **Ephemeral `/tmp` / `emptyDir`** | Full POSIX (local only) | **Dev / Stateless Dry-Run Only** |

> **Operational Rule:** Never mount an object-storage bucket via FUSE as `SMARTRX_DB_PATH`. Always back `/app/data` with a POSIX volume (`ReadWriteOnce` PVC or NFSv4.1/EFS) when durable hash-chain continuity is required.

---

## 4. Durable Object-Storage Sync via JSONL Export

To bridge ephemeral container compute with immutable long-term compliance archiving (HIPAA / SIEM):

1. Configure `AUDIT_LOG_DIR=/app/audit_logs` on a bounded `emptyDir` (`512Mi`) or local volume.
2. `JsonlAuditExporter` writes zero-PHI, UTF-8 JSONL lines to `audit-YYYY-MM-DD.jsonl`, rotating at 50 MB and pruning files older than 30 days or above 500 MB total.
3. Run a lightweight log-shipper sidecar (Fluent Bit, Vector, or CloudWatch/Blob agent) watching `/app/audit_logs/audit-*.jsonl` to stream finalized records to **Amazon S3 (Object Lock)**, **Azure Blob Immutable Storage**, or **Google Cloud Storage** without touching SQLite's WAL locks.
4. On graceful `SIGTERM`/`SIGINT` shutdown, `api/server.py` drains active `/sse` streams and executes `PRAGMA wal_checkpoint(TRUNCATE);` so all committed rows are flushed cleanly into `smartrx_ledger.db` before container termination.
