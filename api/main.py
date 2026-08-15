"""
Agent gateway API — the entry point that would sit in front of the agentic
system in production, with the escalation queue and audit trail exposed for
a human-in-the-loop review UI (see dashboard/app.py).
"""
from fastapi import FastAPI
from pydantic import BaseModel

from agents.orchestrator import run_cycle
from audit.audit_log import get_recent_decisions
from guardrails.monitor import get_escalations, clear_escalation

app = FastAPI(title="Agentic Supply Chain Copilot — Gateway", version="1.0")


class CycleRequest(BaseModel):
    sku: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/run-cycle")
def run_cycle_endpoint(req: CycleRequest):
    result = run_cycle(req.sku)
    return {
        "sku": req.sku,
        "outcome": result["outcome"],
        "forecast": result["forecast"],
        "pricing": result["pricing"],
        "supply": result["supply"],
        "guardrail_passed": result["guardrail_passed"],
        "guardrail_checks": result["guardrail_checks"],
        "guardrail_failures": result["guardrail_failures"],
    }


@app.get("/escalations")
def escalations():
    return get_escalations()


@app.post("/escalations/{sku}/resolve")
def resolve_escalation(sku: str):
    clear_escalation(sku)
    return {"sku": sku, "status": "resolved"}


@app.get("/audit-log")
def audit_log(limit: int = 50):
    return get_recent_decisions(limit)
