# -*- coding: utf-8 -*-
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

_PRODUCT_ROOT = Path(__file__).resolve().parent.parent.parent
_DB_PATH = Path(os.environ.get("DATABASE_PATH", _PRODUCT_ROOT / "data" / "parking_pso.db"))


def _conn():
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS scenarios (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                scenario_json TEXT NOT NULL,
                metrics_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT,
                result_json TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )


def _now():
    return datetime.now(timezone.utc).isoformat()


def list_scenarios():
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, name, metrics_json, created_at, updated_at FROM scenarios ORDER BY updated_at DESC"
        ).fetchall()
    out = []
    for r in rows:
        metrics = json.loads(r["metrics_json"]) if r["metrics_json"] else {}
        out.append(
            {
                "id": r["id"],
                "name": r["name"],
                "metrics": metrics,
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            }
        )
    return out


def get_scenario(scenario_id):
    with _conn() as conn:
        row = conn.execute("SELECT * FROM scenarios WHERE id = ?", (scenario_id,)).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "name": row["name"],
        "scenario": json.loads(row["scenario_json"]),
        "metrics": json.loads(row["metrics_json"]) if row["metrics_json"] else {},
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def save_scenario(name, scenario, metrics=None, scenario_id=None):
    sid = scenario_id or str(uuid.uuid4())
    now = _now()
    metrics_json = json.dumps(metrics or {}, ensure_ascii=False)
    scenario_json = json.dumps(scenario, ensure_ascii=False)
    with _conn() as conn:
        existing = conn.execute("SELECT id FROM scenarios WHERE id = ?", (sid,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE scenarios SET name=?, scenario_json=?, metrics_json=?, updated_at=? WHERE id=?",
                (name, scenario_json, metrics_json, now, sid),
            )
        else:
            conn.execute(
                "INSERT INTO scenarios (id, name, scenario_json, metrics_json, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                (sid, name, scenario_json, metrics_json, now, now),
            )
    return get_scenario(sid)


def delete_scenario(scenario_id):
    with _conn() as conn:
        conn.execute("DELETE FROM scenarios WHERE id = ?", (scenario_id,))
    return True


def create_job(kind, payload):
    jid = str(uuid.uuid4())
    now = _now()
    with _conn() as conn:
        conn.execute(
            "INSERT INTO jobs (id, kind, status, payload_json, result_json, error, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (jid, kind, "pending", json.dumps(payload, ensure_ascii=False), None, None, now, now),
        )
    return jid


def update_job(jid, status, result=None, error=None):
    now = _now()
    with _conn() as conn:
        conn.execute(
            "UPDATE jobs SET status=?, result_json=?, error=?, updated_at=? WHERE id=?",
            (
                status,
                json.dumps(result, ensure_ascii=False) if result is not None else None,
                error,
                now,
                jid,
            ),
        )


def get_job(jid):
    with _conn() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (jid,)).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "kind": row["kind"],
        "status": row["status"],
        "payload": json.loads(row["payload_json"]) if row["payload_json"] else {},
        "result": json.loads(row["result_json"]) if row["result_json"] else None,
        "error": row["error"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
