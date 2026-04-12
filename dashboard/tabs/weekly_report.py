"""Lumina — Weekly Report tab."""
from __future__ import annotations

from datetime import datetime, timedelta
from html import escape

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dashboard.api_client import api_get, api_get_bytes
from dashboard.components.charts import section_header
from reporting.weekly_report_export import build_pdf_chart_figures, render_weekly_report_pdf

WEEKLY_REPORT_QUERY = "What are the key developer sentiment trends and tool discussions from the past week?"

_TOPIC_COLORS = ["#5cd65c", "#d0d0d0", "#909090", "#707070", "#e0a020", "#ff4444"]


def _theme_mode() -> str:
    return st.session_state.get("theme", "dark")


def _format_report_schedule_text(generated_at_raw: str) -> str:
    generated_at = datetime.fromisoformat(str(generated_at_raw))
    next_report_at = generated_at + timedelta(days=7)
    generated_label = generated_at.strftime("%B %d, %Y at %I:%M %p").replace(" 0", " ")
    next_label = next_report_at.strftime("%B %d, %Y at %I:%M %p").replace(" 0", " ")
    return (
        f'The latest report was generated on {generated_label}. '
        f'Next report will be generated at {next_label}.'
    )


def _base_layout(for_pdf: bool = False) -> dict:
    if for_pdf:
        return dict(
            paper_bgcolor="#ffffff",
            plot_bgcolor="#ffffff",
            font=dict(color="#222222", family="Helvetica,Arial,sans-serif", size=13),
            title_font=dict(color="#111111", family="Helvetica,Arial,sans-serif", size=20),
            xaxis=dict(
                gridcolor="rgba(0,0,0,0.08)",
                zeroline=False,
                linecolor="rgba(0,0,0,0.18)",
                tickfont=dict(color="#444444", size=11),
                title_font=dict(color="#222222", size=13),
            ),
            yaxis=dict(
                gridcolor="rgba(0,0,0,0.08)",
                zeroline=False,
                linecolor="rgba(0,0,0,0.18)",
                tickfont=dict(color="#444444", size=11),
                title_font=dict(color="#222222", size=13),
            ),
            legend=dict(bgcolor="rgba(255,255,255,0.95)", bordercolor="rgba(0,0,0,0.12)", borderwidth=1),
            margin=dict(l=70, r=30, t=70, b=70),
            height=520,
        )

    dark = _theme_mode() == "dark"
    if dark:
        return dict(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(17,17,17,0.6)",
            font=dict(color="#c8c8c8", family="DM Sans,sans-serif"),
            title_font=dict(color="#f0f0f0", family="Space Grotesk,sans-serif", size=13),
            xaxis=dict(gridcolor="rgba(255,255,255,0.05)", zeroline=False),
            yaxis=dict(gridcolor="rgba(255,255,255,0.05)", zeroline=False),
            legend=dict(bgcolor="rgba(0,0,0,0)"),
            margin=dict(l=10, r=10, t=44, b=10),
            height=360,
        )
    return dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(238,238,238,0.5)",
        font=dict(color="#303030", family="DM Sans,sans-serif"),
        title_font=dict(color="#0a0a0a", family="Space Grotesk,sans-serif", size=13),
        xaxis=dict(gridcolor="rgba(0,0,0,0.06)", zeroline=False),
        yaxis=dict(gridcolor="rgba(0,0,0,0.06)", zeroline=False),
        legend=dict(bgcolor="rgba(255,255,255,0.7)"),
        margin=dict(l=10, r=10, t=44, b=10),
        height=360,
    )


def _build_sentiment_figure(trends_df: pd.DataFrame, for_pdf: bool = False) -> go.Figure:
    daily = (
        trends_df.groupby("post_date")
        .agg(avg_sentiment=("avg_sentiment", "mean"))
        .reset_index()
        .sort_values("post_date")
    )
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=daily["post_date"],
        y=daily["avg_sentiment"],
        mode="lines+markers",
        line=dict(color="#2f9e44", width=4 if for_pdf else 3),
        marker=dict(size=8 if for_pdf else 7, color="#2f9e44"),
        name="Avg Sentiment",
    ))
    fig.add_hline(
        y=0,
        line_dash="dot",
        line_color="rgba(0,0,0,0.28)" if for_pdf else "rgba(128,128,128,0.5)",
        line_width=1,
    )
    layout = _base_layout(for_pdf=for_pdf)
    layout["title"] = "Weekly Sentiment Trend"
    layout["showlegend"] = False
    layout["xaxis"] = {**layout["xaxis"], "title": "Date"}
    layout["yaxis"] = {**layout["yaxis"], "title": "Avg Sentiment", "range": [-1.1, 1.1]}
    fig.update_layout(**layout)
    return fig


