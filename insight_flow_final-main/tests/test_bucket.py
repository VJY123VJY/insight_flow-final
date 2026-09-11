import pytest
import os
import tempfile
import uuid
from httpx import ASGITransport, AsyncClient

from bucket.main import app, storage
from bucket.models import AuditEventCreate
from bucket.storage import AuditStorage


import asyncio

@pytest.fixture(autouse=True)
def init_test_db(tmp_path, monkeypatch):
    """Initializes an isolated temporary SQLite database for each test."""
    test_db_path = str(tmp_path / "test_bucket.db")
    test_storage = AuditStorage(db_path=test_db_path)
    asyncio.run(test_storage.init_db())
    monkeypatch.setattr("bucket.main.storage", test_storage)
    return test_storage


@pytest.mark.asyncio
async def test_bucket_health():
    """Verify GET /health returns expected healthy payload."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "service": "bucket"
    }


@pytest.mark.asyncio
async def test_bucket_health_unhealthy(monkeypatch):
    """Verify GET /health returns 503 when storage layer is unreachable."""
    async def mock_unhealthy():
        return False

    monkeypatch.setattr("bucket.main.storage.check_health", mock_unhealthy)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/health")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["service"] == "bucket"


@pytest.mark.asyncio
async def test_bucket_post_audit_full():
    """Verify POST /audit persists an event with full metadata."""
    custom_id = f"audit-{uuid.uuid4()}"
    payload = {
        "audit_id": custom_id,
        "timestamp": 1718282891.123,
        "action": "ENFORCE",
        "decision": "ALLOW",
        "reason": "Valid identity and policy compliance",
        "identity": "admin_user",
        "context": {
            "method": "POST",
            "path": "/enforce",
            "ip": "127.0.0.1",
            "resource": "bucket_access",
            "dataset_id": "BHIV-DS-GOVERNANCE-MUTATION-LOGS-001"
        },
        "request_metadata": {"version": "v1"},
        "runtime_metadata": {"worker": "worker-1"}
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/audit", json=payload)
    
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "success"
    assert data["audit_id"] == custom_id
    assert "recorded successfully" in data["message"]

    # Verify retrieval
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        get_res = await ac.get(f"/audit/{custom_id}")
    assert get_res.status_code == 200
    saved = get_res.json()
    assert saved["audit_id"] == custom_id
    assert saved["decision"] == "ALLOW"
    assert saved["identity"] == "admin_user"
    assert saved["context"]["dataset_id"] == "BHIV-DS-GOVERNANCE-MUTATION-LOGS-001"
    assert saved["request_metadata"]["version"] == "v1"


@pytest.mark.asyncio
async def test_bucket_post_audit_generates_id_and_timestamp():
    """Verify POST /audit automatically generates audit_id and timestamp if omitted."""
    payload = {
        "decision": "DENY",
        "reason": "Missing required header"
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/audit", json=payload)
    
    assert response.status_code == 201
    data = response.json()
    generated_id = data["audit_id"]
    assert generated_id is not None
    assert len(generated_id) > 10

    # Retrieve and check generated timestamp
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        get_res = await ac.get(f"/audit/{generated_id}")
    assert get_res.status_code == 200
    saved = get_res.json()
    assert saved["decision"] == "DENY"
    assert saved["timestamp"] is not None
    assert "created_at" in saved


@pytest.mark.asyncio
async def test_bucket_get_audit_list():
    """Verify GET /audit returns list of stored records with pagination metadata."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post("/audit", json={"decision": "ALLOW", "reason": "event 1"})
        await ac.post("/audit", json={"decision": "DENY", "reason": "event 2"})

        response = await ac.get("/audit?limit=10&offset=0")
    
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 2
    assert len(data["events"]) >= 2


@pytest.mark.asyncio
async def test_bucket_get_audit_not_found():
    """Verify GET /audit/{audit_id} returns 404 for unknown IDs."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/audit/nonexistent-uuid-12345")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_bucket_invalid_payload():
    """Verify POST /audit rejects invalid payload missing required fields."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Missing decision field
        response = await ac.post("/audit", json={"reason": "incomplete payload"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_bucket_persistence(tmp_path):
    """Verify stored audit records persist across storage instance restarts using SQLite."""
    db_file = str(tmp_path / "persistent_test.db")
    
    # 1. First storage instance writes event
    storage1 = AuditStorage(db_path=db_file)
    await storage1.init_db()
    event_id = f"persist-{uuid.uuid4()}"
    event = AuditEventCreate(
        audit_id=event_id,
        decision="ALLOW",
        reason="Persistence Verification",
        identity="persistence_user",
        context={"env": "test"}
    )
    await storage1.store_event(event)

    # 2. Simulate complete restart: create new storage instance pointing to same file
    storage2 = AuditStorage(db_path=db_file)
    retrieved = await storage2.get_event_by_id(event_id)
    assert retrieved is not None
    assert retrieved["audit_id"] == event_id
    assert retrieved["decision"] == "ALLOW"
    assert retrieved["identity"] == "persistence_user"
    assert retrieved["context"] == {"env": "test"}
