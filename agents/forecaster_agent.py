"""Forecaster agent: predicts near-term demand from ERP order history.

Scoped (via MCP) to read-only tools: get_inventory, get_orders. It cannot
touch pricing — least-privilege by design.
"""
from agents.llm_client import complete
from agents.mcp_server import call_tool


def naive_forecast(history: list[dict], horizon: int = 7) -> float:
    """Simple moving-average forecast — deterministic, no LLM needed for the
    numeric prediction itself. The LLM is used for the *reasoning/narrative*
    layer on top, which is where hallucination risk actually lives."""
    if not history:
        return 0.0
    recent = [h["units_sold"] for h in history[-14:]]
    return round(sum(recent) / len(recent), 1)


def run(sku: str) -> dict:
    inventory = call_tool("forecaster", "get_inventory", sku=sku)
    orders = call_tool("forecaster", "get_orders", sku=sku)

    forecast_daily = naive_forecast(orders["history"])
    days_of_cover = inventory["on_hand"] / forecast_daily if forecast_daily else float("inf")
    stockout_risk = days_of_cover < inventory["lead_time_days"]

    narrative = complete(
        system_prompt="You are a demand forecasting analyst. Be concise and cite the numbers.",
        user_prompt=(
            f"SKU {sku}: forecast daily demand {forecast_daily}, on-hand {inventory['on_hand']}, "
            f"lead time {inventory['lead_time_days']} days. Assess stockout risk."
        ),
    )

    return {
        "agent": "forecaster",
        "sku": sku,
        "forecast_daily_demand": forecast_daily,
        "days_of_cover": round(days_of_cover, 1),
        "stockout_risk": stockout_risk,
        "narrative": narrative,
        "sources": ["erp:get_inventory", "erp:get_orders"],
    }
