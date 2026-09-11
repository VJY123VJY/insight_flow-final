import os
import json
import time
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
import aiosqlite
try:
    from bucket.models import AuditEventCreate
except ImportError:
    from models import AuditEventCreate

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = os.getenv("BUCKET_DB_PATH", os.path.join(os.path.dirname(__file__), "data", "bucket.db"))


class AuditStorage:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        # Ensure parent directory exists
        parent_dir = os.path.dirname(os.path.abspath(self.db_path))
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

    async def init_db(self):
        """Initializes the database schema if not already present."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS audit_events (
                    audit_id TEXT PRIMARY KEY,
                    timestamp REAL NOT NULL,
                    action TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    reason TEXT,
                    identity TEXT,
                    context TEXT,
                    request_metadata TEXT,
                    runtime_metadata TEXT,
                    raw_payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_events(timestamp DESC)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_audit_identity ON audit_events(identity)")
            await db.commit()
        logger.info(f"Audit database initialized at {self.db_path}")

    async def check_health(self) -> bool:
        """Executes a lightweight query to verify storage connectivity and usability."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute("SELECT 1") as cursor:
                    result = await cursor.fetchone()
                    return result is not None and result[0] == 1
        except Exception as exc:
            logger.error(f"AuditStorage health check failed: {exc}")
            return False

    async def store_event(self, event: AuditEventCreate) -> Dict[str, Any]:
        """Persists a validated audit event into SQLite storage."""
        audit_id = event.audit_id or str(uuid.uuid4())
        
        # Handle timestamp parsing
        if event.timestamp is not None:
            try:
                ts = float(event.timestamp)
            except (ValueError, TypeError):
                ts = time.time()
        else:
            ts = time.time()

        created_at = datetime.now(timezone.utc).isoformat()
        
        # Serialize raw incoming payload
        raw_dict = event.model_dump(exclude_unset=False)
        raw_payload_str = json.dumps(raw_dict)
        context_str = json.dumps(event.context) if event.context is not None else "{}"
        req_meta_str = json.dumps(event.request_metadata) if event.request_metadata is not None else "{}"
        rt_meta_str = json.dumps(event.runtime_metadata) if event.runtime_metadata is not None else "{}"

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO audit_events (
                    audit_id, timestamp, action, decision, reason, identity,
                    context, request_metadata, runtime_metadata, raw_payload, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                audit_id,
                ts,
                event.action,
                event.decision,
                event.reason,
                event.identity,
                context_str,
                req_meta_str,
                rt_meta_str,
                raw_payload_str,
                created_at
            ))
            await db.commit()

        stored_record = {
            "audit_id": audit_id,
            "timestamp": ts,
            "action": event.action,
            "decision": event.decision,
            "reason": event.reason,
            "identity": event.identity,
            "context": event.context or {},
            "request_metadata": event.request_metadata or {},
            "runtime_metadata": event.runtime_metadata or {},
            "created_at": created_at
        }
        return stored_record

    def _row_to_dict(self, row: sqlite3_row_type if False else Any) -> Dict[str, Any]:
        audit_id, ts, action, decision, reason, identity, ctx, req_meta, rt_meta, raw_payload, created_at = row
        try:
            extra_data = json.loads(raw_payload) if raw_payload else {}
        except Exception:
            extra_data = {}

        record = {
            **extra_data,
            "audit_id": audit_id,
            "timestamp": ts,
            "action": action,
            "decision": decision,
            "reason": reason,
            "identity": identity,
            "context": json.loads(ctx) if ctx else {},
            "request_metadata": json.loads(req_meta) if req_meta else {},
            "runtime_metadata": json.loads(rt_meta) if rt_meta else {},
            "created_at": created_at
        }
        return record

    async def get_events(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Retrieves paginated audit events ordered by timestamp descending."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT audit_id, timestamp, action, decision, reason, identity,
                       context, request_metadata, runtime_metadata, raw_payload, created_at
                FROM audit_events
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
            """, (limit, offset)) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_dict(row) for row in rows]

    async def get_event_by_id(self, audit_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single audit event by unique audit_id."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT audit_id, timestamp, action, decision, reason, identity,
                       context, request_metadata, runtime_metadata, raw_payload, created_at
                FROM audit_events
                WHERE audit_id = ?
            """, (audit_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return self._row_to_dict(row)

    async def count_events(self) -> int:
        """Returns total count of stored audit records."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM audit_events") as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0
