"""
Guardrail / monitor layer — this is the JD's "monitoring, guardrails, and a
defined kill-switch/escalation path for autonomous workflows" requirement.

Checks applied before any agent decision is allowed to act (e.g. before the
Pricer's proposed_price is actually written to the ERP):

1. Sanity bounds — is the proposed change within a safe percentage move?
2. Margin floor — does it violate the ERP's own minimum margin? (defense in
   depth: the ERP already rejects this, but we want to catch it *before*
   attempting the write, and log why.)
3. Cross-agent consistency — does the Pricer's move contradict what the
   Supply Optimizer sees (e.g. raising price while flagging massive
   overstock)?

If any check fails, the cycle is NOT auto-applied — it's queued for human
escalation instead. This is the kill-switch: the system defaults to
"stop and ask a human" rather than "act anyway."
"""
from dataclasses import dataclass, field
from datetime import datetime

MAX_PRICE_MOVE_PCT = 8.0  # a single automated cycle may not move price >8%


@dataclass
class GuardrailResult:
    passed: bool
    checks: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    escalated: bool = False
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


# In-memory escalation queue. In production this would push to Slack/email/
# a ticketing system and persist to a durable store.
_escalation_queue: list[dict] = []


def check_cycle(forecast_result: dict, pricing_result: dict, supply_result: dict) -> GuardrailResult:
    checks, failures = [], []

    # 1. sanity bound on price move
    current = pricing_result["current_price"]
    proposed = pricing_result["proposed_price"]
    move_pct = abs(proposed - current) / current * 100 if current else 0
    checks.append(f"price move {move_pct:.1f}% (limit {MAX_PRICE_MOVE_PCT}%)")
    if move_pct > MAX_PRICE_MOVE_PCT:
        failures.append(f"Proposed price move {move_pct:.1f}% exceeds safety limit {MAX_PRICE_MOVE_PCT}%")

    # 2. margin floor (defense in depth vs ERP's own check)
    checks.append(f"price floor {pricing_result['min_price_floor']} vs proposed {proposed}")
    if proposed < pricing_result["min_price_floor"]:
        failures.append("Proposed price is below the ERP's minimum margin floor")

    # 3. cross-agent consistency: don't raise price while sitting on huge overstock
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
