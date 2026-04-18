"""Lumina — Tool Tracker tab."""
import pandas as pd
import streamlit as st

from dashboard.api_client import api_get, api_post
from dashboard.components.charts import (
    filters_label,
    metric_row,
    section_header,
    sentiment_bar_chart,
    sentiment_line_chart,
    tool_comparison_chart,
)
from dashboard.components.filters import days_filter


def render() -> None:
    section_header(
        "🛠️",
        "Tool Tracker",
        "Side-by-side tool sentiment comparison — see which tools developers love, hate, or are buzzing about.",
    )

    # ── Filters ───────────────────────────────────────────────────────────────
    filters_label()
    col1, col2 = st.columns(2)
    window = api_get("/tools/window") or {}
    max_lookback_days = max(1, int(window.get("max_lookback_days", 1)))
    if "tt_days" in st.session_state and int(st.session_state["tt_days"]) > max_lookback_days:
        st.session_state["tt_days"] = max_lookback_days
    with col2:
        days = days_filter(
            "tt_days",
            default=min(28, max_lookback_days),
            min_value=1,
            max_value=max_lookback_days,
            step=1,
        )

    all_data = api_get("/tools/compare", params={"days": days})
    if not all_data or not all_data.get("tools"):
        st.info("No tool data available for this time window.")
        return

    all_df_temp = pd.DataFrame(all_data["data"])
    top_tools = (
        all_df_temp.groupby("tool")["post_count"]
        .sum()
        .sort_values(ascending=False)
        .head(50)
        .index.tolist()
    )

    with col1:
        selected_tools = st.multiselect(
            "Compare specific tools (leave empty for overall trend)",
            options=top_tools,
            key="tt_tools",
        )

    df = pd.DataFrame(all_data["data"])
    df["post_date"] = pd.to_datetime(df["post_date"])

    if df.empty:
        st.info("No data for the selected time window.")
        return

    unique_tools = df["tool"].unique().tolist()
    best_tool = df.groupby("tool")["avg_sentiment"].mean().idxmax()
    most_disc = df.groupby("tool")["post_count"].sum().idxmax()

    # ── Metrics ───────────────────────────────────────────────────────────────
    metric_row([
        {"label": "Tools Tracked",      "value": len(unique_tools)},
        {"label": "Most Positive Tool", "value": best_tool},
        {"label": "Most Discussed",     "value": most_disc},
        {"label": "Total Posts",        "value": f"{int(df['post_count'].sum()):,}"},
    ])

    st.divider()

    # ── Charts ────────────────────────────────────────────────────────────────
    if selected_tools:
        chart_df = df[df["tool"].isin(selected_tools)]
        if chart_df.empty:
            st.info("No data for the selected tools.")
            return

        selected_tools_sorted = sorted(selected_tools)
        report_scope_key = f"{','.join(selected_tools_sorted)}|{days}"

        st.markdown("### Tool Decision Report")
        st.caption(
            "Generate a concise LLM summary from the selected tools and current time window."
        )
        context_value = st.text_area(
            "Optional decision context",
            value=st.session_state.get("tt_report_context", ""),
            placeholder="Example: choosing a framework for a production computer-vision stack",
            max_chars=500,
            key="tt_report_context",
        )
        report_col, meta_col = st.columns([1, 3])
        with report_col:
            generate_report = st.button(
                "Generate Report",
                key="tt_generate_report",
                use_container_width=True,
            )
        with meta_col:
            st.caption(
                f"Scope: {', '.join(selected_tools_sorted)} over the last {days} days."
            )

        if generate_report:
            with st.spinner("Generating tool decision report..."):
                report_result = api_post(
                    "/tools/report",
                    {
                        "tools": selected_tools_sorted,
                        "days": days,
                        "context": context_value.strip() or None,
                    },
                )
            if report_result:
                st.session_state["tt_report_result"] = report_result
                st.session_state["tt_report_scope_key"] = report_scope_key

        report_result = (
            st.session_state.get("tt_report_result")
            if st.session_state.get("tt_report_scope_key") == report_scope_key
            else None
        )
        if report_result:
            st.markdown(report_result.get("narrative", ""))
            stats_summary = report_result.get("stats_summary") or []
            if stats_summary:
                st.dataframe(
                    pd.DataFrame(stats_summary),
                    use_container_width=True,
                    hide_index=True,
                )
            st.caption(
                f"Generated at {report_result.get('generated_at', 'unknown')} using {report_result.get('model_used', 'unknown')}."
            )

        st.divider()

        tool_comparison_chart(chart_df, title="Tool Sentiment Comparison Over Time")
        st.caption(
            "Each line tracks one tool's average daily sentiment (−1 = very negative, +1 = very positive). "
            "Converging lines mean communities agree; diverging lines reveal tool-specific mood shifts."
        )

        tool_summary = (
            chart_df.groupby("tool")
            .agg(
                avg_sentiment=("avg_sentiment",  "mean"),
                positive_count=("positive_count", "sum"),
                negative_count=("negative_count", "sum"),
                neutral_count=("neutral_count",  "sum"),
                post_count=("post_count",    "sum"),
            )
            .reset_index()
        )
        sentiment_bar_chart(tool_summary, x_col="tool", title="Sentiment Breakdown by Tool")
        st.caption(
            "Stacked bars show total positive / neutral / negative posts per tool. "
            "Taller green bars = stronger positive reception; taller red bars = more frustration."
        )

        with st.expander("View raw data"):
            st.dataframe(chart_df, use_container_width=True, hide_index=True)

    else:
        combined = (
            df.groupby("post_date")
            .agg(avg_sentiment=("avg_sentiment", "mean"))
            .reset_index()
        )
        sentiment_line_chart(combined, title="Overall Tool Sentiment Trend")
        st.caption(
            "Combined average daily sentiment across all tracked tools. "
            "Select specific tools above to compare their individual trends side by side."
        )

        top10 = (
            all_df_temp.groupby("tool")["post_count"]
            .sum()
            .sort_values(ascending=False)
            .head(10)
            .index.tolist()
        )
        top10_df = df[df["tool"].isin(top10)]
        tool_summary = (
            top10_df.groupby("tool")
            .agg(
                avg_sentiment=("avg_sentiment",  "mean"),
                positive_count=("positive_count", "sum"),
                negative_count=("negative_count", "sum"),
                neutral_count=("neutral_count",  "sum"),
                post_count=("post_count",    "sum"),
            )
            .reset_index()
        )
        sentiment_bar_chart(tool_summary, x_col="tool", title="Sentiment Breakdown — Top 10 Tools")
        st.caption(
            "Positive / neutral / negative post counts for the 10 most-discussed tools. "
            "Select tools in the filter above to drill into any specific comparison."
        )

        with st.expander("View raw data"):
            st.dataframe(df, use_container_width=True, hide_index=True)
