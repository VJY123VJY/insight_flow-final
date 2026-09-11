from fastapi import APIRouter, Depends, Request, HTTPException, status
from typing import Dict, Any
import time

from app.core.security import SovereignAuth
from app.schemas.dataset import DatasetMetadata
from app.services.mdu import MDUService
from app.services.observability import ObservabilityService

router = APIRouter()

# Simple In-Memory Replay/Rate-Limit store for demo
# In production, this would use Redis/SQL
REPLAY_CACHE = {}
RATE_LIMITS = {}

@router.post("/enforce")
async def enforce(request: Request, payload: Dict[str, Any] = Depends(SovereignAuth.verify_token)):
    start_time = time.time()
    client_ip = request.client.host
    resource = request.query_params.get("resource", "default")
    dataset_id = request.query_params.get("dataset_id")
    request_body: Dict[str, Any] = {}

    if not dataset_id:
        try:
            request_body = await request.json()
        except Exception:
            request_body = {}
        dataset_id = request_body.get("dataset_id")

    if not dataset_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Missing dataset_id for MDU validation. "
                "Provide ?dataset_id=... or JSON body {\"dataset_id\": \"...\"}."
            )
        )

    obs_metadata = {
        "start_time": start_time,
        "sub": payload.get("sub"),
        "resource": resource,
        "method": request.method,
        "path": request.url.path,
        "ip": client_ip,
        "dataset_id": dataset_id,
    }

    try:
        dataset_meta: DatasetMetadata = await MDUService.fetch_dataset_metadata(dataset_id)
        obs_metadata.update({
            "dataset_trust_level": dataset_meta.trust_level,
            "dataset_schema": dataset_meta.schema_name,
            "dataset_compatibility": dataset_meta.compatibility,
            "dataset_provenance": dataset_meta.provenance,
        })

        await ObservabilityService.log_dataset_validation(dataset_meta, "VALIDATED", obs_metadata)

        # 1. Replay Protection (Mock)
        jti = payload.get("jti")
        if jti:
            if jti in REPLAY_CACHE:
                reason = "Replay attack detected (duplicate JTI)"
                await ObservabilityService.emit_insightflow_event("DENY", reason, obs_metadata)
                await ObservabilityService.log_to_bucket("DENY", reason, obs_metadata, payload)
                raise HTTPException(status_code=403, detail=reason)
            REPLAY_CACHE[jti] = time.time()

        # 2. Rate Limiting (Mock)
        now = time.time()
        user_key = f"{payload.get('sub')}:{client_ip}"
        history = RATE_LIMITS.get(user_key, [])
        history = [t for t in history if now - t < 60]  # 1 minute window

        if len(history) >= 5:  # Small limit for demo visibility
            reason = "Rate limit breached (max 5 req/min)"
            await ObservabilityService.emit_insightflow_event("DENY", reason, obs_metadata)
            await ObservabilityService.log_to_bucket("DENY", reason, obs_metadata, payload)
            raise HTTPException(status_code=429, detail=reason)

        history.append(now)
        RATE_LIMITS[user_key] = history

        # 3. Final Decision
        decision = "ALLOW"
        reason = "Valid identity, dataset metadata validated, and policy compliance"

        # Telemetry & Audit
        await ObservabilityService.emit_insightflow_event(decision, reason, obs_metadata)
        await ObservabilityService.log_to_bucket(decision, reason, obs_metadata, payload)

        return {
            "status": decision,
            "decision_id": str(time.time()),
            "principal": payload.get("sub"),
            "resource": resource,
            "dataset_id": dataset_meta.dataset_id,
            "dataset_trust_level": dataset_meta.trust_level,
            "dataset_schema": dataset_meta.schema_name,
            "dataset_compatibility": dataset_meta.compatibility,
            "dataset_provenance": dataset_meta.provenance,
        }

    except HTTPException:
        raise
    except Exception as e:
        # Fail-Closed logic for unexpected errors
        reason = f"Internal processing error: {str(e)}"
        await ObservabilityService.emit_insightflow_event("DENY", reason, obs_metadata)
        raise HTTPException(status_code=500, detail="Internal security error (Fail-Closed)")
