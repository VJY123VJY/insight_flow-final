import pytest
from httpx import AsyncClient
from main import app
from app.core.config import settings
from app.core.security import SovereignAuth
import time
import json

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

@pytest.mark.asyncio
async def test_valid_request(monkeypatch):
    # Mock JWKS and Token Decoding
    monkeypatch.setattr(SovereignAuth, "get_jwks", MockJWKS.get_mock_jwks)
    
    # We mock the decode to bypass RSA validation in this test env
    monkeypatch.setattr("jose.jwt.decode", lambda *args, **kwargs: {
        "sub": "user_123",
        "aud": settings.CORE_AUDIENCE,
        "iss": settings.CORE_ISSUER,
        "jti": "unique_jti_1"
    })
    monkeypatch.setattr("jose.jwt.get_unverified_header", lambda token: {"kid": "demo-kid"})

    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post(
            "/enforce?resource=bucket_access",
            headers={"Authorization": "Bearer valid_token"}
        )
    
    assert response.status_code == 200
    assert response.json()["status"] == "ALLOW"
    print("\n[VERIFIED] Valid Request -> ALLOW")

@pytest.mark.asyncio
async def test_invalid_jwt(monkeypatch):
    monkeypatch.setattr(SovereignAuth, "get_jwks", MockJWKS.get_mock_jwks)
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # No header
        response = await ac.post("/enforce")
        assert response.status_code == 403 # FastAPI default for missing bearer

        # Invalid token
        response = await ac.post(
            "/enforce",
            headers={"Authorization": "Bearer invalid_token"}
        )
        assert response.status_code == 401
    print("[VERIFIED] Invalid JWT -> 401 DENY")

@pytest.mark.asyncio
async def test_replay_protection(monkeypatch):
    monkeypatch.setattr(SovereignAuth, "get_jwks", MockJWKS.get_mock_jwks)
    monkeypatch.setattr("jose.jwt.get_unverified_header", lambda token: {"kid": "demo-kid"})
    
    # Same JTI for both requests
    jti = "replay_jti_123"
    monkeypatch.setattr("jose.jwt.decode", lambda *args, **kwargs: {
        "sub": "user_123", "aud": settings.CORE_AUDIENCE, "iss": settings.CORE_ISSUER, "jti": jti
    })

    async with AsyncClient(app=app, base_url="http://test") as ac:
        # First use
        await ac.post("/enforce", headers={"Authorization": "Bearer token1"})
        # Replay
        response = await ac.post("/enforce", headers={"Authorization": "Bearer token1"})
    
    assert response.status_code == 403
    assert "Replay attack" in response.json()["detail"]
    print("[VERIFIED] Replay Attempt -> 403 DENY")

@pytest.mark.asyncio
async def test_fail_closed_core_unavailable(monkeypatch):
    # Simulate Core Down
    monkeypatch.setattr(SovereignAuth, "get_jwks", lambda: None)
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post(
            "/enforce",
            headers={"Authorization": "Bearer some_token"}
        )
    
    assert response.status_code == 503
    assert "Unavailable" in response.json()["detail"]
    print("[VERIFIED] Core Unavailable -> 503 FAIL-CLOSED")

@pytest.mark.asyncio
async def test_rate_limit(monkeypatch):
    monkeypatch.setattr(SovereignAuth, "get_jwks", MockJWKS.get_mock_jwks)
    monkeypatch.setattr("jose.jwt.get_unverified_header", lambda token: {"kid": "demo-kid"})
    
    # Mock unique JTI for each call
    jti_counter = 0
    def mock_decode(*args, **kwargs):
        nonlocal jti_counter
        jti_counter += 1
        return {"sub": "throttled_user", "aud": settings.CORE_AUDIENCE, "iss": settings.CORE_ISSUER, "jti": f"jti_{jti_counter}"}
    
    monkeypatch.setattr("jose.jwt.decode", mock_decode)

    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Fire 6 requests (Limit is 5)
        for _ in range(5):
            await ac.post("/enforce", headers={"Authorization": "Bearer t"})
        
        response = await ac.post("/enforce", headers={"Authorization": "Bearer t"})
        assert response.status_code == 429
    print("[VERIFIED] Rate Limit Breach -> 429 DENY")
