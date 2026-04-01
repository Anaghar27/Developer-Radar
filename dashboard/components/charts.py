import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


def sentiment_line_chart(df: pd.DataFrame, title: str = "Sentiment Over Time"):
    """Line chart of avg_sentiment over post_date."""
    if df.empty:
        st.info("No data available for this chart.")
        return
    fig = px.line(
        df,
        x="post_date",
        y="avg_sentiment",
        color="topic" if "topic" in df.columns else None,
        title=title,
        labels={"avg_sentiment": "Avg Sentiment", "post_date": "Date"},
        template="plotly_dark",
    )
    fig.update_layout(
        yaxis=dict(range=[-1.1, 1.1]),
        legend_title="Topic",
        height=400,
    )
    st.plotly_chart(fig, use_container_width=True)


def sentiment_bar_chart(df: pd.DataFrame, x_col: str, title: str = "Sentiment Breakdown"):
    """Stacked bar chart of positive/negative/neutral counts."""
    if df.empty:
        st.info("No data available for this chart.")
        return
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Positive", x=df[x_col], y=df["positive_count"],
                         marker_color="#2ecc71"))
    fig.add_trace(go.Bar(name="Neutral", x=df[x_col], y=df["neutral_count"],
                         marker_color="#95a5a6"))
    fig.add_trace(go.Bar(name="Negative", x=df[x_col], y=df["negative_count"],
                         marker_color="#e74c3c"))
    fig.update_layout(
        barmode="stack",
        title=title,
        template="plotly_dark",
        height=400,
        xaxis_title=x_col.replace("_", " ").title(),
        yaxis_title="Post Count",
    )
    st.plotly_chart(fig, use_container_width=True)


def divergence_chart(df: pd.DataFrame, title: str = "Reddit vs HN Sentiment Delta"):
    """Bar chart showing sentiment delta between Reddit and HN."""
    if df.empty:
        st.info("No divergence data available.")
        return
    fig = px.bar(
        df,
        x="topic",
        y="sentiment_delta",
        color="sentiment_delta",
        color_continuous_scale=["#e74c3c", "#95a5a6", "#2ecc71"],
        title=title,
        labels={"sentiment_delta": "Sentiment Delta (Reddit - HN)"},
        template="plotly_dark",
    )
    fig.update_layout(height=400)
    st.plotly_chart(fig, use_container_width=True)


def tool_comparison_chart(df: pd.DataFrame, title: str = "Tool Sentiment Comparison"):
    """Line+marker chart comparing avg_sentiment across tools over time."""
    if df.empty:
        st.info("No tool comparison data available.")
        return

    # Only warn about sparse tools when the chart has few tools selected
    # (not when showing all 300+ tools at once — the message would be enormous)
    points_per_tool = df.groupby("tool").size()
    sparse_tools = points_per_tool[points_per_tool == 1].index.tolist()
    if sparse_tools and df["tool"].nunique() <= 10:
        st.warning(
            f"{'These tools have' if len(sparse_tools) > 1 else 'This tool has'} only 1 data point "
            f"— shown as a dot, not a line: {', '.join(sparse_tools)}. "
            f"Widen the date range to see trend lines."
        )

    fig = px.line(
        df,
        x="post_date",
        y="avg_sentiment",
        color="tool",
        title=title,
        labels={"avg_sentiment": "Avg Sentiment", "post_date": "Date"},
        template="plotly_dark",
        markers=True,  # show dots so single-point tools are visible
    )
    fig.update_traces(marker=dict(size=8))
    fig.update_layout(
        yaxis=dict(range=[-1.1, 1.1]),
        height=400,
    )
    st.plotly_chart(fig, use_container_width=True)


def metric_row(metrics: list[dict]):
    """
    Render a row of st.metric cards.
    Each dict: {"label": str, "value": any, "delta": optional}
    """
    cols = st.columns(len(metrics))
    for col, m in zip(cols, metrics):
        with col:
            st.metric(
                label=m["label"],
                value=m["value"],
                delta=m.get("delta"),
            )
