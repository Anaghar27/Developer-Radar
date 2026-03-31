import streamlit as st
import pandas as pd
from dashboard.api_client import api_get
from dashboard.components.filters import tool_multiselect, days_filter
from dashboard.components.charts import tool_comparison_chart, sentiment_bar_chart, metric_row


def render():
    st.header("🛠️ Tool Tracker")
    st.caption("Side-by-side tool sentiment from mart_tool_comparison")

    col1, col2 = st.columns(2)
    with col1:
        tools = tool_multiselect("tt_tools")
    with col2:
        days = days_filter("tt_days", default=30)

    params = {"days": days}
    if tools:
        params["tools"] = tools

    data = api_get("/tools/compare", params=params)
    if not data or not data.get("data"):
        st.info("No tool comparison data available. Select tools above or wait for data to accumulate.")
        return

    df = pd.DataFrame(data["data"])
    df["post_date"] = pd.to_datetime(df["post_date"])
    unique_tools = data.get("tools", [])

    # Metrics
    if not df.empty:
        best_tool = df.groupby("tool")["avg_sentiment"].mean().idxmax()
        most_discussed = df.groupby("tool")["post_count"].sum().idxmax()
        metric_row([
            {"label": "Tools Tracked", "value": len(unique_tools)},
            {"label": "Most Positive Tool", "value": best_tool},
            {"label": "Most Discussed Tool", "value": most_discussed},
            {"label": "Total Posts", "value": int(df["post_count"].sum())},
        ])

    st.divider()

    # Tool sentiment line chart
    tool_comparison_chart(df, title="Tool Sentiment Over Time")

    # Sentiment breakdown per tool
    if not df.empty:
        tool_summary = df.groupby("tool").agg(
            avg_sentiment=("avg_sentiment", "mean"),
            positive_count=("positive_count", "sum"),
            negative_count=("negative_count", "sum"),
            neutral_count=("neutral_count", "sum"),
            post_count=("post_count", "sum"),
        ).reset_index()
        sentiment_bar_chart(tool_summary, x_col="tool", title="Sentiment Breakdown by Tool")

    with st.expander("View raw data"):
        st.dataframe(df, use_container_width=True, hide_index=True)
