"""Developer Radar — LLM Admin tab (admin users only)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.api_client import api_get
from dashboard.components.charts import section_header


def render() -> None:
    """
    Render LLM cost and quality monitor.
    This function is only called when the current user is an admin —
    the tab itself is not added to st.tabs() for non-admin users.
    """
    section_header(
        "🤖",
        "LLM Cost & Quality Monitor",
        "Real-time LLM usage, cost, and performance across all operations.",
    )

    col_refresh, col_reset, _ = st.columns([1, 1, 6])
    do_reset = False
    with col_refresh:
        if st.button("🔄 Refresh", use_container_width=True):
            st.cache_data.clear()
    with col_reset:
        if st.button("🗑️ Reset Stats", use_container_width=True, type="secondary"):
            do_reset = True

    params = {"reset": "true"} if do_reset else {}
    with st.spinner("Loading LLM stats..."):
        data = api_get("/admin/me/llm-stats", params=params)

    if data is None:
        # api_get already showed the error — nothing more to do
        return

    if do_reset:
        st.success("✅ Stats reset successfully.")

    # ── Top metrics ───────────────────────────────────────────────────────────
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total LLM Calls", f"{data['total_calls']:,}")
    m2.metric("Total Cost", f"${data['total_cost_usd']:.6f}")
    m3.metric("Success Rate", f"{data['success_rate'] * 100:.1f}%")
    m4.metric("Avg Latency", f"{data['avg_latency_ms']:.0f} ms")

    st.markdown("---")

    # ── By Operation ──────────────────────────────────────────────────────────
    st.subheader("By Operation")
    by_op = data.get("by_operation", {})
    if by_op:
        rows = []
        for op, s in by_op.items():
            calls = s.get("calls", 0)
            rows.append({
                "Operation": op,
                "Calls": calls,
                "Failures": s.get("failures", 0),
                "Cost (USD)": f"${s.get('cost_usd', 0):.6f}",
                "Avg Latency (ms)": round(s.get("total_latency_ms", 0) / calls, 1) if calls else 0,
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("No operation data yet — make some API calls first.")

    # ── By Provider ───────────────────────────────────────────────────────────
    st.subheader("By Provider")
    by_prov = data.get("by_provider", {})
    if by_prov:
        rows = []
        for provider, s in by_prov.items():
            calls = s.get("calls", 0)
            failures = s.get("failures", 0)
            rows.append({
                "Provider": provider,
                "Calls": calls,
                "Failures": failures,
                "Cost (USD)": f"${s.get('cost_usd', 0):.6f}",
                "Failure Rate (%)": round((failures / calls) * 100, 1) if calls else 0,
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("No provider data yet.")

    st.markdown("---")
    st.caption(f"Snapshot taken at: {data.get('snapshot_taken_at', 'unknown')}")
    st.caption("Stats are aggregated from the shared PostgreSQL LLM call log.")