def _build_topics_figure(trends_df: pd.DataFrame, for_pdf: bool = False) -> go.Figure:
    topic_df = (
        trends_df.groupby("topic")
        .agg(post_count=("post_count", "sum"))
        .reset_index()
        .sort_values("post_count", ascending=False)
        .head(8)
    )
    fig = px.bar(
        topic_df,
        x="topic",
        y="post_count",
        title="Top Topics This Week",
        color_discrete_sequence=["#2f9e44", "#6c757d", "#868e96", "#adb5bd", "#f08c00", "#c92a2a"] if for_pdf else _TOPIC_COLORS,
    )
    fig.update_traces(marker_line_width=0)
    layout = _base_layout(for_pdf=for_pdf)
    layout["showlegend"] = False
    layout["xaxis"] = {**layout["xaxis"], "title": "Topic"}
    layout["yaxis"] = {**layout["yaxis"], "title": "Post Count"}
    fig.update_layout(**layout)
    return fig


def render() -> None:
    section_header(
        "🗓️",
        "Weekly Report",
        "Saved weekly report generated by the scheduled transformation pipeline.",
    )

    latest_weekly = api_get("/reports/latest", params={"query": WEEKLY_REPORT_QUERY})
    if not latest_weekly:
        st.info("No saved weekly report is available yet. It will appear here after the scheduled Sunday run.")
        return

    trends_data = api_get("/trends", params={"days": 7}) or {}
    trends_rows = trends_data.get("data", [])
    trends_df = pd.DataFrame(trends_rows) if trends_rows else pd.DataFrame()
    chart_figures: list[go.Figure] = []

    if not trends_df.empty:
        trends_df["post_date"] = pd.to_datetime(trends_df["post_date"])
        sentiment_fig = _build_sentiment_figure(trends_df)
        topics_fig = _build_topics_figure(trends_df)
        chart_figures = [sentiment_fig, topics_fig]

    source_items = latest_weekly.get("source_items") or []
    presented_report_text = str(
        latest_weekly.get("formatted_report_text")
        or latest_weekly.get("report_text")
        or ""
    )
    latest_weekly["presented_report_text"] = presented_report_text

    c1, c2 = st.columns([4, 1])
    with c1:
        st.caption(_format_report_schedule_text(str(latest_weekly["generated_at"])))
    with c2:
        generated_date = str(latest_weekly["generated_at"]).split("T")[0]
        try:
            pdf_bytes = api_get_bytes("/reports/latest/pdf", params={"query": WEEKLY_REPORT_QUERY})
            if not pdf_bytes:
                pdf_chart_figures = build_pdf_chart_figures(trends_df)
                pdf_bytes = render_weekly_report_pdf(latest_weekly, source_items, pdf_chart_figures)
            st.download_button(
                "Download PDF",
                data=pdf_bytes,
                file_name=f"developer-radar-weekly-report-{generated_date}.pdf",
                mime="application/pdf",
                use_container_width=True,
                key="weekly_report_download_pdf",
            )
        except Exception as exc:
            st.caption(f"PDF export unavailable: {exc}")

    st.markdown(presented_report_text)

    if chart_figures:
        st.divider()
        st.markdown("### Weekly Charts")
        st.plotly_chart(chart_figures[0], use_container_width=True)
        st.plotly_chart(chart_figures[1], use_container_width=True)

    if source_items:
        st.markdown(f"**Sources ({len(source_items)})**")
        rows = ""
        for i, item in enumerate(source_items, 1):
            label = item.get("label") or item.get("url", "")
            src = item.get("url", "")
            link = (
                f'<a href="{src}" target="_blank" rel="noopener">{escape(str(label))}</a>'
                if src.startswith("http")
                else f"<code>{escape(str(src))}</code>"
            )
            rows += (
                f'<div class="dp-source-row">'
                f'<span class="dp-source-num">{i}</span>'
                f"{link}"
                f"</div>"
            )
        st.markdown(rows, unsafe_allow_html=True)

    with st.expander("Weekly report metadata"):
        st.json({
            "id": latest_weekly.get("id"),
            "query": latest_weekly.get("query"),
            "generated_at": latest_weekly.get("generated_at"),
            "sources_count": len(source_items),
            "charts_included": len(chart_figures),
        })
