"""Silver Ghost chart components — monochrome Plotly charts with green/red data pops."""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ── Design tokens ──────────────────────────────────────────────────────────────

# Silver Ghost — stepped grays + green/red as only pops of colour
_COLORS_DARK = [
    "#e0e0e0",  # near-white
    "#5cd65c",  # green (positive pop)
    "#ff4444",  # red (negative pop)
    "#a0a0a0",  # mid gray
    "#c8c8c8",  # light gray
    "#707070",  # darker gray
    "#e0a020",  # amber (warning)
    "#888888",  # muted gray
    "#d0d0d0",  # silver
    "#505050",  # deep gray
]
_COLORS_LIGHT = [
    "#1a1a1a",  # near-black
    "#1e8c1e",  # green
    "#cc0000",  # red
    "#484848",  # dark gray
    "#787878",  # mid gray
    "#303030",  # deep gray
    "#b06800",  # amber
    "#909090",  # muted gray
    "#585858",  # medium-dark gray
    "#a8a8a8",  # light gray
]

_SENTIMENT_DARK  = {"positive": "#5cd65c", "neutral": "#888888", "negative": "#ff4444"}
_SENTIMENT_LIGHT = {"positive": "#1e8c1e", "neutral": "#787878", "negative": "#cc0000"}

_REDDIT_COLOR = "#FF6B35"   # brand-adjacent orange-red
_HN_COLOR = "#FBBF24"       # amber


def _theme_mode() -> str:
    return st.session_state.get("theme", "dark")


def _colors() -> list[str]:
    return _COLORS_DARK if _theme_mode() == "dark" else _COLORS_LIGHT


def _sent_colors() -> dict:
    return _SENTIMENT_DARK if _theme_mode() == "dark" else _SENTIMENT_LIGHT


def _plotly_base(dark: bool) -> dict:
    if dark:
        return dict(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(17,17,17,0.6)",
            font=dict(family="DM Sans,sans-serif", color="#909090", size=12),
            title_font=dict(size=13, color="#f0f0f0", family="Space Grotesk,sans-serif"),
            title_x=0,
            title_xanchor="left",
            xaxis=dict(
                gridcolor="rgba(255,255,255,0.05)",
                linecolor="rgba(255,255,255,0.08)",
                tickfont=dict(size=11, color="#585858"),
                showgrid=True, zeroline=False,
            ),
            yaxis=dict(
                gridcolor="rgba(255,255,255,0.05)",
                linecolor="rgba(255,255,255,0.08)",
                tickfont=dict(size=11, color="#585858"),
                showgrid=True, zeroline=False,
            ),
            legend=dict(
                bgcolor="rgba(0,0,0,0)",
                bordercolor="rgba(255,255,255,0.08)",
                borderwidth=1,
                font=dict(size=11, color="#909090"),
            ),
            hoverlabel=dict(
                bgcolor="#1a1a1a",
                bordercolor="#ffffff",
                font=dict(size=12, color="#f0f0f0", family="DM Sans,sans-serif"),
            ),
            margin=dict(l=10, r=10, t=44, b=10),
            height=420,
        )
    else:
        return dict(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(238,238,238,0.5)",
            font=dict(family="DM Sans,sans-serif", color="#484848", size=12),
            title_font=dict(size=13, color="#0a0a0a", family="Space Grotesk,sans-serif"),
            title_x=0,
            title_xanchor="left",
            xaxis=dict(
                gridcolor="rgba(0,0,0,0.06)",
                linecolor="rgba(0,0,0,0.10)",
                tickfont=dict(size=11, color="#787878"),
                showgrid=True, zeroline=False,
            ),
            yaxis=dict(
                gridcolor="rgba(0,0,0,0.06)",
                linecolor="rgba(0,0,0,0.10)",
                tickfont=dict(size=11, color="#787878"),
                showgrid=True, zeroline=False,
            ),
            legend=dict(
                bgcolor="rgba(255,255,255,0.85)",
                bordercolor="rgba(0,0,0,0.10)",
                borderwidth=1,
                font=dict(size=11, color="#484848"),
            ),
            hoverlabel=dict(
                bgcolor="#ffffff",
                bordercolor="#0a0a0a",
                font=dict(size=12, color="#0a0a0a", family="DM Sans,sans-serif"),
            ),
            margin=dict(l=10, r=10, t=44, b=10),
            height=420,
        )


