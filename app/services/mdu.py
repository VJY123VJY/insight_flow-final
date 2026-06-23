import logging

import httpx
from fastapi import HTTPException, status

from app.core.config import settings
from app.schemas.dataset import DatasetMetadata

logger = logging.getLogger(__name__)


class MDUService:
    @staticmethod
    async def fetch_dataset_metadata(dataset_id: str) -> DatasetMetadata:
        if not dataset_id or not isinstance(dataset_id, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing or invalid dataset_id for MDU validation"
            )

        url = f"{settings.MDU_BASE_URL}/api/v1/datasets/canonical/{dataset_id}"
        logger.info(f"MDU request started for dataset_id={dataset_id}")

        headers = {}
        if settings.MDU_API_KEY:
            headers["X-API-Key"] = settings.MDU_API_KEY

        try:
            async with httpx.AsyncClient(timeout=settings.MDU_API_TIMEOUT) as client:
                response = await client.get(url, headers=headers)
        except Exception as exc:
            logger.error(f"Could not connect to MDU: {exc}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Metadata Discovery Unit unavailable"
            )

        if response.status_code == 404:
            logger.warning(f"MDU dataset not found: {dataset_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dataset {dataset_id} not registered in MDU"
            )

        if response.status_code != 200:
            logger.error(
                f"Unexpected MDU response for {dataset_id}: {response.status_code} {response.text}"
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Metadata Discovery Unit returned an unexpected response"
            )

        try:
            dataset = DatasetMetadata.parse_obj(response.json())
        except Exception as exc:
            logger.error(f"Failed to parse MDU payload for {dataset_id}: {exc}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Invalid dataset metadata payload from MDU"
            )

        if dataset.trust_level not in settings.MDU_ALLOW_TRUST_LEVELS:
            logger.warning(
                "MDU dataset rejected due to insufficient trust level",
                extra={
                    "dataset_id": dataset.dataset_id,
                    "trust_level": dataset.trust_level,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Dataset {dataset.dataset_id} trust level '{dataset.trust_level}' is not permitted. "
                    "Only TRUSTED or VERIFIED datasets may be processed."
                ),
            )

        logger.info(
            f"MDU dataset validated: {dataset.dataset_id} trust_level={dataset.trust_level} schema={dataset.schema}"
        )
        return dataset
