"""
Basic tests — run with: pytest tests/

Requires the mock ERP running on localhost:8001 for the ingest/agent tests
(test_guardrail_logic runs standalone with no dependencies).
"""
import pytest

from guardrails.monitor import check_cycle, MAX_PRICE_MOVE_PCT


def _fake_pricing(current, proposed, floor=1.0):
    return {"sku": "SKU-TEST", "current_price": current, "proposed_price": proposed, "min_price_floor": floor,
            "reason": "test"}


def _fake_forecast(days_of_cover=20, stockout_risk=False):
    return {"days_of_cover": days_of_cover, "stockout_risk": stockout_risk, "forecast_daily_demand": 10}


def _fake_supply(should_reorder=True):
    return {"should_reorder": should_reorder, "reorder_qty": 50}


def test_guardrail_passes_small_move():
    result = check_cycle(_fake_forecast(), _fake_pricing(10.0, 10.3), _fake_supply())
    assert result.passed is True


def test_guardrail_blocks_large_move():
    result = check_cycle(_fake_forecast(), _fake_pricing(10.0, 15.0), _fake_supply())
    assert result.passed is False
    assert any("exceeds safety limit" in f for f in result.failures)


def test_guardrail_blocks_below_floor():
    result = check_cycle(_fake_forecast(), _fake_pricing(10.0, 9.0, floor=9.5), _fake_supply())
    assert result.passed is False
    assert any("margin floor" in f for f in result.failures)


def test_guardrail_blocks_contradictory_signal():
    # raising price while heavily overstocked and no reorder needed
    forecast = _fake_forecast(days_of_cover=90)
    supply = _fake_supply(should_reorder=False)
    result = check_cycle(forecast, _fake_pricing(10.0, 10.5), supply)
    assert result.passed is False
    assert any("contradictory signals" in f for f in result.failures)


@pytest.mark.integration
def test_full_ingest_cycle():
    """Requires: uvicorn erp.mock_erp:app --port 8001 running separately."""
    from pipeline.ingest import run_ingest_cycle

    features = run_ingest_cycle("SKU-1042")
    assert features["sku"] == "SKU-1042"
    assert features["avg_daily_demand"] > 0
