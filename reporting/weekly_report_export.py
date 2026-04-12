"""Shared weekly report PDF rendering helpers."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from html import escape
from io import BytesIO

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def inline_markdown_to_html(text: str) -> str:
    html = escape(text)
    html = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html)
    html = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", html)
    return html


def normalize_presented_markdown(text: str) -> str:
    normalized = text.replace("\r\n", "\n").strip()
    section_titles = [
        "Executive Summary",
        "Key Themes",
        "Notable Signals",
        "Watch Next Week",
    ]

    for title in section_titles:
        normalized = re.sub(
            rf"(^|\n)(##\s*{re.escape(title)})\s+",
            rf"\1## {title}\n",
            normalized,
        )
        normalized = re.sub(
            rf"(^|\n){re.escape(title)}\s*[-:]\s+",
            rf"\1## {title}\n",
            normalized,
        )

    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized


def split_report_blocks(text: str) -> tuple[str | None, list[tuple[str, str]]]:
    normalized = normalize_presented_markdown(text)
    title: str | None = None
    blocks: list[tuple[str, str]] = []
    paragraph_lines: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph_lines
        if not paragraph_lines:
            return
        merged = " ".join(line.strip() for line in paragraph_lines if line.strip())
        if merged:
            blocks.append(("paragraph", merged))
        paragraph_lines = []

    for raw_line in normalized.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            flush_paragraph()
            continue
        if stripped.startswith("# "):
            flush_paragraph()
            if not title:
                title = stripped[2:].strip()
            continue
        if stripped.startswith("## "):
            flush_paragraph()
            blocks.append(("heading2", stripped[3:].strip()))
            continue
        if stripped.startswith("### "):
            flush_paragraph()
            blocks.append(("heading3", stripped[4:].strip()))
            continue
        if stripped.startswith("- ") or stripped.startswith("* "):
            flush_paragraph()
            blocks.append(("bullet", stripped[2:].strip()))
            continue
        paragraph_lines.append(stripped)

    flush_paragraph()
    return title, blocks


def format_report_schedule_text(generated_at_raw: str) -> str:
    generated_at = datetime.fromisoformat(str(generated_at_raw))
    next_report_at = generated_at + timedelta(days=7)
    generated_label = generated_at.strftime("%B %d, %Y at %I:%M %p").replace(" 0", " ")
    next_label = next_report_at.strftime("%B %d, %Y at %I:%M %p").replace(" 0", " ")
    return (
        f"The latest report was generated on {generated_label}. "
        f"Next report will be generated at {next_label}."
    )


def build_pdf_base_layout() -> dict:
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


def build_pdf_sentiment_figure(trends_df: pd.DataFrame) -> go.Figure:
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
        line=dict(color="#2f9e44", width=4),
        marker=dict(size=8, color="#2f9e44"),
        name="Avg Sentiment",
    ))
    fig.add_hline(
        y=0,
        line_dash="dot",
        line_color="rgba(0,0,0,0.28)",
        line_width=1,
    )
    layout = build_pdf_base_layout()
    layout["title"] = "Weekly Sentiment Trend"
    layout["showlegend"] = False
    layout["xaxis"] = {**layout["xaxis"], "title": "Date"}
    layout["yaxis"] = {**layout["yaxis"], "title": "Avg Sentiment", "range": [-1.1, 1.1]}
    fig.update_layout(**layout)
    return fig


def build_pdf_topics_figure(trends_df: pd.DataFrame) -> go.Figure:
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
        color_discrete_sequence=["#2f9e44", "#6c757d", "#868e96", "#adb5bd", "#f08c00", "#c92a2a"],
    )
    fig.update_traces(marker_line_width=0)
    layout = build_pdf_base_layout()
    layout["showlegend"] = False
    layout["xaxis"] = {**layout["xaxis"], "title": "Topic"}
    layout["yaxis"] = {**layout["yaxis"], "title": "Post Count"}
    fig.update_layout(**layout)
    return fig


def build_pdf_chart_figures(trends_df: pd.DataFrame) -> list[go.Figure]:
    if trends_df.empty:
        return []
    normalized_df = trends_df.copy()
    normalized_df["post_date"] = pd.to_datetime(normalized_df["post_date"])
    return [
        build_pdf_sentiment_figure(normalized_df),
        build_pdf_topics_figure(normalized_df),
    ]


def render_weekly_report_pdf(report: dict, source_items: list[dict], chart_figures: list[go.Figure]) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import HRFlowable, Image, Paragraph, SimpleDocTemplate, Spacer
    except Exception as exc:
        raise RuntimeError("PDF export dependencies are unavailable. Install reportlab and kaleido.") from exc

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
        title="Developer Radar Weekly Report",
        author="Developer Radar",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="ReportTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#111111"),
        alignment=TA_LEFT,
        spaceAfter=14,
    ))
    styles.add(ParagraphStyle(
        name="ReportBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10.5,
        leading=15,
        textColor=colors.HexColor("#222222"),
        spaceAfter=10,
    ))
    styles.add(ParagraphStyle(
        name="ReportMeta",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#555555"),
        spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="ReportLead",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#444444"),
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="ReportHeading2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=18,
        textColor=colors.HexColor("#111111"),
        spaceBefore=12,
        spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="ReportHeading3",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#1f1f1f"),
        spaceBefore=8,
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="ReportBullet",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10.5,
        leading=14,
        leftIndent=14,
        firstLineIndent=0,
        bulletIndent=2,
        textColor=colors.HexColor("#222222"),
        spaceAfter=4,
    ))

    report_text = str(report.get("presented_report_text") or report.get("formatted_report_text") or report.get("report_text", ""))
    report_title, report_blocks = split_report_blocks(report_text)
    generated_at = escape(str(report.get("generated_at", "")))
    query = escape(str(report.get("query", "")))

    story = [
        Paragraph(report_title or "Developer Radar Weekly Report", styles["ReportTitle"]),
        Paragraph(format_report_schedule_text(generated_at), styles["ReportLead"]),
        Paragraph(f"Weekly focus: {query}", styles["ReportMeta"]),
        Spacer(1, 0.06 * inch),
        HRFlowable(width="100%", thickness=0.7, color=colors.HexColor("#d9d9d9"), spaceBefore=0, spaceAfter=12),
    ]

    for block_type, block_text in report_blocks:
        if block_type == "heading2":
            story.append(Paragraph(escape(block_text), styles["ReportHeading2"]))
        elif block_type == "heading3":
            story.append(Paragraph(escape(block_text), styles["ReportHeading3"]))
        elif block_type == "bullet":
            story.append(Paragraph(inline_markdown_to_html(block_text), styles["ReportBullet"], bulletText="•"))
        else:
            story.append(Paragraph(inline_markdown_to_html(block_text), styles["ReportBody"]))

    if chart_figures:
        story.append(Spacer(1, 0.2 * inch))
        story.append(Paragraph("Weekly Charts", styles["ReportHeading2"]))
        story.append(Spacer(1, 0.1 * inch))
        for fig in chart_figures:
            image_bytes = fig.to_image(format="png", width=1400, height=900, scale=2)
            image_buffer = BytesIO(image_bytes)
            story.append(Image(image_buffer, width=6.8 * inch, height=3.95 * inch))
            story.append(Spacer(1, 0.15 * inch))

    if source_items:
        story.append(Spacer(1, 0.15 * inch))
        story.append(Paragraph("Sources", styles["ReportHeading2"]))
        story.append(Spacer(1, 0.05 * inch))
        for idx, item in enumerate(source_items, 1):
            label = escape(str(item.get("label", "")))
            url = escape(str(item.get("url", "")))
            story.append(Paragraph(f"{idx}. {label}<br/><font size='9' color='#666666'>{url}</font>", styles["ReportBody"]))

    def draw_page_background(canvas, pdf_doc) -> None:
        del pdf_doc
        canvas.saveState()
        canvas.setFillColor(colors.white)
        canvas.rect(0, 0, letter[0], letter[1], fill=1, stroke=0)
        canvas.setFillColor(colors.HexColor("#888888"))
        canvas.setFont("Helvetica", 9)
        canvas.drawRightString(letter[0] - 40, 24, f"Page {canvas.getPageNumber()}")
        canvas.restoreState()

    doc.build(story, onFirstPage=draw_page_background, onLaterPages=draw_page_background)
    return buffer.getvalue()
