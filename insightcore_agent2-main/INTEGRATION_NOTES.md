# InsightBridge Integration Notes

## Sovereign Core Wiring
- **Consumed**:
    - **JWKS Endpoint**: `https://sovereign-core.bhiv.local/.well-known/jwks.json`
    - **Issuer (iss)**: `https://sovereign-core.bhiv.local`
    - **Audience (aud)**: `insight-bridge`
- **Identity Flow**:
    - Validates service identity by verifying RS256 signatures against Core public keys.
    - Extracts `sub` (principal) and `jti` (unique token ID) for decision logic.
- **Fail-Closed Strategy**:
    - If Core JWKS is unreachable, the system returns `503 Service Unavailable`.
    - Verification is blocked; no "bypass" mode exists for security integrity.

## Bucket Integration (Auditing)
- **Approved Surface**: `https://bucket.bhiv.local/audit`
- **Output Schema**:
    - `audit_id`: UUID
    - `timestamp`: Unix seconds
    - `action`: ENFORCE
    - `decision`: ALLOW/DENY
    - `identity`: Masked/Validated principal from JWT
- **Security**: No raw JWTs or private claims are ever written to Bucket.

## InsightFlow Integration (Telemetry)
- **Output Channel**: `https://insightflow.bhiv.local/events`
- **Event Structure**:
    - `decision`: ALLOW or DENY
    - `decision_id`: Correlated tracking ID
    - `latency_ms`: Processing time
    - `reason`: Machine-readable reason code
- **Visibility**: InsightFlow can observe allow/deny paths deterministically for downstream Karma tracking and observability.

## Downstream Consumers
- **Karma Tracker (Siddhesh)**: Consumes `decision` and `reason` from InsightFlow events for risk scoring.
- **InsightFlow (Ashmit)**: Primary consumer of the telemetry stream.
