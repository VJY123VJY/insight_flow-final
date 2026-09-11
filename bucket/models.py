from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, Union, List


class AuditEventCreate(BaseModel):
    """
    Schema for incoming audit event payloads.
    Supports existing InsightFlow fields as well as standard audit metadata.
    """
    audit_id: Optional[str] = Field(default=None, description="Unique audit event identifier (generated if omitted)")
    timestamp: Optional[Union[float, str]] = Field(default=None, description="Timestamp of event occurrence")
    action: str = Field(default="ENFORCE", description="Audited action name")
    decision: str = Field(..., min_length=1, description="Decision result, e.g., ALLOW or DENY")
    reason: Optional[str] = Field(default=None, description="Human/machine readable reason for decision")
    identity: Optional[str] = Field(default=None, description="Subject or principal identifier")
    context: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Request context (method, path, ip, etc.)")
    request_metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional request metadata")
    runtime_metadata: Optional[Dict[str, Any]] = Field(default=None, description="Runtime execution metadata")

    model_config = {
        "extra": "allow",
        "populate_by_name": True
    }


class AuditResponse(BaseModel):
    status: str = "success"
    audit_id: str
    message: str = "Audit event recorded successfully"


class AuditListResponse(BaseModel):
    total: int
    events: List[Dict[str, Any]]


class HealthResponse(BaseModel):
    status: str = "healthy"
    service: str = "bucket"
