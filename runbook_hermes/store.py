from __future__ import annotations

import abc
import contextlib
import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

try:  # pragma: no cover - fcntl is Unix-only, CI here is Linux.
    import fcntl
except Exception:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

from .storage_schema import BUCKET_KEY_FIELDS, POSTGRES_DDL, POSTGRES_INDEXES, POSTGRES_TABLES, SQLITE_DDL, SQLITE_INDEXES, SCHEMA_BUCKETS, canonical_record


class Store(abc.ABC):
    """Small durable-store interface used by RunbookHermes.

    The public contract intentionally mirrors the original JsonStore so existing
    callers keep working while backends can add queryable schemas underneath.
    """

    @abc.abstractmethod
    def read(self, bucket: str) -> Dict[str, Any]:
        raise NotImplementedError

    @abc.abstractmethod
    def write(self, bucket: str, data: Dict[str, Any]) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def put(self, bucket: str, key: str, value: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    @abc.abstractmethod
    def append_event(self, incident_id: str, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    def list_bucket(self, bucket: str) -> List[Dict[str, Any]]:
        data = self.read(bucket)
        if bucket == "events":
            out: List[Dict[str, Any]] = []
            for events in data.values():
                if isinstance(events, list):
                    out.extend(events)
            return out
        return list(data.values())


class JsonStore(Store):
    """Local JSON backend with process/thread-safe read-modify-write locking."""

    _thread_locks: Dict[Path, threading.RLock] = {}
    _thread_locks_guard = threading.Lock()

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.root / ".store.lock"
        with self._thread_locks_guard:
            self._thread_lock = self._thread_locks.setdefault(self.lock_path.resolve(), threading.RLock())

    def _path(self, bucket: str) -> Path:
        return self.root / f"{bucket}.json"

    @contextlib.contextmanager
    def _locked(self) -> Iterator[None]:
        self.root.mkdir(parents=True, exist_ok=True)
        with self._thread_lock:
            with self.lock_path.open("a+", encoding="utf-8") as lock_fh:
                if fcntl is not None:
                    fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    if fcntl is not None:
                        fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)

    def _read_unlocked(self, bucket: str) -> Dict[str, Any]:
        path = self._path(bucket)
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _write_unlocked(self, bucket: str, data: Dict[str, Any]) -> None:
        path = self._path(bucket)
        tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(path)

    def read(self, bucket: str) -> Dict[str, Any]:
        with self._locked():
            return self._read_unlocked(bucket)

    def write(self, bucket: str, data: Dict[str, Any]) -> None:
        normalized = data
        if bucket != "events":
            normalized = {str(k): canonical_record(bucket, str(k), v if isinstance(v, dict) else {"value": v}) for k, v in data.items()}
        with self._locked():
            self._write_unlocked(bucket, normalized)

    def put(self, bucket: str, key: str, value: Dict[str, Any]) -> Dict[str, Any]:
        item = canonical_record(bucket, key, value)
        with self._locked():
            data = self._read_unlocked(bucket)
            data[key] = item
            self._write_unlocked(bucket, data)
        return item

    def append_event(self, incident_id: str, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        event = {
            "event_id": f"evt_{uuid.uuid4().hex[:16]}",
            "incident_id": incident_id,
            "event_type": event_type,
            "payload": payload,
            "ts": time.time(),
            "schema_version": 1,
        }
        with self._locked():
            data = self._read_unlocked("events")
            events = data.setdefault(incident_id, [])
            if not isinstance(events, list):
                events = []
                data[incident_id] = events
            events.append(event)
            self._write_unlocked("events", data)
        return event


class SQLiteStore(Store):
    """SQLite backend with schema tables for incidents/evidence/actions/etc."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._thread_lock = threading.RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def _init_db(self) -> None:
        with self._thread_lock, self._connect() as conn:
            for ddl in SQLITE_DDL.values():
                conn.execute(ddl)
            for idx in SQLITE_INDEXES:
                conn.execute(idx)

    @staticmethod
    def _loads(value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return value
        if value is None:
            return {}
        try:
            data = json.loads(value)
            return data if isinstance(data, dict) else {"value": data}
        except Exception:
            return {"value": value}

    @staticmethod
    def _payload(item: Dict[str, Any]) -> str:
        return json.dumps(item, ensure_ascii=False, sort_keys=True)

    def _table_info(self, bucket: str) -> Optional[Tuple[str, str]]:
        if bucket in SCHEMA_BUCKETS and bucket not in {"events"}:
            return bucket, BUCKET_KEY_FIELDS[bucket]
        return None

    def _upsert_known(self, conn: sqlite3.Connection, bucket: str, key: str, value: Dict[str, Any]) -> Dict[str, Any]:
        item = canonical_record(bucket, key, value)
        payload = self._payload(item)
        if bucket == "incidents":
            conn.execute(
                """INSERT INTO incidents(incident_id,service,severity,environment,status,created_at,updated_at,payload)
                   VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(incident_id) DO UPDATE SET service=excluded.service,severity=excluded.severity,environment=excluded.environment,status=excluded.status,created_at=excluded.created_at,updated_at=excluded.updated_at,payload=excluded.payload""",
                (key, item.get("service"), item.get("severity"), item.get("environment"), item.get("status"), item.get("created_at"), item.get("updated_at"), payload),
            )
        elif bucket == "evidence":
            conn.execute(
                """INSERT INTO evidence(evidence_id,incident_id,service,source,confidence,created_at,payload)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(evidence_id) DO UPDATE SET incident_id=excluded.incident_id,service=excluded.service,source=excluded.source,confidence=excluded.confidence,created_at=excluded.created_at,payload=excluded.payload""",
                (key, item.get("incident_id"), item.get("service"), item.get("source"), item.get("confidence"), item.get("created_at", time.time()), payload),
            )
        elif bucket == "hypotheses":
            conn.execute(
                """INSERT INTO hypotheses(hypothesis_id,incident_id,category,confidence,created_at,payload)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(hypothesis_id) DO UPDATE SET incident_id=excluded.incident_id,category=excluded.category,confidence=excluded.confidence,created_at=excluded.created_at,payload=excluded.payload""",
                (key, item.get("incident_id"), item.get("category"), item.get("confidence"), item.get("created_at", time.time()), payload),
            )
        elif bucket == "actions":
            conn.execute(
                """INSERT INTO actions(action_id,incident_id,action_type,risk_level,requires_approval,created_at,payload)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(action_id) DO UPDATE SET incident_id=excluded.incident_id,action_type=excluded.action_type,risk_level=excluded.risk_level,requires_approval=excluded.requires_approval,created_at=excluded.created_at,payload=excluded.payload""",
                (key, item.get("incident_id"), item.get("action_type"), item.get("risk_level"), int(bool(item.get("requires_approval"))), item.get("created_at", time.time()), payload),
            )
        elif bucket == "approvals":
            conn.execute(
                """INSERT INTO approvals(approval_id,incident_id,service,action,status,checkpoint_id,created_at,decided_at,payload)
                   VALUES(?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(approval_id) DO UPDATE SET incident_id=excluded.incident_id,service=excluded.service,action=excluded.action,status=excluded.status,checkpoint_id=excluded.checkpoint_id,created_at=excluded.created_at,decided_at=excluded.decided_at,payload=excluded.payload""",
                (key, item.get("incident_id"), item.get("service"), item.get("action"), item.get("status"), item.get("checkpoint_id"), item.get("created_at"), item.get("decided_at"), payload),
            )
        elif bucket == "checkpoints":
            conn.execute(
                """INSERT INTO checkpoints(checkpoint_id,incident_id,service,action,created_at,payload)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(checkpoint_id) DO UPDATE SET incident_id=excluded.incident_id,service=excluded.service,action=excluded.action,created_at=excluded.created_at,payload=excluded.payload""",
                (key, item.get("incident_id"), item.get("service"), item.get("action"), item.get("created_at"), payload),
            )
        elif bucket == "skills":
            conn.execute(
                """INSERT INTO skills(skill_id,incident_id,service,title,created_at,payload)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(skill_id) DO UPDATE SET incident_id=excluded.incident_id,service=excluded.service,title=excluded.title,created_at=excluded.created_at,payload=excluded.payload""",
                (key, item.get("incident_id"), item.get("service"), item.get("title"), item.get("created_at"), payload),
            )
        else:
            conn.execute(
                "INSERT OR REPLACE INTO kv_store(bucket,key,payload,updated_at) VALUES(?,?,?,?)",
                (bucket, key, payload, time.time()),
            )
        return item

    def read(self, bucket: str) -> Dict[str, Any]:
        with self._thread_lock, self._connect() as conn:
            if bucket == "events":
                rows = conn.execute("SELECT incident_id,event_id,event_type,ts,payload FROM events ORDER BY ts ASC").fetchall()
                out: Dict[str, List[Dict[str, Any]]] = {}
                for row in rows:
                    payload = self._loads(row["payload"])
                    event = {"event_id": row["event_id"], "incident_id": row["incident_id"], "event_type": row["event_type"], "payload": payload, "ts": row["ts"], "schema_version": 1}
                    out.setdefault(row["incident_id"], []).append(event)
                return out
            info = self._table_info(bucket)
            if info:
                table, key_field = info
                rows = conn.execute(f"SELECT {key_field} AS key, payload FROM {table}").fetchall()
                return {row["key"]: self._loads(row["payload"]) for row in rows}
            rows = conn.execute("SELECT key,payload FROM kv_store WHERE bucket=?", (bucket,)).fetchall()
            return {row["key"]: self._loads(row["payload"]) for row in rows}

    def write(self, bucket: str, data: Dict[str, Any]) -> None:
        with self._thread_lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                if bucket == "events":
                    conn.execute("DELETE FROM events")
                    for incident_id, events in data.items():
                        for event in events if isinstance(events, list) else []:
                            event_id = event.get("event_id") or f"evt_{uuid.uuid4().hex[:16]}"
                            conn.execute(
                                "INSERT INTO events(event_id,incident_id,event_type,ts,payload) VALUES(?,?,?,?,?)",
                                (event_id, event.get("incident_id") or incident_id, event.get("event_type", "unknown"), event.get("ts", time.time()), self._payload(event.get("payload", {}))),
                            )
                else:
                    info = self._table_info(bucket)
                    if info:
                        table, _ = info
                        conn.execute(f"DELETE FROM {table}")
                    else:
                        conn.execute("DELETE FROM kv_store WHERE bucket=?", (bucket,))
                    for key, value in data.items():
                        self._upsert_known(conn, bucket, str(key), value if isinstance(value, dict) else {"value": value})
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def put(self, bucket: str, key: str, value: Dict[str, Any]) -> Dict[str, Any]:
        with self._thread_lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                item = self._upsert_known(conn, bucket, key, value)
                conn.execute("COMMIT")
                return item
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def append_event(self, incident_id: str, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        event = {
            "event_id": f"evt_{uuid.uuid4().hex[:16]}",
            "incident_id": incident_id,
            "event_type": event_type,
            "payload": payload,
            "ts": time.time(),
            "schema_version": 1,
        }
        with self._thread_lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO events(event_id,incident_id,event_type,ts,payload) VALUES(?,?,?,?,?)",
                (event["event_id"], incident_id, event_type, event["ts"], self._payload(payload)),
            )
        return event


class PostgresStore(Store):
    """PostgreSQL backend with typed JSONB-backed runbook tables.

    Requires psycopg (v3) or psycopg2 at runtime. It is optional so local demos
    remain dependency-free. The payload JSONB remains the source of truth; typed
    columns make incidents, evidence, actions, approvals and events queryable.
    """

    def __init__(self, dsn: str):
        self.dsn = dsn
        if not dsn:
            raise RuntimeError("RUNBOOK_STORE_POSTGRES_DSN is required for RUNBOOK_STORE_BACKEND=postgres")
        self._driver = self._load_driver()
        self._init_db()

    @staticmethod
    def _load_driver():
        try:
            import psycopg  # type: ignore

            return psycopg
        except Exception:
            try:
                import psycopg2  # type: ignore

                return psycopg2
            except Exception as exc:  # pragma: no cover - optional dependency
                raise RuntimeError("PostgresStore requires psycopg or psycopg2") from exc

    @contextlib.contextmanager
    def _connect(self):
        conn = self._driver.connect(self.dsn)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            cur = conn.cursor()
            for stmt in POSTGRES_DDL.values():
                cur.execute(stmt)
            for stmt in POSTGRES_INDEXES:
                cur.execute(stmt)
            cur.close()

    @staticmethod
    def _json_payload(value: Dict[str, Any]) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _loads(value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return value
        if value is None:
            return {}
        try:
            data = json.loads(value)
            return data if isinstance(data, dict) else {"value": data}
        except Exception:
            return {"value": value}

    def _table_info(self, bucket: str) -> Optional[Tuple[str, str]]:
        return POSTGRES_TABLES.get(bucket)

    def _upsert_known(self, cur: Any, bucket: str, key: str, value: Dict[str, Any]) -> Dict[str, Any]:
        item = canonical_record(bucket, key, value)
        payload = self._json_payload(item)
        if bucket == "incidents":
            cur.execute(
                """INSERT INTO runbook_incidents(incident_id,service,severity,environment,status,created_at,updated_at,payload)
                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                   ON CONFLICT(incident_id) DO UPDATE SET service=excluded.service,severity=excluded.severity,environment=excluded.environment,status=excluded.status,created_at=excluded.created_at,updated_at=excluded.updated_at,payload=excluded.payload""",
                (key, item.get("service"), item.get("severity"), item.get("environment"), item.get("status"), item.get("created_at"), item.get("updated_at"), payload),
            )
        elif bucket == "evidence":
            cur.execute(
                """INSERT INTO runbook_evidence(evidence_id,incident_id,service,source,confidence,created_at,payload)
                   VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb)
                   ON CONFLICT(evidence_id) DO UPDATE SET incident_id=excluded.incident_id,service=excluded.service,source=excluded.source,confidence=excluded.confidence,created_at=excluded.created_at,payload=excluded.payload""",
                (key, item.get("incident_id"), item.get("service"), item.get("source"), item.get("confidence"), item.get("created_at"), payload),
            )
        elif bucket == "hypotheses":
            cur.execute(
                """INSERT INTO runbook_hypotheses(hypothesis_id,incident_id,category,confidence,created_at,payload)
                   VALUES(%s,%s,%s,%s,%s,%s::jsonb)
                   ON CONFLICT(hypothesis_id) DO UPDATE SET incident_id=excluded.incident_id,category=excluded.category,confidence=excluded.confidence,created_at=excluded.created_at,payload=excluded.payload""",
                (key, item.get("incident_id"), item.get("category"), item.get("confidence"), item.get("created_at"), payload),
            )
        elif bucket == "actions":
            cur.execute(
                """INSERT INTO runbook_actions(action_id,incident_id,action_type,risk_level,requires_approval,created_at,payload)
                   VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb)
                   ON CONFLICT(action_id) DO UPDATE SET incident_id=excluded.incident_id,action_type=excluded.action_type,risk_level=excluded.risk_level,requires_approval=excluded.requires_approval,created_at=excluded.created_at,payload=excluded.payload""",
                (key, item.get("incident_id"), item.get("action_type"), item.get("risk_level"), bool(item.get("requires_approval")), item.get("created_at"), payload),
            )
        elif bucket == "approvals":
            cur.execute(
                """INSERT INTO runbook_approvals(approval_id,incident_id,service,action,status,checkpoint_id,created_at,decided_at,payload)
                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                   ON CONFLICT(approval_id) DO UPDATE SET incident_id=excluded.incident_id,service=excluded.service,action=excluded.action,status=excluded.status,checkpoint_id=excluded.checkpoint_id,created_at=excluded.created_at,decided_at=excluded.decided_at,payload=excluded.payload""",
                (key, item.get("incident_id"), item.get("service"), item.get("action"), item.get("status"), item.get("checkpoint_id"), item.get("created_at"), item.get("decided_at"), payload),
            )
        elif bucket == "checkpoints":
            cur.execute(
                """INSERT INTO runbook_checkpoints(checkpoint_id,incident_id,service,action,created_at,payload)
                   VALUES(%s,%s,%s,%s,%s,%s::jsonb)
                   ON CONFLICT(checkpoint_id) DO UPDATE SET incident_id=excluded.incident_id,service=excluded.service,action=excluded.action,created_at=excluded.created_at,payload=excluded.payload""",
                (key, item.get("incident_id"), item.get("service"), item.get("action"), item.get("created_at"), payload),
            )
        elif bucket == "skills":
            cur.execute(
                """INSERT INTO runbook_skills(skill_id,incident_id,service,title,created_at,payload)
                   VALUES(%s,%s,%s,%s,%s,%s::jsonb)
                   ON CONFLICT(skill_id) DO UPDATE SET incident_id=excluded.incident_id,service=excluded.service,title=excluded.title,created_at=excluded.created_at,payload=excluded.payload""",
                (key, item.get("incident_id"), item.get("service"), item.get("title"), item.get("created_at"), payload),
            )
        else:
            cur.execute(
                """INSERT INTO runbook_store(bucket,key,payload,updated_at) VALUES(%s,%s,%s::jsonb,%s)
                   ON CONFLICT(bucket,key) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at""",
                (bucket, key, payload, time.time()),
            )
        return item

    def read(self, bucket: str) -> Dict[str, Any]:
        with self._connect() as conn:
            cur = conn.cursor()
            if bucket == "events":
                cur.execute("SELECT incident_id,event_id,event_type,ts,payload FROM runbook_events ORDER BY ts ASC")
                out: Dict[str, List[Dict[str, Any]]] = {}
                for incident_id, event_id, event_type, ts, payload in cur.fetchall():
                    out.setdefault(incident_id, []).append({"event_id": event_id, "incident_id": incident_id, "event_type": event_type, "payload": self._loads(payload), "ts": ts, "schema_version": 1})
                cur.close()
                return out
            info = self._table_info(bucket)
            if info:
                table, key_field = info
                cur.execute(f"SELECT {key_field},payload FROM {table}")
                out = {key: self._loads(payload) for key, payload in cur.fetchall()}
                cur.close()
                return out
            cur.execute("SELECT key,payload FROM runbook_store WHERE bucket=%s", (bucket,))
            out = {key: self._loads(payload) for key, payload in cur.fetchall()}
            cur.close()
            return out

    def write(self, bucket: str, data: Dict[str, Any]) -> None:
        with self._connect() as conn:
            cur = conn.cursor()
            if bucket == "events":
                cur.execute("DELETE FROM runbook_events")
                for incident_id, events in data.items():
                    for event in events if isinstance(events, list) else []:
                        event_id = event.get("event_id") or f"evt_{uuid.uuid4().hex[:16]}"
                        cur.execute(
                            "INSERT INTO runbook_events(event_id,incident_id,event_type,ts,payload) VALUES(%s,%s,%s,%s,%s::jsonb)",
                            (event_id, event.get("incident_id") or incident_id, event.get("event_type", "unknown"), event.get("ts", time.time()), self._json_payload(event.get("payload", {}))),
                        )
            else:
                info = self._table_info(bucket)
                if info:
                    table, _ = info
                    cur.execute(f"DELETE FROM {table}")
                else:
                    cur.execute("DELETE FROM runbook_store WHERE bucket=%s", (bucket,))
                for key, value in data.items():
                    self._upsert_known(cur, bucket, str(key), value if isinstance(value, dict) else {"value": value})
            cur.close()

    def put(self, bucket: str, key: str, value: Dict[str, Any]) -> Dict[str, Any]:
        with self._connect() as conn:
            cur = conn.cursor()
            item = self._upsert_known(cur, bucket, key, value)
            cur.close()
            return item

    def append_event(self, incident_id: str, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        event = {
            "event_id": f"evt_{uuid.uuid4().hex[:16]}",
            "incident_id": incident_id,
            "event_type": event_type,
            "payload": payload,
            "ts": time.time(),
            "schema_version": 1,
        }
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO runbook_events(event_id,incident_id,event_type,ts,payload) VALUES(%s,%s,%s,%s,%s::jsonb)",
                (event["event_id"], incident_id, event_type, event["ts"], self._json_payload(payload)),
            )
            cur.close()
        return event

def get_store(settings: Any | None = None) -> Store:
    if settings is None:
        from .config import load_settings

        settings = load_settings()
    backend = str(getattr(settings, "store_backend", "json") or "json").strip().lower()
    if backend in {"json", "local", "file", "files"}:
        return JsonStore(getattr(settings, "store_dir"))
    if backend in {"sqlite", "sqlite3"}:
        db_path = getattr(settings, "store_sqlite_path", None) or Path(getattr(settings, "store_dir")) / "runbook_store.sqlite3"
        return SQLiteStore(db_path)
    if backend in {"postgres", "postgresql", "pg"}:
        return PostgresStore(str(getattr(settings, "store_postgres_dsn", "") or ""))
    raise ValueError(f"Unsupported RUNBOOK_STORE_BACKEND={backend!r}")
