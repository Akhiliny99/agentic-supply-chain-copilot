"""
Audit trail — the JD's "responsible-AI documentation for autonomous
systems" requirement. Every agent decision is logged with: which agent
made it, what data sources it used, the outcome, guardrail result, and
whether it was auto-applied or escalated to a human.

Uses SQLite locally (stand-in for a BigQuery audit table — same schema,
just swap write_rows()/read_rows() for the real BigQuery calls in
pipeline/gcp_clients.py, which is exactly what USE_REAL_GCP does).
"""
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(os.getenv("AUDIT_DB_PATH", "./audit_trail.db"))


def _conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT,
            cycle_json TEXT,
            guardrail_passed INTEGER,
            escalated INTEGER,
            outcome TEXT,
            sources TEXT,
            created_at TEXT
        )"""
    )
    return conn


def log_decision(sku: str, cycle: dict, guardrail_passed: bool, escalated: bool, outcome: str, sources: list[str]) -> None:
    conn = _conn()
    with conn:
        conn.execute(
            """INSERT INTO decisions (sku, cycle_json, guardrail_passed, escalated, outcome, sources, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                sku,
                json.dumps(cycle),
                int(guardrail_passed),
                int(escalated),
                outcome,
                json.dumps(sources),
                datetime.utcnow().isoformat(),
            ),
        )
    conn.close()


def get_recent_decisions(limit: int = 50) -> list[dict]:
    conn = _conn()
    cur = conn.execute(
        "SELECT sku, cycle_json, guardrail_passed, escalated, outcome, sources, created_at "
        "FROM decisions ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "sku": r[0],
            "cycle": json.loads(r[1]),
            "guardrail_passed": bool(r[2]),
            "escalated": bool(r[3]),
            "outcome": r[4],
            "sources": json.loads(r[5]),
            "created_at": r[6],
        }
        for r in rows
    ]
