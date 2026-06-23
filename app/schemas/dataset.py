from pydantic import BaseModel, Field
from typing import Optional


class DatasetMetadata(BaseModel):
    dataset_id: str = Field(..., description="Canonical dataset identifier")
    trust_level: str = Field(..., description="Dataset trust level (TRUSTED, VERIFIED, PROVISIONAL)")
    schema_name: str = Field(..., alias="schema", description="Dataset schema or compatibility profile")
    compatibility: Optional[str] = Field(None, description="Dataset compatibility hint")
    provenance: Optional[str] = Field(None, description="Dataset provenance or lineage metadata")

    model_config = {
        "extra": "ignore",
        "populate_by_name": True,
    }
