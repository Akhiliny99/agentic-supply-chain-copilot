"""
GCP client layer: BigQuery (lakehouse), Pub/Sub (event bus), Vertex AI
(model hosting).

USE_REAL_GCP=false (default): everything runs against local stand-ins
(SQLite for BigQuery, an in-process queue for Pub/Sub) so the whole project
runs with zero cloud account. This is intentional — an interviewer can run
it in 30 seconds.

USE_REAL_GCP=true: the real google-cloud-* clients below take over. The
calling code in pipeline/ingest.py and agents/ never changes either way —
it only talks to the functions in this file.
"""
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from queue import Queue
from typing import Any

USE_REAL_GCP = os.getenv("USE_REAL_GCP", "false").lower() == "true"
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "")
BQ_DATASET = os.getenv("BQ_DATASET", "supply_chain_copilot")
PUBSUB_TOPIC = os.getenv("PUBSUB_TOPIC", "agent-events")
LOCAL_LAKEHOUSE_PATH = Path(os.getenv("AUDIT_DB_PATH", "./audit_trail.db")).parent / "lakehouse.db"

# ---------------------------------------------------------------------------
# Pub/Sub (event ingestion from ERP / plant systems into the pipeline)
# ---------------------------------------------------------------------------
_local_queue: "Queue[dict]" = Queue()


def publish_event(payload: dict) -> None:
    payload = {**payload, "published_at": datetime.utcnow().isoformat()}
    if USE_REAL_GCP:
        from google.cloud import pubsub_v1  # pragma: no cover - needs real creds

        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(GCP_PROJECT_ID, PUBSUB_TOPIC)
        publisher.publish(topic_path, json.dumps(payload).encode("utf-8"))
    else:
        _local_queue.put(payload)


def drain_events() -> list[dict]:
    """Local-mode helper: pull everything currently queued (Dataflow would
    normally do this continuously; here we just drain synchronously)."""
    events = []
    while not _local_queue.empty():
        events.append(_local_queue.get())
    return events


# ---------------------------------------------------------------------------
# BigQuery (lakehouse storage for transformed events + decisions)
# ---------------------------------------------------------------------------
def _local_conn():
    LOCAL_LAKEHOUSE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(LOCAL_LAKEHOUSE_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS lakehouse_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT,
            payload TEXT,
            inserted_at TEXT
        )"""
    )
    return conn


def write_rows(table_name: str, rows: list[dict]) -> None:
    if not rows:
        return
    if USE_REAL_GCP:
        from google.cloud import bigquery  # pragma: no cover - needs real creds

        client = bigquery.Client(project=GCP_PROJECT_ID)
        table_ref = f"{GCP_PROJECT_ID}.{BQ_DATASET}.{table_name}"
        errors = client.insert_rows_json(table_ref, rows)
        if errors:
            raise RuntimeError(f"BigQuery insert errors: {errors}")
    else:
        conn = _local_conn()
        with conn:
            for row in rows:
                conn.execute(
                    "INSERT INTO lakehouse_events (table_name, payload, inserted_at) VALUES (?, ?, ?)",
                    (table_name, json.dumps(row), datetime.utcnow().isoformat()),
                )
        conn.close()


def read_rows(table_name: str, limit: int = 100) -> list[dict]:
    if USE_REAL_GCP:
        from google.cloud import bigquery  # pragma: no cover - needs real creds

        client = bigquery.Client(project=GCP_PROJECT_ID)
        query = f"SELECT * FROM `{GCP_PROJECT_ID}.{BQ_DATASET}.{table_name}` LIMIT {limit}"
        return [dict(row) for row in client.query(query).result()]
    conn = _local_conn()
    cur = conn.execute(
        "SELECT payload, inserted_at FROM lakehouse_events WHERE table_name=? ORDER BY id DESC LIMIT ?",
        (table_name, limit),
    )
    rows = [{**json.loads(p), "_inserted_at": t} for p, t in cur.fetchall()]
    conn.close()
    return rows


# ---------------------------------------------------------------------------
# Vertex AI (forecasting model hosting)
# ---------------------------------------------------------------------------
def vertex_predict(model_name: str, instances: list[dict]) -> Any:
    """Real path calls a deployed Vertex AI endpoint. Local path calls the
    same rule-based forecaster used by agents/llm_client.py's mock mode, so
    behaviour is consistent whichever mode you run in."""
    if USE_REAL_GCP:
        from google.cloud import aiplatform  # pragma: no cover - needs real creds

        aiplatform.init(project=GCP_PROJECT_ID)
        endpoint = aiplatform.Endpoint(model_name)
        return endpoint.predict(instances=instances)
    from agents.forecaster_agent import naive_forecast  # local import avoids cycle

    return [naive_forecast(inst["history"]) for inst in instances]
