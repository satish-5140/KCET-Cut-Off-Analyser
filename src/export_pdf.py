"""
export_pdf.py
Generates a filtered PDF that visually mirrors the KCET cutoff PDF layout.
Uses ReportLab for precise table rendering in landscape A3.
"""

import logging
from io import BytesIO
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    HRFlowable,
    KeepTogether,
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import PageBreak

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Colours (matching KCET PDF aesthetic)
# ──────────────────────────────────────────────────────────────────────────────

COL_HEADER_BG   = colors.HexColor("#1a3a5c")   # dark navy – column header
COL_HEADER_FG   = colors.white
COLLEGE_BG      = colors.HexColor("#f0f4f8")   # very light blue – college header row
COLLEGE_FG      = colors.HexColor("#1a3a5c")
ROW_ODD         = colors.white
ROW_EVEN        = colors.HexColor("#f9fafb")
BORDER_COL      = colors.HexColor("#c0ccd8")
GRID_COL        = colors.HexColor("#d0dde8")


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def export_to_pdf(filtered_colleges: list[dict], title: str = "KCET Cutoff Analysis") -> BytesIO:
    """
    Generate a filtered PDF and return it as a BytesIO object.
    """
    buf = BytesIO()

    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A3),
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=title,
    )

    styles = _build_styles()
    story = []

    # ── Document title ──
    story.append(Paragraph(title, styles["doc_title"]))
    story.append(Spacer(1, 4 * mm))
    story.append(HRFlowable(width="100%", thickness=1.5, color=COL_HEADER_BG))
    story.append(Spacer(1, 6 * mm))

    for college in filtered_colleges:
        df = college["table"]
        if df is None or df.empty:
            continue

        college_header = college.get("college_header", college.get("college_name", ""))
        block = _build_college_block(college_header, df, styles)
        story.append(KeepTogether(block[:4]))  # try to keep at least heading + first rows together
        for item in block[4:]:
            story.append(item)
        story.append(Spacer(1, 8 * mm))

    if not story or len(story) <= 4:
        story.append(Paragraph("No matching branches found.", styles["body"]))

    doc.build(story, onFirstPage=_page_header_footer, onLaterPages=_page_header_footer)
    buf.seek(0)
    return buf


# ──────────────────────────────────────────────────────────────────────────────
# Block builder
# ──────────────────────────────────────────────────────────────────────────────

def _build_college_block(college_header: str, df, styles) -> list:
    elements = []

    # College heading
    elements.append(Paragraph(f"<b>{college_header}</b>", styles["college_heading"]))
    elements.append(Spacer(1, 2 * mm))

    # Build table data
    columns = list(df.columns)
    header_row = [Paragraph(f"<b>{c}</b>", styles["col_header"]) for c in columns]
    data_rows = []

    for _, row in df.iterrows():
        data_row = []
        for i, col in enumerate(columns):
            val = str(row[col]) if str(row[col]) not in ("nan", "None", "") else "--"
            if i == 0:
                data_row.append(Paragraph(val, styles["course_cell"]))
            else:
                data_row.append(Paragraph(val, styles["data_cell"]))
        data_rows.append(data_row)

    table_data = [header_row] + data_rows

    # Calculate column widths
    page_width = landscape(A3)[0] - 20 * mm  # usable width
    n_cols = len(columns)

    if n_cols <= 1:
        col_widths = [page_width]
    else:
        course_col_w = page_width * 0.18  # ~18% for course name
        remaining = page_width - course_col_w
        other_w = remaining / (n_cols - 1)
        # Clamp other columns
        other_w = max(other_w, 8 * mm)
        col_widths = [course_col_w] + [other_w] * (n_cols - 1)

    tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(_table_style(len(data_rows)))
    elements.append(tbl)
    elements.append(Spacer(1, 2 * mm))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=BORDER_COL))

    return elements


def _table_style(n_data_rows: int) -> TableStyle:
    cmds = [
        # Header row
        ("BACKGROUND",    (0, 0), (-1, 0), COL_HEADER_BG),
        ("TEXTCOLOR",     (0, 0), (-1, 0), COL_HEADER_FG),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0), 6.5),
        ("ALIGN",         (0, 0), (-1, 0), "CENTER"),
        ("VALIGN",        (0, 0), (-1, 0), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
        ("TOPPADDING",    (0, 0), (-1, 0), 4),
        # Grid
        ("GRID",          (0, 0), (-1, -1), 0.4, GRID_COL),
        ("BOX",           (0, 0), (-1, -1), 0.8, BORDER_COL),
        # Data rows general
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 1), (-1, -1), 6),
        ("VALIGN",        (0, 1), (-1, -1), "MIDDLE"),
        ("ALIGN",         (1, 1), (-1, -1), "CENTER"),  # numeric cols centred
        ("ALIGN",         (0, 1), (0, -1), "LEFT"),     # course name left-aligned
        ("TOPPADDING",    (0, 1), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
    ]

    # Alternating row colours
    for i in range(1, n_data_rows + 1):
        bg = ROW_ODD if i % 2 != 0 else ROW_EVEN
        cmds.append(("BACKGROUND", (0, i), (-1, i), bg))

    return TableStyle(cmds)


# ──────────────────────────────────────────────────────────────────────────────
# Styles
# ──────────────────────────────────────────────────────────────────────────────

def _build_styles() -> dict:
    base = getSampleStyleSheet()

    return {
        "doc_title": ParagraphStyle(
            "doc_title",
            fontSize=14,
            fontName="Helvetica-Bold",
            textColor=COL_HEADER_BG,
            alignment=TA_CENTER,
            spaceAfter=2 * mm,
        ),
        "college_heading": ParagraphStyle(
            "college_heading",
            fontSize=8,
            fontName="Helvetica-Bold",
            textColor=COLLEGE_FG,
            backColor=COLLEGE_BG,
            borderPad=3,
            leading=11,
            spaceAfter=1 * mm,
        ),
        "col_header": ParagraphStyle(
            "col_header",
            fontSize=6.5,
            fontName="Helvetica-Bold",
            textColor=COL_HEADER_FG,
            alignment=TA_CENTER,
            leading=8,
        ),
        "course_cell": ParagraphStyle(
            "course_cell",
            fontSize=6,
            fontName="Helvetica",
            leading=8,
            alignment=TA_LEFT,
        ),
        "data_cell": ParagraphStyle(
            "data_cell",
            fontSize=6,
            fontName="Helvetica",
            leading=8,
            alignment=TA_CENTER,
        ),
        "body": base["Normal"],
    }


# ──────────────────────────────────────────────────────────────────────────────
# Page decorators
# ──────────────────────────────────────────────────────────────────────────────

def _page_header_footer(canvas, doc):
    canvas.saveState()
    w, h = landscape(A3)

    # Footer
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#666666"))
    canvas.drawString(10 * mm, 6 * mm, "KCET Cutoff Analyser — Filtered Results")
    canvas.drawRightString(w - 10 * mm, 6 * mm, f"Page {doc.page}")

    canvas.restoreState()
