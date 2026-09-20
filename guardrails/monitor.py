
from dataclasses import dataclass, field
from datetime import datetime

MAX_PRICE_MOVE_PCT = 8.0  


@dataclass
class GuardrailResult:
    passed: bool
    checks: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    escalated: bool = False
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())



_escalation_queue: list[dict] = []


def check_cycle(forecast_result: dict, pricing_result: dict, supply_result: dict) -> GuardrailResult:
    checks, failures = [], []

   
    current = pricing_result["current_price"]
    proposed = pricing_result["proposed_price"]
    move_pct = abs(proposed - current) / current * 100 if current else 0
    checks.append(f"price move {move_pct:.1f}% (limit {MAX_PRICE_MOVE_PCT}%)")
    if move_pct > MAX_PRICE_MOVE_PCT:
        failures.append(f"Proposed price move {move_pct:.1f}% exceeds safety limit {MAX_PRICE_MOVE_PCT}%")

    
    checks.append(f"price floor {pricing_result['min_price_floor']} vs proposed {proposed}")
    if proposed < pricing_result["min_price_floor"]:
        failures.append("Proposed price is below the ERP's minimum margin floor")


    checks.append("cross-agent consistency: price direction vs inventory signal")
    raising_price = proposed > current
    heavy_overstock = supply_result["should_reorder"] is False and forecast_result["days_of_cover"] > 60
    if raising_price and heavy_overstock:
        failures.append(
            "Pricer wants to raise price while Supply Optimizer reports heavy overstock "
            f"({forecast_result['days_of_cover']} days of cover) — contradictory signals"
        )

    passed = len(failures) == 0
    result = GuardrailResult(passed=passed, checks=checks, failures=failures, escalated=not passed)

    if not passed:
        _escalation_queue.append(
            {
                "sku": pricing_result["sku"],
                "reason": "; ".join(failures),
                "forecast": forecast_result,
                "pricing": pricing_result,
                "supply": supply_result,
                "timestamp": result.timestamp,
            }
        )

    return result


def get_escalations() -> list[dict]:
    return list(_escalation_queue)


def clear_escalation(sku: str) -> None:
    """Human reviewer resolves/dismisses an escalation."""
    global _escalation_queue
    _escalation_queue = [e for e in _escalation_queue if e["sku"] != sku]
