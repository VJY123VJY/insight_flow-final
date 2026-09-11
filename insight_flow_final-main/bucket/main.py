import os
import logging
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException, status, Query
from fastapi.responses import JSONResponse

try:
    from bucket.models import (
        AuditEventCreate,
        AuditResponse,
        AuditListResponse,
        HealthResponse
    )
    from bucket.storage import AuditStorage
except ImportError:
    from models import (
        AuditEventCreate,
        AuditResponse,
        AuditListResponse,
        HealthResponse
    )
    from storage import AuditStorage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [BUCKET] %(message)s"
)
logger = logging.getLogger("bucket")

# Initialize persistent storage instance
storage = AuditStorage()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure database tables & indexes exist
    logger.info("Bucket microservice starting up...")
    await storage.init_db()
    yield
    # Shutdown
    logger.info("Bucket microservice shutting down...")


app = FastAPI(
    title="Bucket Service",
    description="Dedicated audit persistence microservice for InsightFlow",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health():
    """
    Health check endpoint.
    Reports healthy only when application and storage layer are verified usable.
    """
    is_healthy = await storage.check_health()
    if not is_healthy:
        logger.error("Health check failed: storage layer unreachable")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "service": "bucket",
                "detail": "Storage layer failure"
            }
        )
    return {
        "status": "healthy",
        "service": "bucket"
    }


@app.post("/audit", status_code=status.HTTP_201_CREATED, response_model=AuditResponse, tags=["Audit"])
async def create_audit(event: AuditEventCreate):
    """
    Receives and persists a structured audit event.
    Validates payload, assigns identifiers / timestamps if missing, and records to SQLite.
    """
    try:
        stored_record = await storage.store_event(event)
        logger.info(f"Persisted audit event: {stored_record['audit_id']} [Decision: {stored_record['decision']}]")
        return {
            "status": "success",
            "audit_id": stored_record["audit_id"],
            "message": "Audit event recorded successfully"
        }
    except Exception as exc:
        logger.error(f"Failed to persist audit event: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Storage failure while persisting audit event: {str(exc)}"
        )


@app.get("/audit", response_model=AuditListResponse, tags=["Audit"])
async def list_audits(
    limit: int = Query(default=100, ge=1, le=1000, description="Max records to return"),
    offset: int = Query(default=0, ge=0, description="Pagination offset")
):
    """
    Retrieves stored audit records sorted in reverse-chronological order.
    """
    try:
        events = await storage.get_events(limit=limit, offset=offset)
        total = await storage.count_events()
        return {
            "total": total,
            "events": events
        }
    except Exception as exc:
        logger.error(f"Failed to list audit events: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Storage failure while retrieving audit events"
        )


@app.get("/audit/{audit_id}", tags=["Audit"])
async def get_audit(audit_id: str):
    """
    Retrieves a specific audit event by its audit_id.
    """
    try:
        event = await storage.get_event_by_id(audit_id)
        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Audit event '{audit_id}' not found"
            )
        return event
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to fetch audit event {audit_id}: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Storage failure while retrieving audit event"
        )


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 9000))
    uvicorn.run("bucket.main:app", host=host, port=port, reload=True)
