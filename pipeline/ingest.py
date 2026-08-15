"""
Ingestion pipeline: ERP data -> Pub/Sub (event bus) -> transform (stand-in
for a Dataflow job) -> BigQuery (lakehouse).

This is the "data pipelines integrating enterprise ERP systems with cloud
and lakehouse platforms" piece of the JD. In production this transform step
would be a real Apache Beam / Dataflow job; here it's a plain Python
function so the whole thing runs without a Dataflow cluster, but it's
structured as a discrete, testable transform stage so swapping it for a
Beam pipeline later is a drop-in replacement, not a rewrite.
"""
import os

import httpx

from pipeline.gcp_clients import publish_event, drain_events, write_rows

ERP_BASE_URL = os.getenv("ERP_BASE_URL", "http://localhost:8001")


def pull_from_erp(sku: str) -> dict:
    """Read the three ERP surfaces an agent cycle needs."""
    with httpx.Client(timeout=10) as client:
        inventory = client.get(f"{ERP_BASE_URL}/inventory/{sku}").json()
        orders = client.get(f"{ERP_BASE_URL}/orders/{sku}").json()
        pricing = client.get(f"{ERP_BASE_URL}/pricing/{sku}").json()
    return {"inventory": inventory, "orders": orders, "pricing": pricing}


def transform(raw: dict) -> dict:
    """Dataflow-equivalent transform: flatten + derive features used by the
    agents (avg daily demand, days of cover, current margin)."""
    history = raw["orders"]["history"]
    avg_daily_demand = sum(h["units_sold"] for h in history) / max(len(history), 1)
    on_hand = raw["inventory"]["on_hand"]
    days_of_cover = on_hand / avg_daily_demand if avg_daily_demand else float("inf")
    unit_cost = raw["pricing"]["unit_cost"]
    current_price = raw["pricing"]["current_price"]
    margin_pct = ((current_price - unit_cost) / current_price) * 100 if current_price else 0

    return {
        "sku": raw["inventory"]["sku"],
        "avg_daily_demand": round(avg_daily_demand, 2),
        "on_hand": on_hand,
        "reorder_point": raw["inventory"]["reorder_point"],
        "lead_time_days": raw["inventory"]["lead_time_days"],
        "days_of_cover": round(days_of_cover, 1),
        "unit_cost": unit_cost,
        "current_price": current_price,
        "margin_pct": round(margin_pct, 1),
        "history": history,
    }


def run_ingest_cycle(sku: str) -> dict:
    """Full pipeline: pull -> publish (Pub/Sub) -> drain+transform (Dataflow)
    -> write (BigQuery). Returns the transformed feature set agents consume."""
    raw = pull_from_erp(sku)
    publish_event({"event": "erp_pull", "sku": sku, "raw": raw})

    events = drain_events()
    features = None
    for evt in events:
        if evt["sku"] == sku and evt["event"] == "erp_pull":
            features = transform(evt["raw"])

    if features is None:
        features = transform(raw)

    write_rows("sku_features", [features])
    return features