def _theme(fig: go.Figure, **overrides) -> go.Figure:
    """Apply the shared Plotly theme (auto dark/light), with optional overrides."""
    dark = _theme_mode() == "dark"
    layout = {**_plotly_base(dark), **overrides}
    # Merge nested dicts (xaxis, yaxis) rather than replace
    for key in ("xaxis", "yaxis"):
        if key in overrides and key in _plotly_base(dark):
            merged = {**_plotly_base(dark)[key], **overrides[key]}
            layout[key] = merged
    fig.update_layout(**layout)
    return fig


def _zero_hline(fig: go.Figure) -> go.Figure:
    dark = _theme_mode() == "dark"
    color = "rgba(255,255,255,0.20)" if dark else "rgba(0,0,0,0.15)"
    fig.add_hline(y=0, line_dash="dot", line_color=color, line_width=1)
    return fig


# ── Section header ─────────────────────────────────────────────────────────────

def section_header(icon: str, title: str, description: str = "") -> None:
    """Render a styled section header for dashboard tabs."""
    desc_html = f'<p class="dp-tab-desc">{description}</p>' if description else ""
    st.markdown(
        f'<div class="dp-tab-header">'
        f'<h2 class="dp-tab-title">'
        f'<span class="dp-tab-title-icon">{icon}</span>'
        f'{title}'
        f'</h2>'
        f'{desc_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


def filters_label() -> None:
    st.markdown('<span class="dp-filter-label">Filters</span>', unsafe_allow_html=True)


# ── Charts ─────────────────────────────────────────────────────────────────────

def sentiment_line_chart(df: pd.DataFrame, title: str = "Sentiment Over Time") -> None:
    """Line chart of avg_sentiment over post_date."""
    if df.empty:
        st.info("No data available for this chart.")
        return

    has_topic = "topic" in df.columns and df["topic"].nunique() > 1
    dark = _theme_mode() == "dark"
    zero_color = "rgba(255,255,255,0.18)" if dark else "rgba(0,0,0,0.14)"

    fig = px.line(
        df,
        x="post_date",
        y="avg_sentiment",
        color="topic" if has_topic else None,
        title=title,
        labels={"avg_sentiment": "Avg Sentiment", "post_date": "Date"},
        color_discrete_sequence=_colors(),
    )
    fig.update_traces(line_width=2.5)
    _theme(
        fig,
        yaxis=dict(
            range=[-1.1, 1.1],
            zeroline=True,
            zerolinecolor=zero_color,
            zerolinewidth=1,
        ),
        legend_title="Topic",
    )
    _zero_hline(fig)
    st.plotly_chart(fig, use_container_width=True)


def sentiment_bar_chart(
    df: pd.DataFrame, x_col: str, title: str = "Sentiment Breakdown"
) -> None:
    """Stacked bar chart of positive / neutral / negative counts."""
    if df.empty:
        st.info("No data available for this chart.")
        return

    sc = _sent_colors()
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Positive", x=df[x_col], y=df["positive_count"],
        marker_color=sc["positive"], marker_line_width=0,
    ))
    fig.add_trace(go.Bar(
        name="Neutral", x=df[x_col], y=df["neutral_count"],
        marker_color=sc["neutral"], marker_line_width=0, opacity=0.75,
    ))
    fig.add_trace(go.Bar(
        name="Negative", x=df[x_col], y=df["negative_count"],
        marker_color=sc["negative"], marker_line_width=0,
    ))
    _theme(
        fig,
        barmode="stack",
        title=title,
        xaxis_title=x_col.replace("_", " ").title(),
        yaxis_title="Post Count",
    )
    st.plotly_chart(fig, use_container_width=True)


