from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional, List

class Settings(BaseSettings):
    # App Settings
    APP_NAME: str = "InsightBridge"
    DEBUG: bool = False
    
    # Sovereign Core Settings
    CORE_ISSUER: str = Field(default="https://sovereign-core.bhiv.local", description="Issuer for Core JWTs")
    CORE_AUDIENCE: str = Field(default="insight-bridge", description="Audience for InsightBridge")
    CORE_JWKS_URL: str = Field(default="https://sovereign-core.bhiv.local/.well-known/jwks.json", description="JWKS endpoint")
    
    # Metadata Discovery Unit (MDU) Settings
    MDU_BASE_URL: str = Field(default="https://mdu.bhiv.local", description="Base URL for Metadata Discovery Unit")
    MDU_API_TIMEOUT: int = Field(default=5, description="HTTP timeout seconds for MDU requests")
    MDU_ALLOW_TRUST_LEVELS: List[str] = Field(default=["TRUSTED", "VERIFIED"], description="Allowed dataset trust levels")

    # Bucket Settings (Audit Store)
    BUCKET_ENDPOINT: str = Field(default="https://bucket.bhiv.local/audit", description="Bucket audit API")
    BUCKET_AUTH_TOKEN: Optional[str] = None
    
    # InsightFlow Settings (Telemetry)
    INSIGHTFLOW_ENDPOINT: str = Field(default="https://insightflow.bhiv.local/events", description="InsightFlow telemetry endpoint")
    
    # Security Policy
    RATE_LIMIT_WINDOWS_SEC: int = 60
    MAX_REQUESTS_PER_WINDOW: int = 100
    ENFORCE_REPLAY_PROTECTION: bool = True
    
    class Config:
        env_file = ".env"

settings = Settings()
