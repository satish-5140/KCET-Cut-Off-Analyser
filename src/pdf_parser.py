"""
pdf_parser.py
Extracts college blocks and raw table data from KCET cutoff PDFs.
Handles text-based PDFs with pdfplumber, falls back to OCR via PyMuPDF + Tesseract.
"""

import re
import logging
from pathlib import Path
from typing import Optional

import pdfplumber
import fitz  # PyMuPDF
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

COLLEGE_PATTERN = re.compile(
    r"College\s*:\s*([A-Z]\d{3,4}[^\n]+)",
    re.IGNORECASE,
)

EXPECTED_COLUMNS = [
    "Course Name",
    "1G", "1K", "1R",
    "2AG", "2AK", "2AR",
    "2BG", "2BK", "2BR",
    "3AG", "3AK", "3AR",
    "3BG", "3BK", "3BR",
    "GM", "GMK", "GMP", "GMR",
    "NRI", "OPN", "OTH",
    "SCG", "SCK", "SCR",
    "STG", "STK", "STR",
]

# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def parse_pdf(pdf_path: str, progress_callback=None) -> list[dict]:
    """
    Parse the entire PDF and return a list of college dicts.

    Each dict:
    {
        "college_code": "E001",
        "college_name": "University Visvesvaraya College ...",
        "college_header": "College: E001 University ...",
        "table": pd.DataFrame   # rows = branches, cols = cutoff columns
    }
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    logger.info(f"Parsing PDF: {path.name}")

    # Try text-based extraction first
    colleges = _extract_with_pdfplumber(str(path), progress_callback)

    if not colleges:
        logger.warning("pdfplumber extracted nothing — falling back to OCR")
        colleges = _extract_with_ocr(str(path), progress_callback)

    logger.info(f"Total colleges extracted: {len(colleges)}")
    return colleges


# ──────────────────────────────────────────────────────────────────────────────
# pdfplumber extraction
# ──────────────────────────────────────────────────────────────────────────────

def _extract_with_pdfplumber(pdf_path: str, progress_callback=None) -> list[dict]:
    colleges = []
    pending_college_header = None
    pending_college_code = None
    pending_college_name = None
    accumulated_rows = []

    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)

        for page_num, page in enumerate(pdf.pages):
            if progress_callback:
                progress_callback(page_num + 1, total, f"Reading page {page_num + 1}/{total}")

            # ── Extract raw text lines to detect college headers ──
            text = page.extract_text() or ""
            lines = text.split("\n")

            # ── Extract tables from this page ──
            page_tables = page.extract_tables(
                table_settings={
                    "vertical_strategy": "lines",
                    "horizontal_strategy": "lines",
                    "snap_tolerance": 5,
                    "join_tolerance": 3,
                    "edge_min_length": 10,
                    "min_words_vertical": 1,
                    "min_words_horizontal": 1,
                }
            )

            # Check each line for a college header
            line_idx = 0
            table_idx = 0

            for line in lines:
                m = COLLEGE_PATTERN.search(line)
                if m:
                    # Save previous college if any
                    if pending_college_header and accumulated_rows:
                        df = _rows_to_dataframe(accumulated_rows)
                        if df is not None and not df.empty:
                            colleges.append({
                                "college_code": pending_college_code,
                                "college_name": pending_college_name,
                                "college_header": pending_college_header,
                                "table": df,
                            })
                    elif pending_college_header and not accumulated_rows:
                        # Will pick up table from next iteration
                        pass

                    full_match = m.group(1).strip()
                    code_match = re.match(r"([A-Z]\d{3,4})", full_match)
                    pending_college_code = code_match.group(1) if code_match else "UNKNOWN"
                    pending_college_name = full_match
                    pending_college_header = line.strip()
                    accumulated_rows = []

            # Assign tables to colleges using position heuristics
            for raw_table in page_tables:
                if not raw_table or len(raw_table) < 2:
                    continue
                rows = _clean_raw_table(raw_table)
                if rows:
                    accumulated_rows.extend(rows)

        # Don't forget the last college
        if pending_college_header and accumulated_rows:
            df = _rows_to_dataframe(accumulated_rows)
            if df is not None and not df.empty:
                colleges.append({
                    "college_code": pending_college_code,
                    "college_name": pending_college_name,
                    "college_header": pending_college_header,
                    "table": df,
                })

    # If the simple page-level approach missed colleges, try block-level
    if not colleges:
        colleges = _extract_block_level(pdf_path, progress_callback)

    return colleges


def _extract_block_level(pdf_path: str, progress_callback=None) -> list[dict]:
    """
    Alternative: collect ALL text + tables, then split by college headers.
    More robust for PDFs where college header and table span different pages.
    """
    all_text_blocks = []   # (page_num, text)
    all_table_blocks = []  # (page_num, raw_table)

    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        for page_num, page in enumerate(pdf.pages):
            if progress_callback:
                progress_callback(page_num + 1, total, f"Block scan page {page_num + 1}/{total}")

            text = page.extract_text() or ""
            all_text_blocks.append((page_num, text))

            tables = page.extract_tables() or []
            for t in tables:
                all_table_blocks.append((page_num, t))

    # Build a flat ordered structure
    full_text = "\n".join(t for _, t in all_text_blocks)
    segments = _split_into_college_segments(full_text)

    if not segments:
        return []

    # Now assign tables to segments by order
    colleges = []
    table_queue = list(all_table_blocks)
    table_ptr = 0

    for seg in segments:
        # Each segment = one college. Find matching tables.
        # Heuristic: consume tables until we hit a table that looks like
        # it belongs to the next college (detect header row again).
        seg_tables = []
        while table_ptr < len(table_queue):
            _, raw = table_queue[table_ptr]
            rows = _clean_raw_table(raw)
            if rows:
                seg_tables.extend(rows)
            table_ptr += 1
            # Stop after consuming at least one non-empty table
            # and the next table starts a new college block
            if seg_tables and table_ptr < len(table_queue):
                next_raw = table_queue[table_ptr][1]
                if _table_is_header_table(next_raw) and len(seg_tables) > 1:
                    break

        df = _rows_to_dataframe(seg_tables) if seg_tables else pd.DataFrame()
        colleges.append({
            "college_code": seg["code"],
            "college_name": seg["name"],
            "college_header": seg["header"],
            "table": df,
        })

    return colleges


def _split_into_college_segments(full_text: str) -> list[dict]:
    segments = []
    matches = list(COLLEGE_PATTERN.finditer(full_text))
    for i, m in enumerate(matches):
        full_match = m.group(1).strip()
        code_match = re.match(r"([A-Z]\d{3,4})", full_match)
        code = code_match.group(1) if code_match else "UNKNOWN"
        segments.append({
            "code": code,
            "name": full_match,
            "header": m.group(0).strip(),
        })
    return segments


def _table_is_header_table(raw_table) -> bool:
    if not raw_table or not raw_table[0]:
        return False
    first_row = [str(c or "") for c in raw_table[0]]
    return any("Course Name" in c or "1G" in c for c in first_row)


def _clean_raw_table(raw_table: list) -> list[list]:
    """Remove None cells, strip whitespace, skip fully-empty rows."""
    cleaned = []
    for row in raw_table:
        if row is None:
            continue
        cells = [str(c).strip().replace("\n", " ") if c is not None else "" for c in row]
        if any(c for c in cells):
            cleaned.append(cells)
    return cleaned


def _rows_to_dataframe(rows: list[list]) -> Optional[pd.DataFrame]:
    """
    Convert a list of raw rows into a DataFrame with proper headers.
    Detect the header row (contains '1G' or 'Course Name') and use it.
    """
    if not rows:
        return None

    # Find header row
    header_idx = None
    for i, row in enumerate(rows):
        row_str = " ".join(row).upper()
        if "1G" in row_str and ("COURSE" in row_str or "GM" in row_str):
            header_idx = i
            break
        if "COURSE NAME" in row_str:
            header_idx = i
            break

    if header_idx is None:
        # Try to use the first row
        header_idx = 0

    headers = rows[header_idx]
    data_rows = rows[header_idx + 1 :]

    if not data_rows:
        return None

    # Normalize column count
    n_cols = len(headers)
    normalized = []
    for row in data_rows:
        if len(row) < n_cols:
            row = row + [""] * (n_cols - len(row))
        elif len(row) > n_cols:
            row = row[:n_cols]
        normalized.append(row)

    df = pd.DataFrame(normalized, columns=headers)

    # Drop rows that are completely empty or just duplicates of header
    df = df.dropna(how="all")
    df = df[~df.apply(lambda r: " ".join(str(v) for v in r).strip() == "", axis=1)]

    # Remove header-repeat rows inside data
    if "Course Name" in df.columns or (df.columns[0] if len(df.columns) > 0 else "") == "Course Name":
        first_col = df.columns[0]
        df = df[df[first_col].str.upper() != "COURSE NAME"]

    df = df.reset_index(drop=True)
    return df if not df.empty else None


# ──────────────────────────────────────────────────────────────────────────────
# OCR fallback
# ──────────────────────────────────────────────────────────────────────────────

def _extract_with_ocr(pdf_path: str, progress_callback=None) -> list[dict]:
    """
    Rasterize each page with PyMuPDF, run Tesseract OCR, parse the text.
    """
    try:
        import pytesseract
        from PIL import Image
        import io
    except ImportError:
        logger.error("pytesseract / Pillow not available for OCR fallback")
        return []

    doc = fitz.open(pdf_path)
    total = len(doc)
    all_text = []

    for page_num in range(total):
        if progress_callback:
            progress_callback(page_num + 1, total, f"OCR page {page_num + 1}/{total}")

        page = doc[page_num]
        mat = fitz.Matrix(2.0, 2.0)  # 2x zoom for better OCR
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
        img_data = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_data))

        text = pytesseract.image_to_string(img, config="--psm 6")
        all_text.append(text)

    doc.close()

    full_text = "\n".join(all_text)
    segments = _split_into_college_segments(full_text)

    # For OCR, we parse tables from the text lines (no native table extraction)
    colleges = []
    for seg in segments:
        colleges.append({
            "college_code": seg["code"],
            "college_name": seg["name"],
            "college_header": seg["header"],
            "table": pd.DataFrame(),  # OCR text parsing is approximate
        })

    return colleges
