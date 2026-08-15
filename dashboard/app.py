"""
Streamlit dashboard — agent decision history, escalation queue, and
cost/accuracy-style metrics. Talks to the FastAPI gateway (api/main.py),
never touches agents or the ERP directly, matching the same boundary a real
ops dashboard would respect.
"""
import os

import httpx
import pandas as pd
import plotly.express as px
import streamlit as st

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")

st.set_page_config(page_title="Agentic Supply Chain Copilot", layout="wide")
st.title("Agentic Supply Chain Copilot")
st.caption("Forecaster → Pricer → Supply Optimizer, gated by guardrails, logged to an audit trail.")

skus = ["SKU-1042", "SKU-2077", "SKU-3311"]

col_run, col_sku = st.columns([1, 3])
with col_sku:
    sku = st.selectbox("SKU", skus)
with col_run:
    st.write("")
    st.write("")
    run_clicked = st.button("Run agent cycle", type="primary")

if run_clicked:
    try:
        resp = httpx.post(f"{GATEWAY_URL}/run-cycle", json={"sku": sku}, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        if result["guardrail_passed"]:
            st.success(f"Outcome: {result['outcome']}")
        else:
            st.warning(f"Escalated to human review: {'; '.join(result['guardrail_failures'])}")

        c1, c2, c3 = st.columns(3)
        c1.metric("Forecast daily demand", result["forecast"]["forecast_daily_demand"])
        c2.metric("Proposed price", result["pricing"]["proposed_price"],
                   delta=round(result["pricing"]["proposed_price"] - result["pricing"]["current_price"], 2))
        c3.metric("Reorder qty", result["supply"]["reorder_qty"] if result["supply"]["should_reorder"] else 0)

        with st.expander("Guardrail checks"):
            for c in result["guardrail_checks"]:
                st.write(f"✓ {c}")
    except httpx.ConnectError:
        st.error(f"Can't reach gateway at {GATEWAY_URL}. Start it with: uvicorn api.main:app --port 8000")

st.divider()

tab1, tab2 = st.tabs(["Audit trail", "Escalation queue"])

with tab1:
    try:
        logs = httpx.get(f"{GATEWAY_URL}/audit-log", timeout=10).json()
        if logs:
            df = pd.DataFrame(
                [
                    {
                        "time": l["created_at"],
                        "sku": l["sku"],
                        "outcome": l["outcome"],
                        "guardrail_passed": l["guardrail_passed"],
                        "escalated": l["escalated"],
                    }
                    for l in logs
                ]
            )
            st.dataframe(df, use_container_width=True)

            outcome_counts = df["outcome"].value_counts().reset_index()
            outcome_counts.columns = ["outcome", "count"]
            fig = px.bar(outcome_counts, x="outcome", y="count", title="Decisions by outcome")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No decisions logged yet — run a cycle above.")
    except httpx.ConnectError:
        st.error(f"Can't reach gateway at {GATEWAY_URL}.")

with tab2:
    try:
        escalations = httpx.get(f"{GATEWAY_URL}/escalations", timeout=10).json()
        if escalations:
            for e in escalations:
                with st.container(border=True):
                    st.write(f"**{e['sku']}** — {e['reason']}")
                    st.caption(e["timestamp"])
                    if st.button(f"Resolve {e['sku']}", key=f"resolve_{e['sku']}_{e['timestamp']}"):
                        httpx.post(f"{GATEWAY_URL}/escalations/{e['sku']}/resolve", timeout=10)
                        st.rerun()
        else:
            st.success("No pending escalations.")
    except httpx.ConnectError:
        st.error(f"Can't reach gateway at {GATEWAY_URL}.")
