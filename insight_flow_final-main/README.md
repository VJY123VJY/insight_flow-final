# InsightFlow - Sovereign Enforcement Agent & Local Bucket Service

InsightFlow is an enforcement agent within the BHIV architecture that performs policy enforcement, token validation, and dataset trust level verification (via the Metadata Discovery Unit - MDU) before allowing or denying actions.

---

## Bucket Integration

### 1. What Bucket Does
The **Bucket** microservice is an independent, dedicated audit persistence service. It provides:
- A standardized REST API to receive and validate audit events generated during decision flows.
- Automatic server-side metadata generation (`audit_id` UUID, timestamps, UTC recorded-at).
- Persistent storage using SQLite (`aiosqlite`) ensuring audit events are written to disk and survive container restarts.
- Query capabilities to retrieve all audit logs or inspect specific audit records by ID.

### 2. Why InsightFlow Needs It
InsightFlow enforces access control and dataset safety. For strict governance, compliance, and tamper-resistant auditability, every enforcement evaluation (`ALLOW` or `DENY`) must produce an immutable audit trail.
By delegating audit storage to the independent Bucket service:
- Audit records are decoupled from the lifecycle of the enforcement agent.
- Audit storage failures or network hiccups do **not** unnecessarily crash the enforcement pipeline (fail-safe audit logging).
- Audit logs can be independently inspected, queried, and verified by external auditors, security tooling, or downstream services like Karma Tracker.

### 3. Bucket API Endpoints

| Method | Endpoint | Description | Expected Response |
|--------|----------|-------------|-------------------|
| `GET` | `/health` | Health check verifying app and storage layer readiness | `200 OK`: `{"status": "healthy", "service": "bucket"}` (or `503` if storage unreachable) |
| `POST` | `/audit` | Validates, timestamps, and persists an audit event | `201 Created`: `{"status": "success", "audit_id": "<uuid>", "message": "Audit event recorded successfully"}` |
| `GET` | `/audit` | Lists stored audit events in reverse-chronological order | `200 OK`: `{"total": <count>, "events": [...]}` |
| `GET` | `/audit/{audit_id}` | Retrieves a specific audit record by ID | `200 OK`: `{...}` or `404 Not Found` |

### 4. Audit Event Schema
The Bucket service accepts and preserves the full InsightFlow audit schema:
```json
{
  "audit_id": "c71a39f6-6c1f-4ff0-bce8-d2e46cfc3c43",
  "timestamp": 1718282891.123,
  "action": "ENFORCE",
  "decision": "ALLOW",
  "reason": "Valid identity, dataset metadata validated, and policy compliance",
  "identity": "admin",
  "context": {
    "method": "POST",
    "path": "/enforce",
    "ip": "127.0.0.1",
    "resource": "default",
    "dataset_id": "BHIV-DS-GOVERNANCE-MUTATION-LOGS-001"
  },
  "request_metadata": {},
  "runtime_metadata": {},
  "created_at": "2026-09-07T11:50:00.000000+00:00"
}
```

### 5. Local Bucket URL & Network Architecture
- **Local Host URL**: `http://localhost:9000`
- **Docker Compose Internal URL**: `http://bucket:9000`
- **InsightFlow Audit Target**: `http://bucket:9000/audit` (inside Docker) or `http://localhost:9000/audit` (local host).

### 6. Docker Architecture & Persistence
The multi-container stack configured in `docker-compose.yml` comprises:
1. `insightflow` (FastAPI, port `8000`): Policy enforcement and observability client.
2. `mock_mdu` (FastAPI, port `8001`): Metadata Discovery Unit mock for dataset trust checks.
3. `bucket` (FastAPI, port `9000`): Audit persistence microservice.

**Storage Persistence**:
Bucket persists data to `/app/data/bucket.db` backed by a named Docker volume `bucket_data`. Even when containers are stopped, removed, or rebuilt, audit history remains intact.

### 7. Environment Variables

