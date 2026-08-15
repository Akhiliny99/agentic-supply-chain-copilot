# Agentic Supply Chain Copilot

A multi-agent AI system for demand forecasting, dynamic pricing, and supply
chain optimization — built to demonstrate production-grade agentic AI
infrastructure: agent orchestration, MCP tool exposure, ERP integration,
least-privilege access, guardrails/kill-switch, and an audit trail.

Runs **fully locally with zero API keys** (mock LLM + mock GCP + mock ERP).
Every mock component has a matching "real" implementation path you can flip
on with one env var — see `pipeline/gcp_clients.py` and `agents/llm_client.py`.

## Architecture

```
                        ┌─────────────────────┐
   Mock ERP (FastAPI)   │  inventory / orders  │
   (stand-in for SAP /  │  / pricing endpoints │
    Oracle ERP)         └──────────┬───────────┘
                                    │ REST
                                    ▼
                        ┌─────────────────────┐
                        │   MCP Tool Server    │  ← least-privilege:
                        │  (agents/mcp_server) │    each agent only gets
                        └──────────┬───────────┘    the tools it's scoped for
                                    │
        ┌───────────────────────────────────────────────┐
        │              LangGraph Orchestrator            │
        │                                                 │
        │   Forecaster ──► Pricer ──► Supply Optimizer   │
        │        │             │             │            │
        │        └─────────────┴─────────────┘            │
        │                      ▼                           │
        │              Guardrail / Monitor                 │
        │        (confidence check + kill-switch)           │
        │                      │                            │
        │           pass ◄─────┴─────► escalate to human    │
        └───────────────────────────────────────────────┘
                                    │
                                    ▼
                        ┌─────────────────────┐
                        │     Audit Trail      │  (SQLite locally,
                        │  every decision +    │   stand-in for
                        │  data source logged  │   BigQuery)
                        └──────────┬───────────┘
                                    │
                                    ▼
                        ┌─────────────────────┐
                        │  Streamlit Dashboard │
                        │  decisions, cost,     │
                        │  accuracy, escalations│
                        └─────────────────────┘
```

## Maps directly to the job description

| JD requirement | Where it lives |
|---|---|
| Agent orchestration / tool-use (MCP) | `agents/mcp_server.py`, `agents/orchestrator.py` |
| Least-privilege agent permissions | `agents/mcp_server.py` — `AGENT_SCOPES` |
| ERP integration | `erp/mock_erp.py` (swap for real SAP/Oracle client) |
| GCP / lakehouse (BigQuery, Dataflow, Pub/Sub, Vertex AI) | `pipeline/gcp_clients.py`, `pipeline/ingest.py` |
| Guardrails, hallucination checks | `guardrails/monitor.py` |
| Kill-switch / escalation path | `guardrails/monitor.py` — `escalate()` |
| Audit trail / responsible-AI documentation | `audit/audit_log.py` |
| Cost-per-query / accuracy metrics | `dashboard/app.py` |

## Run it

```bash
pip install -r requirements.txt

# 1. start the mock ERP
uvicorn erp.mock_erp:app --port 8001 &

# 2. start the agent gateway
uvicorn api.main:app --port 8000 &

# 3. run one agent cycle
curl -X POST http://localhost:8000/run-cycle -d '{"sku": "SKU-1042"}' -H "Content-Type: application/json"

# 4. view the dashboard
streamlit run dashboard/app.py
```

## Switching to real GCP / Vertex AI

Set `USE_REAL_GCP=true` and provide `GOOGLE_APPLICATION_CREDENTIALS` — see
`pipeline/gcp_clients.py`. The BigQuery writer, Pub/Sub publisher, and
Vertex AI model call are already written; they're just gated off by default
so the project runs without any cloud account.

## Switching to a real LLM

Set `LLM_PROVIDER=groq` (or `vertex`) and the matching API key — see
`agents/llm_client.py`. Default is `LLM_PROVIDER=mock`, a deterministic
rule-based stand-in so the whole pipeline runs offline.
