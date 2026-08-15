"""
Mock ERP system — stands in for a real SAP / Oracle ERP REST layer.

In a real deployment, this file is replaced by an ERP adapter (e.g. SAP OData
services, Oracle Fusion REST API) behind the SAME interface used below:
GET /inventory/{sku}, GET /orders/{sku}, GET/POST /pricing/{sku}.
Keeping the interface identical means the agents in agents/ never need to
change — only this adapter does. That's the integration boundary the JD
calls out ("connect agents securely to ERP, data platform, and third-party
tools").
"""
import random
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Mock ERP", version="1.0")

# --- seed data: a handful of SKUs with deterministic-ish history ---
random.seed(42)
SKUS = {
    "SKU-1042": {"name": "Industrial Bearing 40mm", "base_demand": 120, "unit_cost": 8.5},
    "SKU-2077": {"name": "Hydraulic Seal Kit", "base_demand": 60, "unit_cost": 22.0},
    "SKU-3311": {"name": "Steel Coupling Flange", "base_demand": 200, "unit_cost": 4.25},
}


def _gen_history(sku: str, days: int = 30):
    base = SKUS[sku]["base_demand"]
    today = datetime.utcnow().date()
    history = []
    for i in range(days, 0, -1):
        d = today - timedelta(days=i)
        noise = random.randint(-15, 15)
        weekday_boost = 20 if d.weekday() < 5 else -10
        history.append({"date": d.isoformat(), "units_sold": max(0, base + noise + weekday_boost)})
    return history


class PriceUpdate(BaseModel):
    new_price: float
    reason: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/inventory/{sku}")
def get_inventory(sku: str):
    if sku not in SKUS:
        raise HTTPException(404, f"Unknown SKU {sku}")
    on_hand = random.randint(50, 500)
    return {
        "sku": sku,
        "name": SKUS[sku]["name"],
        "on_hand": on_hand,
        "reorder_point": 100,
        "lead_time_days": random.choice([7, 14, 21]),
    }


@app.get("/orders/{sku}")
def get_order_history(sku: str, days: int = 30):
    if sku not in SKUS:
        raise HTTPException(404, f"Unknown SKU {sku}")
    return {"sku": sku, "history": _gen_history(sku, days)}


@app.get("/pricing/{sku}")
def get_pricing(sku: str):
    if sku not in SKUS:
        raise HTTPException(404, f"Unknown SKU {sku}")
    unit_cost = SKUS[sku]["unit_cost"]
    return {
        "sku": sku,
        "unit_cost": unit_cost,
        "current_price": round(unit_cost * 1.6, 2),
        "min_margin_pct": 15,
    }


@app.post("/pricing/{sku}")
def update_pricing(sku: str, update: PriceUpdate):
    """Write endpoint — this is the one an agent needs WRITE scope for.
    Everything above is read-only and safe for any agent to call."""
    if sku not in SKUS:
        raise HTTPException(404, f"Unknown SKU {sku}")
    unit_cost = SKUS[sku]["unit_cost"]
    min_price = unit_cost * 1.15
    if update.new_price < min_price:
        raise HTTPException(400, f"Price {update.new_price} violates min margin (floor {min_price:.2f})")
    return {"sku": sku, "accepted_price": update.new_price, "reason": update.reason, "status": "applied"}
