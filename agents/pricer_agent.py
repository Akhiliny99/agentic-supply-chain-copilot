"""Pricer agent: recommends a price adjustment from current margin +
demand signal. This is the only agent scoped for the write tool
(update_pricing) — and even it doesn't call it directly; the write only
happens after the guardrail/monitor approves (see agents/orchestrator.py).
"""
from agents.llm_client import complete
from agents.mcp_server import call_tool


def run(sku: str, forecast_result: dict) -> dict:
    pricing = call_tool("pricer", "get_pricing", sku=sku)

    current_price = pricing["current_price"]
    unit_cost = pricing["unit_cost"]
    min_price = round(unit_cost * (1 + pricing["min_margin_pct"] / 100), 2)

    # simple elasticity heuristic: tight stock -> nudge price up, excess -> nudge down
    if forecast_result["stockout_risk"]:
        proposed_price = round(current_price * 1.05, 2)
        reason = "Stockout risk detected — demand outpacing supply, nudging price up 5%."
    elif forecast_result["days_of_cover"] > 45:
        proposed_price = round(current_price * 0.97, 2)
        reason = "Excess inventory cover (>45 days) — nudging price down 3% to move stock."
    else:
        proposed_price = current_price
        reason = "Demand and inventory balanced — no price change recommended."

    proposed_price = max(proposed_price, min_price)

    narrative = complete(
        system_prompt="You are a pricing analyst. Justify the recommendation against margin floor.",
        user_prompt=(
            f"SKU {sku}: current {current_price}, cost {unit_cost}, min price {min_price}, "
            f"proposed {proposed_price}. Reason: {reason}"
        ),
    )

    return {
        "agent": "pricer",
        "sku": sku,
        "current_price": current_price,
        "proposed_price": proposed_price,
        "min_price_floor": min_price,
        "reason": reason,
        "narrative": narrative,
        "sources": ["erp:get_pricing", "forecaster_agent"],
    }
