import pandas as pd
import streamlit as st

from dashboard.api_client import api_get
from dashboard.components.charts import (
    metric_row,
    sentiment_bar_chart,
    sentiment_line_chart,
    tool_comparison_chart,
)
from dashboard.components.filters import days_filter


def render():
    st.header("🛠️ Tool Tracker")
    st.caption("Side-by-side tool sentiment from mart_tool_comparison")

    col1, col2 = st.columns(2)
    with col2:
        days = days_filter("tt_days", default=30)

    # Fetch all available tools for the selected time window first
    all_data = api_get("/tools/compare", params={"days": days})
    if not all_data or not all_data.get("tools"):
        st.info("No tool data available for this time window.")
        return

    # Rank tools by total post count — show only top 50 in the multiselect
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
            "Compare specific tools (leave empty to see overall trend)",
            options=top_tools,
            key="tt_tools",
        )

    df = pd.DataFrame(all_data["data"])
    df["post_date"] = pd.to_datetime(df["post_date"])

    if df.empty:
        st.info("No data for the selected time window.")
        return

    unique_tools = df["tool"].unique().tolist()

    # Metrics always reflect all tools in the window
    best_tool = df.groupby("tool")["avg_sentiment"].mean().idxmax()
    most_discussed = df.groupby("tool")["post_count"].sum().idxmax()
    metric_row([
        {"label": "Tools Tracked", "value": len(unique_tools)},
        {"label": "Most Positive Tool", "value": best_tool},
        {"label": "Most Discussed Tool", "value": most_discussed},
        {"label": "Total Posts", "value": int(df["post_count"].sum())},
    ])

    st.divider()

    if selected_tools:
        # Compare mode: individual line per selected tool
        chart_df = df[df["tool"].isin(selected_tools)]
        if chart_df.empty:
            st.info("No data for the selected tools.")
            return
        tool_comparison_chart(chart_df, title="Tool Sentiment Comparison Over Time")
        st.caption(
            "Each line tracks one tool's average daily sentiment (−1 = very negative, +1 = very positive). "
            "Converging lines mean communities agree; diverging lines reveal tool-specific shifts."
        )

        # Sentiment breakdown for selected tools
        tool_summary = chart_df.groupby("tool").agg(
            avg_sentiment=("avg_sentiment", "mean"),
            positive_count=("positive_count", "sum"),
            negative_count=("negative_count", "sum"),
            neutral_count=("neutral_count", "sum"),
            post_count=("post_count", "sum"),
        ).reset_index()
        sentiment_bar_chart(tool_summary, x_col="tool", title="Sentiment Breakdown by Tool")
        st.caption(
            "Stacked bars show the total positive / neutral / negative post count per tool. "
            "Taller green bars = stronger positive reception; taller red bars = more frustration."
        )

        with st.expander("View raw data"):
            st.dataframe(chart_df, use_container_width=True, hide_index=True)

    else:
        # Default mode: aggregate all tools into a single combined trend line
        combined = (
            df.groupby("post_date")
            .agg(avg_sentiment=("avg_sentiment", "mean"))
            .reset_index()
            .rename(columns={"post_date": "post_date"})
        )
        sentiment_line_chart(combined, title="Overall Tool Sentiment Trend")
        st.caption(
            "Combined average daily sentiment across all tracked tools. "
            "Select specific tools above to compare their individual trends side by side."
        )

        # Sentiment breakdown for top 10 most-discussed tools
        top10 = (
            all_df_temp.groupby("tool")["post_count"]
            .sum()
            .sort_values(ascending=False)
            .head(10)
            .index.tolist()
        )
        top10_df = df[df["tool"].isin(top10)]
        tool_summary = top10_df.groupby("tool").agg(
            avg_sentiment=("avg_sentiment", "mean"),
            positive_count=("positive_count", "sum"),
            negative_count=("negative_count", "sum"),
            neutral_count=("neutral_count", "sum"),
            post_count=("post_count", "sum"),
        ).reset_index()
        sentiment_bar_chart(tool_summary, x_col="tool", title="Sentiment Breakdown — Top 10 Tools")
        st.caption(
            "Stacked bars show positive / neutral / negative post counts for the 10 most-discussed tools. "
            "Select tools above to drill into any specific tool."
        )

        with st.expander("View raw data"):
            st.dataframe(df, use_container_width=True, hide_index=True)
