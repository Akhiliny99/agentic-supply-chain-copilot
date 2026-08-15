"""Supply Optimizer agent: recommends reorder quantity/timing from
forecasted demand + current inventory. Read-only scope — never touches
pricing or places real purchase orders (that write path isn't built here
on purpose, mirroring the JD's least-privilege / kill-switch emphasis:
an agent shouldn't get a capability its task doesn't require)."""
from agents.llm_client import complete
from agents.mcp_server import call_tool


def run(sku: str, forecast_result: dict) -> dict:
    inventory = call_tool("supply_optimizer", "get_inventory", sku=sku)

    lead_time = inventory["lead_time_days"]
    daily_demand = forecast_result["forecast_daily_demand"]
    safety_stock = round(daily_demand * 3)  # 3 days buffer
    reorder_qty = 0
    should_reorder = inventory["on_hand"] <= inventory["reorder_point"]

    if should_reorder:
        # cover the lead time window plus safety stock, minus what's on hand
        reorder_qty = max(0, round(daily_demand * lead_time + safety_stock - inventory["on_hand"]))

    narrative = complete(
        system_prompt="You are a supply chain planner. Recommend reorder quantity and justify it.",
        user_prompt=(
            f"SKU {sku}: on-hand {inventory['on_hand']}, reorder point {inventory['reorder_point']}, "
            f"lead time {lead_time} days, forecast daily demand {daily_demand}."
        ),
    )

    return {
        "agent": "supply_optimizer",
        "sku": sku,
        "should_reorder": should_reorder,
        "reorder_qty": reorder_qty,
        "lead_time_days": lead_time,
        "safety_stock": safety_stock,
        "narrative": narrative,
        "sources": ["erp:get_inventory", "forecaster_agent"],
    }
