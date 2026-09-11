# InsightBridge Acceptance Checklist

## Sovereign Core Integration
- [x] InsightBridge consumes Core auth material without modifying it.
- [x] Enforcement remains deterministic and fail-closed.
- [x] Core touchpoints are clearly documented.
- [x] Degraded-mode signaling implemented (fail-closed when Core unavailable).

## Integration & Telemetry
- [x] Decisions and telemetry are visible to InsightFlow.
- [x] Audit logs are written only to approved Bucket surfaces (or mock sink).
- [x] No secrets, tokens, or private claims are logged.
- [x] Structured decision events (decision, decision_id, latency, reason) emitted.

## Demo Readiness
- [x] System survives dependency failures (fail-closed).
- [x] valid request flow verified.
- [x] invalid JWT flow verified.
- [x] replay attempt flow verified.
- [x] rate-limit breach flow verified.
- [x] Core unavailable (fail-closed) flow verified.
- [x] E2E demo flows observable via logs/metrics.
- [x] Recording/Demo script ready.
