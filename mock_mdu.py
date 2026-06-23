"""
Mock MDU Server for Local Testing
==================================
This server simulates the Metadata Discovery Unit (MDU) for local development and testing.
Use this when you don't have the actual MDU running on your system.

Run this server with:
    python mock_mdu.py

This starts a mock MDU API on http://localhost:8001/api/v1
"""

from fastapi import FastAPI, HTTPException, Header, status
import uvicorn
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [MDU] %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Mock MDU Server", version="1.0.0")

# Mock API Key
VALID_API_KEY = "test-api-key-12345"

# Mock datasets registry
DATASETS = {
    "BHIV-DS-REPLAY-SEMANTIC-EVENTS-001": {
        "dataset_id": "BHIV-DS-REPLAY-SEMANTIC-EVENTS-001",
        "trust_level": "TRUSTED",
        "schema": "NATIVE",
        "compatibility": "NATIVE",
        "provenance": "BHIV-Internal"
    },
    "BHIV-DS-GOVERNANCE-MUTATION-LOGS-001": {
        "dataset_id": "BHIV-DS-GOVERNANCE-MUTATION-LOGS-001",
        "trust_level": "VERIFIED",
        "schema": "COMPATIBLE",
        "compatibility": "COMPATIBLE",
        "provenance": "BHIV-External"
    },
    "BHIV-DS-RECOVERY-ROLLBACK-SNAPSHOTS-001": {
        "dataset_id": "BHIV-DS-RECOVERY-ROLLBACK-SNAPSHOTS-001",
        "trust_level": "PROVISIONAL",
        "schema": "ADAPTABLE",
        "compatibility": "ADAPTABLE",
        "provenance": "Community"
    },
    "BHIV-DS-GOVERNANCE-CONTRADICTION-AUDITS-001": {
        "dataset_id": "BHIV-DS-GOVERNANCE-CONTRADICTION-AUDITS-001",
        "trust_level": "TRUSTED",
        "schema": "COMPATIBLE",
        "compatibility": "COMPATIBLE",
        "provenance": "BHIV-Internal"
    },
    "BHIV-DS-LINEAGE-CHAIN-001": {
        "dataset_id": "BHIV-DS-LINEAGE-CHAIN-001",
        "trust_level": "VERIFIED",
        "schema": "NATIVE",
        "compatibility": "NATIVE",
        "provenance": "BHIV-External"
    },
    "BHIV-DS-TRUST-PROPAGATION-001": {
        "dataset_id": "BHIV-DS-TRUST-PROPAGATION-001",
        "trust_level": "PROVISIONAL",
        "schema": "ADAPTABLE",
        "compatibility": "ADAPTABLE",
        "provenance": "Community"
    }
}

@app.get("/api/v1/datasets/canonical/{dataset_id}")
async def get_dataset_metadata(
    dataset_id: str,
    x_api_key: str = Header(None, alias="X-API-Key")
):
    """
    Fetch dataset metadata by dataset_id.
    
    Requires X-API-Key header for authentication.
    """
    # Validate API key
    if not x_api_key or x_api_key != VALID_API_KEY:
        logger.warning(f"Unauthorized request for dataset {dataset_id}: invalid API key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key header"
        )
    
    # Check if dataset exists
    if dataset_id not in DATASETS:
        logger.warning(f"Dataset not found: {dataset_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset {dataset_id} not registered in MDU"
        )
    
    dataset = DATASETS[dataset_id]
    logger.info(
        f"Dataset retrieved: {dataset_id} (trust_level={dataset['trust_level']}, "
        f"schema={dataset['schema']})"
    )
    
    return dataset

@app.get("/api/v1/datasets")
async def list_datasets(x_api_key: str = Header(None, alias="X-API-Key")):
    """List all registered datasets."""
    if not x_api_key or x_api_key != VALID_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key header"
        )
    
    logger.info(f"All datasets listed ({len(DATASETS)} total)")
    return {
        "total": len(DATASETS),
        "datasets": list(DATASETS.values())
    }

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "Mock MDU"}

if __name__ == "__main__":
    logger.info("Starting Mock MDU Server on http://localhost:8001")
    logger.info(f"API Key: {VALID_API_KEY}")
    logger.info(f"Registered datasets: {len(DATASETS)}")
    uvicorn.run(app, host="0.0.0.0", port=8001)
