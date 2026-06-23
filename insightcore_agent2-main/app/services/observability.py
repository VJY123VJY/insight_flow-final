import httpx
import time
import uuid
import json
import logging
from typing import Any, Dict
from app.core.config import settings
from app.schemas.dataset import DatasetMetadata

logger = logging.getLogger(__name__)

class ObservabilityService:
    @staticmethod
    async def emit_insightflow_event(decision: str, reason: str, metadata: Dict[str, Any]):
        """
        Emits structured decision events consumable by InsightFlow.
        Fields: decision, decision_id, latency, reason, timestamp
        """
        event_id = str(uuid.uuid4())
        start_time = metadata.get("start_time", time.time())
        latency = (time.time() - start_time) * 1000  # ms
        
        payload = {
            "decision": decision,
            "decision_id": event_id,
            "latency_ms": round(latency, 2),
            "reason": reason,
            "timestamp": time.time(),
            "subject": metadata.get("sub", "unknown"),
            "resource": metadata.get("resource", "unknown")
        }
        
        # LOGGING (No secrets, no tokens)
        logger.info(f"InsightFlow Event: {json.dumps(payload)}")
        
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                # In mock/demo environment, this might be a no-op or log-only
                await client.post(settings.INSIGHTFLOW_ENDPOINT, json=payload)
        except Exception as e:
            logger.warning(f"Could not reach InsightFlow: {e}")

    @staticmethod
    async def log_dataset_validation(dataset_meta: DatasetMetadata, decision: str, metadata: Dict[str, Any]):
        """
        Logs metadata validation decisions for MDU dataset checks.
        """
        validation_id = str(uuid.uuid4())
        event = {
            "validation_id": validation_id,
            "dataset_id": dataset_meta.dataset_id,
            "trust_level": dataset_meta.trust_level,
            "schema": dataset_meta.schema_name,
            "compatibility": dataset_meta.compatibility,
            "provenance": dataset_meta.provenance,
            "decision": decision,
            "timestamp": time.time(),
            "subject": metadata.get("sub", "unknown"),
            "resource": metadata.get("resource", "unknown"),
        }

        logger.info(f"MDU Validation Event: {json.dumps(event)}")

    @staticmethod
    async def log_to_bucket(decision: str, reason: str, request_data: Dict[str, Any], payload: Dict[str, Any]):
        """
        Writes telemetry and audit events to approved Bucket interface.
        Ensures no raw JWTs or secrets are written.
        """
        audit_entry = {
            "audit_id": str(uuid.uuid4()),
            "timestamp": time.time(),
            "action": "ENFORCE",
            "decision": decision,
            "reason": reason,
            "identity": payload.get("sub"), # Claim from validated JWT
            "context": {
                "method": request_data.get("method"),
                "path": request_data.get("path"),
                "ip": request_data.get("ip")
            }
        }
        
        # DEBUG LOG (Masked)
        logger.info(f"Bucket Audit Entry Created: {audit_entry['audit_id']}")
        
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                # Real-world integration with Bucket
                await client.post(settings.BUCKET_ENDPOINT, json=audit_entry)
        except Exception as e:
            # Audit is critical. If Bucket is down, we log locally but alert.
            logger.error(f"CRITICAL: Failed to write to Bucket: {e}. Entry: {json.dumps(audit_entry)}")

    @staticmethod
    def cleanup_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Removes sensitive claims before logging/monitoring."""
        secret_keys = {"token", "secret", "password", "private_key", "jti"}
        return {k: v for k, v in payload.items() if k.lower() not in secret_keys}
