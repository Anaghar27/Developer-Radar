import pandas as pd
import streamlit as st

from dashboard.api_client import api_get, api_post


def render():
    st.header("🧠 Intelligence Reports")
    st.caption("Ask natural language questions — powered by Corrective RAG")

    # ── Query input ───────────────────────────────────────────────────────────
    st.subheader("Ask a Question")

    with st.form("rag_query_form"):
        query = st.text_area(
            "Your question",
            placeholder="e.g. What are developers saying about PyTorch vs TensorFlow this month?",
            height=100,
        )
        col1, col2 = st.columns([3, 1])
        with col1:
            limit = st.slider("Max sources to retrieve", min_value=3, max_value=20, value=10)
        with col2:
            submitted = st.form_submit_button("Generate Report", use_container_width=True)

    if submitted and query.strip():
        with st.spinner("Running Corrective RAG pipeline... (first query may take 30-60s)"):
            result = api_post("/query", {"query": query.strip(), "limit": limit})
        if result:
            st.session_state["rag_result"] = result

    elif submitted:
        st.warning("Please enter a question.")

    # ── Suggested queries ─────────────────────────────────────────────────────
    st.divider()
    st.subheader("Suggested Questions")

    suggestions = [
        "What are the most discussed ML tools this week?",
        "How do developers feel about Rust vs Python?",
        "What are the top frustrations with Kubernetes?",
        "Which AI tools are generating the most excitement?",
        "What career topics are trending in the developer community?",
    ]

    cols = st.columns(2)
    for i, suggestion in enumerate(suggestions):
        with cols[i % 2]:
            if st.button(suggestion, key=f"suggestion_{i}", use_container_width=True):
                st.session_state["suggested_query"] = suggestion
                st.rerun()

    # Handle suggested query click
    if "suggested_query" in st.session_state:
        sq = st.session_state.pop("suggested_query")
        with st.spinner(f"Running query: '{sq}'..."):
            result = api_post("/query", {"query": sq, "limit": 10})
        if result:
            st.session_state["rag_result"] = result

    # ── Display result (persists across reruns via session state) ─────────────
    result = st.session_state.get("rag_result")
    if result:
        if result.get("cached"):
            st.success("⚡ Served from cache")
        else:
            st.success("✅ Fresh report generated")

        st.subheader("Report")
        st.markdown(result["report"])

        st.caption(
            "This report is grounded entirely in posts fetched from Hacker News and Reddit — the model cannot fabricate claims. "
            "Each paragraph cites [1], [2] etc. referring to the source URLs listed below."
        )

        sources = result.get("sources_used", [])
        if sources:
            st.subheader(f"Sources ({len(sources)})")
            for i, src in enumerate(sources, 1):
                if src.startswith("http"):
                    st.markdown(f"{i}. [{src}]({src})")
                else:
                    st.markdown(f"{i}. `{src}`")

        with st.expander("Report metadata"):
            st.json({
                "query": result.get("query"),
                "generated_at": result.get("generated_at"),
                "cached": result.get("cached"),
                "sources_count": len(sources),
            })

    # ── Alerts section ────────────────────────────────────────────────────────
    st.divider()
    st.subheader("🚨 Volume Spike Alerts")

    alerts_data = api_get("/alerts", params={"limit": 10})
    if alerts_data and alerts_data.get("alerts"):
        df = pd.DataFrame(alerts_data["alerts"])
        df["triggered_at"] = pd.to_datetime(df["triggered_at"])
        st.dataframe(
            df[["topic", "today_count", "rolling_avg", "pct_increase", "triggered_at"]],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No volume spike alerts detected recently.")
