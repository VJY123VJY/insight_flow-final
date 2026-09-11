import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from main import app
from app.core.config import settings
from app.core.security import SovereignAuth
from app.schemas.dataset import DatasetMetadata
import time


# --- MOCKING ---
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
async def test_valid_request(monkeypatch):
    monkeypatch.setattr(SovereignAuth, "get_jwks", MockJWKS.get_mock_jwks)
    monkeypatch.setattr("jose.jwt.decode", lambda *args, **kwargs: {
        "sub": "user_123",
        "aud": settings.CORE_AUDIENCE,
        "iss": settings.CORE_ISSUER,
        "jti": "unique_jti_1"
    })
    monkeypatch.setattr("jose.jwt.get_unverified_header", lambda token: {"kid": "demo-kid"})
    monkeypatch.setattr("app.services.mdu.MDUService.fetch_dataset_metadata", mock_valid_dataset)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/enforce?resource=bucket_access&dataset_id=BHIV-DS-GOVERNANCE-MUTATION-LOGS-001",
            headers={"Authorization": "Bearer valid_token"}
        )
    
    assert response.status_code == 200
    assert response.json()["status"] == "ALLOW"
    assert response.json()["dataset_trust_level"] == "VERIFIED"


@pytest.mark.asyncio
async def test_invalid_jwt(monkeypatch):
    monkeypatch.setattr(SovereignAuth, "get_jwks", MockJWKS.get_mock_jwks)
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # No header
        response = await ac.post("/enforce")
        assert response.status_code in (401, 403)

        # Invalid token
        response = await ac.post(
            "/enforce",
            headers={"Authorization": "Bearer invalid_token"}
        )
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_provisional_dataset_denied(monkeypatch):
    monkeypatch.setattr(SovereignAuth, "get_jwks", MockJWKS.get_mock_jwks)
    monkeypatch.setattr("jose.jwt.decode", lambda *args, **kwargs: {
        "sub": "user_123",
        "aud": settings.CORE_AUDIENCE,
        "iss": settings.CORE_ISSUER,
        "jti": "unique_jti_2"
    })
    monkeypatch.setattr("jose.jwt.get_unverified_header", lambda token: {"kid": "demo-kid"})

    async def mock_provisional(dataset_id: str):
        raise HTTPException(
            status_code=403,
            detail=(
                f"Dataset {dataset_id} trust level 'PROVISIONAL' is not permitted. "
                "Only TRUSTED or VERIFIED datasets may be processed."
            )
        )

    monkeypatch.setattr("app.services.mdu.MDUService.fetch_dataset_metadata", mock_provisional)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/enforce?dataset_id=BHIV-DS-TRUST-PROPAGATION-001",
            headers={"Authorization": "Bearer valid_token"}
        )
    assert response.status_code == 403
    assert "PROVISIONAL" in response.json()["detail"]


@pytest.mark.asyncio
async def test_replay_protection(monkeypatch):
    monkeypatch.setattr(SovereignAuth, "get_jwks", MockJWKS.get_mock_jwks)
    monkeypatch.setattr("jose.jwt.get_unverified_header", lambda token: {"kid": "demo-kid"})
    monkeypatch.setattr("app.services.mdu.MDUService.fetch_dataset_metadata", mock_valid_dataset)

    # Same JTI for both requests
    jti = "replay_jti_123"
    monkeypatch.setattr("jose.jwt.decode", lambda *args, **kwargs: {
        "sub": "user_123", "aud": settings.CORE_AUDIENCE, "iss": settings.CORE_ISSUER, "jti": jti
    })

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post(
            "/enforce?dataset_id=BHIV-DS-GOVERNANCE-MUTATION-LOGS-001",
            headers={"Authorization": "Bearer token1"}
        )
        response = await ac.post(
            "/enforce?dataset_id=BHIV-DS-GOVERNANCE-MUTATION-LOGS-001",
            headers={"Authorization": "Bearer token1"}
        )
    
    assert response.status_code == 403
    assert "Replay attack" in response.json()["detail"]


@pytest.mark.asyncio
async def test_fail_closed_core_unavailable(monkeypatch):
    monkeypatch.setattr(SovereignAuth, "get_jwks", MockJWKS.get_mock_jwks)
    monkeypatch.setattr("jose.jwt.get_unverified_header", lambda token: {"kid": "demo-kid"})
    monkeypatch.setattr("jose.jwt.decode", lambda *args, **kwargs: {
        "sub": "user_123",
        "aud": settings.CORE_AUDIENCE,
        "iss": settings.CORE_ISSUER,
        "jti": "mdu_unavailable_jti"
    })

    async def mock_mdu_unavailable(dataset_id):
        raise HTTPException(
            status_code=503,
            detail="Metadata Discovery Unit unavailable"
        )

    monkeypatch.setattr("app.services.mdu.MDUService.fetch_dataset_metadata", mock_mdu_unavailable)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/enforce?dataset_id=BHIV-DS-GOVERNANCE-MUTATION-LOGS-001",
            headers={"Authorization": "Bearer valid_token"}
        )
    
    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_rate_limit(monkeypatch):
    monkeypatch.setattr(SovereignAuth, "get_jwks", MockJWKS.get_mock_jwks)
    monkeypatch.setattr("jose.jwt.get_unverified_header", lambda token: {"kid": "demo-kid"})
    monkeypatch.setattr("app.services.mdu.MDUService.fetch_dataset_metadata", mock_valid_dataset)
    
    jti_counter = 0
    def mock_decode(*args, **kwargs):
        nonlocal jti_counter
        jti_counter += 1
        return {
            "sub": "throttled_user",
            "aud": settings.CORE_AUDIENCE,
            "iss": settings.CORE_ISSUER,
            "jti": f"jti_{jti_counter}"
        }
    
    monkeypatch.setattr("jose.jwt.decode", mock_decode)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        for _ in range(5):
            await ac.post(
                "/enforce?dataset_id=BHIV-DS-GOVERNANCE-MUTATION-LOGS-001",
                headers={"Authorization": "Bearer t"}
            )
        
        response = await ac.post(
            "/enforce?dataset_id=BHIV-DS-GOVERNANCE-MUTATION-LOGS-001",
            headers={"Authorization": "Bearer t"}
        )
        assert response.status_code == 429
