"""
LangGraph orchestrator: Forecaster -> Pricer & Supply Optimizer (parallel,
both depend on forecast) -> Guardrail -> apply-or-escalate.

This is the "autonomous agents for demand forecasting, pricing intelligence,
and supply chain optimization" piece of the JD, wired as an actual
multi-node agent graph rather than a linear script — matching the
plan/code/verify-style graphs already in this candidate's other projects.
"""
from typing import TypedDict

from langgraph.graph import StateGraph, END

from agents import forecaster_agent, pricer_agent, supply_optimizer_agent
from agents.mcp_server import call_tool
from audit.audit_log import log_decision
from guardrails.monitor import check_cycle
from pipeline.ingest import run_ingest_cycle


class CycleState(TypedDict, total=False):
    sku: str
    features: dict
    forecast: dict
    pricing: dict
    supply: dict
    guardrail_passed: bool
    guardrail_checks: list
    guardrail_failures: list
    outcome: str


def node_ingest(state: CycleState) -> CycleState:
    features = run_ingest_cycle(state["sku"])
    return {"features": features}


def node_forecast(state: CycleState) -> CycleState:
    return {"forecast": forecaster_agent.run(state["sku"])}


def node_pricing(state: CycleState) -> CycleState:
    return {"pricing": pricer_agent.run(state["sku"], state["forecast"])}


def node_supply(state: CycleState) -> CycleState:
    return {"supply": supply_optimizer_agent.run(state["sku"], state["forecast"])}


def node_guardrail(state: CycleState) -> CycleState:
    result = check_cycle(state["forecast"], state["pricing"], state["supply"])
    return {
        "guardrail_passed": result.passed,
        "guardrail_checks": result.checks,
        "guardrail_failures": result.failures,
    }


def node_apply_or_escalate(state: CycleState) -> CycleState:
    sku = state["sku"]
    if state["guardrail_passed"]:
        proposed = state["pricing"]["proposed_price"]
        if proposed != state["pricing"]["current_price"]:
            try:
                call_tool("pricer", "update_pricing", sku=sku, new_price=proposed,
                          reason=state["pricing"]["reason"])
                outcome = f"applied: price -> {proposed}"
            except Exception as e:  # ERP itself refused it — belt and braces
                outcome = f"erp_rejected: {e}"
        else:
            outcome = "no_change_needed"
    else:
        outcome = "escalated_to_human"

    all_sources = (
        state["forecast"]["sources"] + state["pricing"]["sources"] + state["supply"]["sources"]
    )
    log_decision(
        sku=sku,
        cycle={
            "forecast": state["forecast"],
            "pricing": state["pricing"],
            "supply": state["supply"],
            "guardrail_checks": state["guardrail_checks"],
            "guardrail_failures": state["guardrail_failures"],
        },
        guardrail_passed=state["guardrail_passed"],
        escalated=not state["guardrail_passed"],
        outcome=outcome,
        sources=sorted(set(all_sources)),
    )
    return {"outcome": outcome}


def build_graph():
    graph = StateGraph(CycleState)
    graph.add_node("ingest", node_ingest)
    graph.add_node("forecast_step", node_forecast)
    graph.add_node("pricing_step", node_pricing)
    graph.add_node("supply_step", node_supply)
    graph.add_node("guardrail_step", node_guardrail)
    graph.add_node("apply_or_escalate", node_apply_or_escalate)

    graph.set_entry_point("ingest")
    graph.add_edge("ingest", "forecast_step")
    # pricing and supply both fan out from forecast, fan back in at guardrail
    graph.add_edge("forecast_step", "pricing_step")
    graph.add_edge("forecast_step", "supply_step")
    graph.add_edge("pricing_step", "guardrail_step")
    graph.add_edge("supply_step", "guardrail_step")
    graph.add_edge("guardrail_step", "apply_or_escalate")
    graph.add_edge("apply_or_escalate", END)

    return graph.compile()


_compiled_graph = None


def run_cycle(sku: str) -> dict:
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    final_state = _compiled_graph.invoke({"sku": sku})
    return final_state