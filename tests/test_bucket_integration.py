import pytest
from httpx import ASGITransport, AsyncClient
import httpx

from main import app as insightflow_app
from bucket.main import app as bucket_app
from bucket.storage import AuditStorage
from app.core.config import settings
from app.core.security import SovereignAuth
from app.schemas.dataset import DatasetMetadata


class MockJWKS:
    @staticmethod
    async def get_mock_jwks():
        return {
            "keys": [
                {
                    "kid": "demo-kid",
                    "kty": "RSA",
                    "n": "v... (mock)",
                    "e": "AQAB"
                }
            ]
        }


async def mock_valid_dataset(dataset_id: str):
    return DatasetMetadata(
        dataset_id=dataset_id,
        trust_level="VERIFIED",
        schema_name="COMPATIBLE",
        compatibility="COMPATIBLE",
        provenance="MDU"
    )


@pytest.mark.asyncio
async def test_end_to_end_insightflow_to_bucket_flow(tmp_path, monkeypatch):
    """
    End-to-End Integration Test:
    InsightFlow request
      → Decision generated (ALLOW)
      → ObservabilityService
      → HTTP POST /audit to Bucket service
      → Real SQLite persistence
      → Audit event retrieved and verified from Bucket.
    
    This does NOT mock the Bucket HTTP response; it executes against the real Bucket FastAPI app & storage.
    """
    # 1. Set up real SQLite storage for Bucket microservice
    test_db_path = str(tmp_path / "e2e_bucket.db")
    test_storage = AuditStorage(db_path=test_db_path)
    await test_storage.init_db()
    monkeypatch.setattr("bucket.main.storage", test_storage)

    # 2. Wire InsightFlow's httpx client to dispatch directly to Bucket FastAPI app via ASGITransport
    bucket_transport = ASGITransport(app=bucket_app)
    original_async_client = httpx.AsyncClient

    def custom_async_client(*args, **kwargs):
        # Route requests targeting bucket endpoint to real Bucket ASGI transport
        kwargs["transport"] = bucket_transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr("httpx.AsyncClient", custom_async_client)
    monkeypatch.setattr(settings, "BUCKET_ENDPOINT", "http://bucket.test/audit")

    # 3. Mock Auth & MDU for valid token and dataset
    monkeypatch.setattr(SovereignAuth, "get_jwks", MockJWKS.get_mock_jwks)
    monkeypatch.setattr("jose.jwt.decode", lambda *args, **kwargs: {
        "sub": "audited_principal_42",
        "aud": settings.CORE_AUDIENCE,
        "iss": settings.CORE_ISSUER,
        "jti": "unique_e2e_jti"
    })
    monkeypatch.setattr("jose.jwt.get_unverified_header", lambda token: {"kid": "demo-kid"})
    monkeypatch.setattr("app.services.mdu.MDUService.fetch_dataset_metadata", mock_valid_dataset)

    # 4. Execute InsightFlow /enforce request
    async with AsyncClient(transport=ASGITransport(app=insightflow_app), base_url="http://insightflow.test") as if_client:
        enforce_response = await if_client.post(
            "/enforce?resource=confidential_data&dataset_id=BHIV-DS-GOVERNANCE-MUTATION-LOGS-001",
            headers={"Authorization": "Bearer valid_e2e_token"}
        )

    assert enforce_response.status_code == 200
    decision_data = enforce_response.json()
    assert decision_data["status"] == "ALLOW"
    assert decision_data["principal"] == "audited_principal_42"

    # 5. Query Bucket directly via HTTP GET /audit to retrieve persisted records
    async with AsyncClient(transport=ASGITransport(app=bucket_app), base_url="http://bucket.test") as b_client:
        list_response = await b_client.get("/audit")
        assert list_response.status_code == 200
        audit_data = list_response.json()
        assert audit_data["total"] >= 1

        # Find the event matching our principal
        matched_event = None
        for ev in audit_data["events"]:
            if ev.get("identity") == "audited_principal_42":
                matched_event = ev
                break
        
        assert matched_event is not None, "Audit event was not persisted in Bucket"
        assert matched_event["decision"] == "ALLOW"
        assert matched_event["action"] == "ENFORCE"
        assert matched_event["context"]["resource"] == "confidential_data"
        assert matched_event["context"]["dataset_id"] == "BHIV-DS-GOVERNANCE-MUTATION-LOGS-001"

        # 6. Retrieve specific event via GET /audit/{audit_id}
        audit_id = matched_event["audit_id"]
        detail_response = await b_client.get(f"/audit/{audit_id}")
        assert detail_response.status_code == 200
        detail_data = detail_response.json()
        assert detail_data["audit_id"] == audit_id
        assert detail_data["identity"] == "audited_principal_42"


@pytest.mark.asyncio
async def test_bucket_unavailable_resilience(monkeypatch):
    """
    Verify that when the Bucket service is completely unavailable (connection error / timeout),
    InsightFlow logs the critical failure clearly but does NOT crash the decision request.
    """
    # Mock Auth & MDU
    monkeypatch.setattr(SovereignAuth, "get_jwks", MockJWKS.get_mock_jwks)
    monkeypatch.setattr("jose.jwt.decode", lambda *args, **kwargs: {
        "sub": "resilient_user",
        "aud": settings.CORE_AUDIENCE,
        "iss": settings.CORE_ISSUER,
        "jti": "jti_resilient"
    })
    monkeypatch.setattr("jose.jwt.get_unverified_header", lambda token: {"kid": "demo-kid"})
    monkeypatch.setattr("app.services.mdu.MDUService.fetch_dataset_metadata", mock_valid_dataset)

    # Point to an unroutable port with small timeout
    monkeypatch.setattr(settings, "BUCKET_ENDPOINT", "http://127.0.0.1:19999/audit")
    monkeypatch.setattr(settings, "BUCKET_TIMEOUT", 0.5)

    async with AsyncClient(transport=ASGITransport(app=insightflow_app), base_url="http://test") as if_client:
        response = await if_client.post(
            "/enforce?dataset_id=BHIV-DS-GOVERNANCE-MUTATION-LOGS-001",
            headers={"Authorization": "Bearer valid_token"}
        )

    # The request must succeed despite Bucket being down
    assert response.status_code == 200
    assert response.json()["status"] == "ALLOW"