| Variable | Default (Local) | Default (Docker) | Purpose |
|----------|-----------------|------------------|---------|
| `BUCKET_ENDPOINT` | `http://localhost:9000/audit` | `http://bucket:9000/audit` | Audit dispatch endpoint used by `ObservabilityService` |
| `BUCKET_TIMEOUT` | `3` | `3` | Connection/read timeout in seconds for Bucket calls |
| `BUCKET_AUTH_TOKEN` | `None` | `None` | Optional Bearer token for authenticated audit writes |
| `BUCKET_DB_PATH` | `data/bucket.db` | `/app/data/bucket.db` | Path to SQLite audit database |
| `HOST` | `0.0.0.0` | `0.0.0.0` | Listening host for Bucket service |
| `PORT` | `9000` | `9000` | Listening port for Bucket service |

---

## Getting Started

### Local Development (Python)

#### 1. Install Dependencies
```bash
pip install -r requirements.txt
pip install -r bucket/requirements.txt
```

#### 2. Start Services
Open 3 terminals:

```bash
# Terminal 1: Start Bucket
python -m uvicorn bucket.main:app --host 0.0.0.0 --port 9000

# Terminal 2: Start Mock MDU
python mock_mdu.py

# Terminal 3: Start InsightFlow
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

### Containerized Deployment (Docker Compose)

```bash
# Build and start all 3 services
docker compose up --build -d

# Verify all containers are running
docker compose ps
```

---

## Verification & Testing

### 1. Run Automated Test Suite
Run the comprehensive 16-test suite covering Bucket endpoints, validation, SQLite persistence, and InsightFlow integration:

```bash
# Run all tests
python -m pytest tests/ -v

# Run Bucket unit tests specifically
python -m pytest tests/test_bucket.py -v

# Run InsightFlow -> Bucket integration tests
python -m pytest tests/test_bucket_integration.py -v

# Run InsightFlow enforcement policy tests
python -m pytest tests/test_demo.py -v
```

### 2. End-to-End Verification with `curl`

#### Step A: Verify Bucket Health
```bash
curl http://localhost:9000/health
```
**Response**:
```json
{
  "status": "healthy",
  "service": "bucket"
}
```

#### Step B: Obtain Authentication Token
```bash
TOKEN=$(curl -s -X POST "http://localhost:8000/login?username=admin&password=admin123" | jq -r .access_token)
echo $TOKEN
```

#### Step C: Execute InsightFlow Enforcement Request
```bash
curl -X POST "http://localhost:8000/enforce?dataset_id=BHIV-DS-GOVERNANCE-MUTATION-LOGS-001" \
  -H "Authorization: Bearer $TOKEN"
```
**Response** (`200 OK`):
```json
{
  "status": "ALLOW",
  "decision_id": "1718282891.456",
  "principal": "admin",
  "resource": "default",
  "dataset_id": "BHIV-DS-GOVERNANCE-MUTATION-LOGS-001",
  "dataset_trust_level": "VERIFIED",
  "dataset_schema": "COMPATIBLE",
  "dataset_compatibility": "COMPATIBLE",
  "dataset_provenance": "BHIV-External"
}
```

#### Step D: Verify Audit Event in Bucket
```bash
curl http://localhost:9000/audit
```
**Response**:
```json
{
  "total": 1,
  "events": [
    {
      "audit_id": "038bf2fe-ff90-4828-b80c-c60bf803ba97",
      "timestamp": 1718282891.5,
      "action": "ENFORCE",
      "decision": "ALLOW",
      "reason": "Valid identity, dataset metadata validated, and policy compliance",
      "identity": "admin",
      "context": {
        "method": "POST",
        "path": "/enforce",
        "ip": "127.0.0.1",
        "resource": "default",
        "dataset_id": "BHIV-DS-GOVERNANCE-MUTATION-LOGS-001"
      },
      "created_at": "2026-09-07T06:20:00.000000+00:00"
    }
  ]
}
```

#### Step E: Fetch Specific Audit Event by ID
```bash
curl http://localhost:9000/audit/038bf2fe-ff90-4828-b80c-c60bf803ba97
```

---

## Limitations & Production Notes
- **Local Bucket Microservice**: This implementation provides a fully functioning, persistent microservice designed for sovereign local, CI/CD, and Docker Compose environments using SQLite storage.
- **External BHIV Production Bucket**: If connecting to a remote managed BHIV Bucket infrastructure in production, configure `BUCKET_ENDPOINT=https://bucket.bhiv.local/audit` (or the actual cloud URL) and provide `BUCKET_AUTH_TOKEN`. The HTTP payload and schema remain 100% compatible.
