import streamlit as st
import pandas as pd
from dashboard.api_client import api_get
from dashboard.components.filters import topic_filter, days_filter
from dashboard.components.charts import divergence_chart, metric_row


def render():
    st.header("⚔️ Community Comparison")
    st.caption("Reddit vs Hacker News sentiment divergence from mart_community_divergence")

    col1, col2 = st.columns(2)
    with col1:
        topic = topic_filter("cc_topic")
    with col2:
        days = days_filter("cc_days", default=30)

    params = {"days": days}
    if topic:
        params["topic"] = topic

    data = api_get("/community/divergence", params=params)
    if not data or not data.get("data"):
        st.info("No community divergence data available.")
        return

    df = pd.DataFrame(data["data"])
    df["post_date"] = pd.to_datetime(df["post_date"])

    # Metrics
    avg_delta = df["sentiment_delta"].mean()
    max_divergence = df.loc[df["sentiment_delta"].abs().idxmax()] if not df.empty else None

    metric_row([
        {"label": "Avg Delta", "value": f"{avg_delta:.3f}"},
        {"label": "Total Reddit Posts", "value": int(df["reddit_count"].sum())},
        {"label": "Total HN Posts", "value": int(df["hn_count"].sum())},
        {"label": "Most Divergent Topic",
         "value": max_divergence["topic"] if max_divergence is not None else "N/A"},
    ])

    st.divider()

    # Divergence chart — most recent day
    latest_date = df["post_date"].max()
    latest_df = df[df["post_date"] == latest_date]
    divergence_chart(latest_df, title=f"Sentiment Delta by Topic ({latest_date.date()})")
    st.caption(
        "Each bar shows Reddit sentiment minus HN sentiment for that topic on the most recent day. "
        "Positive (green) = Reddit is more positive than HN. Negative (red) = HN is more positive than Reddit. "
        "Near zero = both communities agree."
    )

    # Reddit vs HN line comparison
    import plotly.graph_objects as go
    if not df.empty:
        fig = go.Figure()
        daily = df.groupby("post_date")[["reddit_sentiment", "hn_sentiment"]].mean().reset_index()
        fig.add_trace(go.Scatter(
            x=daily["post_date"], y=daily["reddit_sentiment"],
            name="Reddit", line=dict(color="#FF4500", width=2)
        ))
        fig.add_trace(go.Scatter(
            x=daily["post_date"], y=daily["hn_sentiment"],
            name="Hacker News", line=dict(color="#00B4D8", width=2)
        ))
        fig.update_layout(
            title="Reddit vs HN Sentiment Over Time",
            template="plotly_dark",
            yaxis=dict(range=[-1.1, 1.1]),
            height=400,
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "Reddit (orange) vs Hacker News (blue) average daily sentiment over the selected period. "
            "When lines diverge, the two communities have opposing reactions to the same topics. "
            "When they converge, sentiment is broadly shared across both platforms."
        )

    with st.expander("View raw data"):
        st.dataframe(df, use_container_width=True, hide_index=True)