def divergence_chart(df: pd.DataFrame, title: str = "Reddit vs HN Sentiment Delta") -> None:
    """Horizontal-ish bar chart of sentiment delta between Reddit and HN."""
    if df.empty:
        st.info("No divergence data available.")
        return

    sc = _sent_colors()
    chart_df = df.copy()
    near_zero_threshold = 0.1

    def _delta_bucket(value: float) -> str:
        if value > near_zero_threshold:
            return "Positive"
        if value < -near_zero_threshold:
            return "Negative"
        return "Near zero"

    chart_df["delta_bucket"] = chart_df["sentiment_delta"].apply(_delta_bucket)

    fig = px.bar(
        chart_df,
        x="topic",
        y="sentiment_delta",
        color="delta_bucket",
        category_orders={"delta_bucket": ["Positive", "Near zero", "Negative"]},
        color_discrete_map={
            "Positive": sc["positive"],
            "Near zero": sc["neutral"],
            "Negative": sc["negative"],
        },
        title=title,
        labels={
            "sentiment_delta": "Sentiment Delta (Reddit − HN)",
            "delta_bucket": "Delta Type",
        },
    )
    fig.update_traces(marker_line_width=0)
    _theme(fig)
    _zero_hline(fig)
    st.plotly_chart(fig, use_container_width=True)


def tool_comparison_chart(
    df: pd.DataFrame, title: str = "Tool Sentiment Comparison"
) -> None:
    """Line+marker chart comparing avg_sentiment across tools over time."""
    if df.empty:
        st.info("No tool comparison data available.")
        return

    points_per_tool = df.groupby("tool").size()
    sparse_tools = points_per_tool[points_per_tool == 1].index.tolist()
    if sparse_tools and df["tool"].nunique() <= 10:
        st.warning(
            f"{'These tools have' if len(sparse_tools) > 1 else 'This tool has'} only 1 data point "
            f"and will appear as a dot rather than a line: {', '.join(sparse_tools)}. "
            "Widen the date range to see trend lines."
        )

    dark = _theme_mode() == "dark"
    zero_color = "rgba(255,255,255,0.18)" if dark else "rgba(0,0,0,0.14)"

    fig = px.line(
        df,
        x="post_date",
        y="avg_sentiment",
        color="tool",
        title=title,
        labels={"avg_sentiment": "Avg Sentiment", "post_date": "Date"},
        color_discrete_sequence=_colors(),
        markers=True,
    )
    fig.update_traces(marker=dict(size=7), line_width=2.2)
    _theme(
        fig,
        yaxis=dict(
            range=[-1.1, 1.1],
            zeroline=True,
            zerolinecolor=zero_color,
            zerolinewidth=1,
        ),
    )
    _zero_hline(fig)
    st.plotly_chart(fig, use_container_width=True)


def community_overlay_chart(
    daily: pd.DataFrame,
    title: str = "Reddit vs Hacker News — Average Daily Sentiment",
) -> None:
    """Overlay line chart comparing Reddit and HN sentiment over time."""
    if daily.empty:
        st.info("No community data available.")
        return

    dark = _theme_mode() == "dark"
    zero_color = "rgba(255,255,255,0.18)" if dark else "rgba(0,0,0,0.14)"

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=daily["post_date"], y=daily["reddit_sentiment"],
        name="Reddit",
        line=dict(color=_REDDIT_COLOR, width=2.5),
        hovertemplate="<b>Reddit</b><br>%{x|%b %d}<br>Sentiment: %{y:.3f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=daily["post_date"], y=daily["hn_sentiment"],
        name="Hacker News",
        line=dict(color=_HN_COLOR, width=2.5),
        hovertemplate="<b>Hacker News</b><br>%{x|%b %d}<br>Sentiment: %{y:.3f}<extra></extra>",
    ))
    _theme(
        fig,
        title=title,
        yaxis=dict(
            range=[-1.1, 1.1],
            zeroline=True,
            zerolinecolor=zero_color,
            zerolinewidth=1,
        ),
    )
    _zero_hline(fig)
    st.plotly_chart(fig, use_container_width=True)


def metric_row(metrics: list[dict]) -> None:
    """
    Render a row of st.metric cards.
    Each dict: {"label": str, "value": any, "delta": optional}
    """
    cols = st.columns(len(metrics), gap="small")
    for col, m in zip(cols, metrics):
        with col:
            st.metric(
                label=m["label"],
                value=m["value"],
                delta=m.get("delta"),
            )
