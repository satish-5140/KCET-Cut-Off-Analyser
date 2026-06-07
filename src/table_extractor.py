"""
table_extractor.py
Robust table extraction from KCET cutoff PDFs.
Strategy order: pdfplumber → camelot → tabula → OCR
Each college's table preserves original column order exactly.
"""

import logging
import re
from pathlib import Path
from typing import Optional
import io

import pdfplumber
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

COLLEGE_HEADER_RE = re.compile(
    r"College\s*:\s*([A-Z]\d{3,}[^\n]*)",
    re.IGNORECASE,
)

CUTOFF_COLUMNS = [
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
# Main extractor
# ──────────────────────────────────────────────────────────────────────────────

def extract_all_colleges(pdf_path: str, progress_callback=None) -> list[dict]:
    """
    Full extraction pipeline. Returns list of college dicts:
    {
        college_code, college_name, college_header,
        table: pd.DataFrame  (Course Name + cutoff cols)
    }
    """
    path = Path(pdf_path)
    colleges = []

    try:
        colleges = _pdfplumber_full_extraction(str(path), progress_callback)
    except Exception as e:
        logger.warning(f"pdfplumber full extraction failed: {e}")

    if not colleges:
        logger.info("Trying camelot extraction...")
        try:
            colleges = _camelot_extraction(str(path), progress_callback)
        except Exception as e:
            logger.warning(f"camelot failed: {e}")

    if not colleges:
        logger.info("Trying tabula extraction...")
        try:
            colleges = _tabula_extraction(str(path), progress_callback)
        except Exception as e:
            logger.warning(f"tabula failed: {e}")

    # Post-process: normalise column names, deduplicate rows
    for college in colleges:
        college["table"] = _normalize_table(college["table"])

    colleges = [c for c in colleges if c["table"] is not None and not c["table"].empty]
    logger.info(f"Extracted {len(colleges)} colleges with data.")
    return colleges


# ──────────────────────────────────────────────────────────────────────────────
# Strategy 1: pdfplumber — page-by-page, track college headers
# ──────────────────────────────────────────────────────────────────────────────

def _pdfplumber_full_extraction(pdf_path: str, progress_callback=None) -> list[dict]:
    colleges_raw: list[dict] = []  # {header_info, rows[]}

    current_college: Optional[dict] = None

    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)

        for page_num, page in enumerate(pdf.pages):
            if progress_callback:
                pct = int((page_num / total) * 100)
                progress_callback(page_num + 1, total, f"Extracting page {page_num + 1} / {total}")

            page_text = page.extract_text() or ""

            # Check for college headers in this page's text
            header_positions = []
            for m in COLLEGE_HEADER_RE.finditer(page_text):
                header_positions.append(m)

            # Extract tables from this page
            raw_tables = page.extract_tables(
                table_settings={
                    "vertical_strategy": "lines",
                    "horizontal_strategy": "lines",
                    "snap_tolerance": 6,
                    "join_tolerance": 4,
                    "edge_min_length": 8,
                    "min_words_vertical": 1,
                    "min_words_horizontal": 1,
                    "intersection_tolerance": 5,
                }
            ) or []

            if not raw_tables:
                # Try with text-based strategy
                raw_tables = page.extract_tables(
                    table_settings={
                        "vertical_strategy": "text",
                        "horizontal_strategy": "lines",
                        "snap_tolerance": 8,
                    }
                ) or []

            # If there are college headers on this page, start new college entries
            if header_positions:
                for m in header_positions:
                    full = m.group(1).strip()
                    cm = re.match(r"([A-Z]\d{3,})", full)
                    code = cm.group(1) if cm else "UNKNOWN"

                    new_college = {
                        "college_code": code,
                        "college_name": full,
                        "college_header": m.group(0).strip(),
                        "rows": [],
                    }
                    colleges_raw.append(new_college)
                    current_college = new_college
            elif not colleges_raw:
                # Create a placeholder college if no header seen yet
                current_college = {
                    "college_code": "UNKNOWN",
                    "college_name": "Unknown College",
                    "college_header": "",
                    "rows": [],
                }
                colleges_raw.append(current_college)

            # Assign all tables from this page to the LAST college header seen
            if current_college is None and colleges_raw:
                current_college = colleges_raw[-1]

            for raw_table in raw_tables:
                if not raw_table:
                    continue
                cleaned = _clean_table_rows(raw_table)
                if cleaned and current_college is not None:
                    current_college["rows"].extend(cleaned)

    # Convert to final format
    result = []
    seen_codes = {}
    for c in colleges_raw:
        code = c["college_code"]
        df = _rows_to_df(c["rows"])
        if df is None or df.empty:
            continue

        # Merge if same college code appears across pages
        if code in seen_codes:
            existing = seen_codes[code]
            try:
                existing["table"] = pd.concat(
                    [existing["table"], df], ignore_index=True
                ).drop_duplicates()
            except Exception:
                pass
        else:
            entry = {
                "college_code": c["college_code"],
                "college_name": c["college_name"],
                "college_header": c["college_header"],
                "table": df,
            }
            result.append(entry)
            seen_codes[code] = entry

    return result


# ──────────────────────────────────────────────────────────────────────────────
# Strategy 2: camelot
# ──────────────────────────────────────────────────────────────────────────────

def _camelot_extraction(pdf_path: str, progress_callback=None) -> list[dict]:
    import camelot
    tables = camelot.read_pdf(pdf_path, pages="all", flavor="lattice")
    if not tables or len(tables) == 0:
        tables = camelot.read_pdf(pdf_path, pages="all", flavor="stream")

    dfs = [t.df for t in tables if t.df is not None and not t.df.empty]
    if not dfs:
        return []

    # Since camelot doesn't give context, we stitch all into one big df
    # and group by college headers
    combined = pd.concat(dfs, ignore_index=True)
    return _split_by_college_header_df(combined)


# ──────────────────────────────────────────────────────────────────────────────
# Strategy 3: tabula
# ──────────────────────────────────────────────────────────────────────────────

def _tabula_extraction(pdf_path: str, progress_callback=None) -> list[dict]:
    import tabula
    dfs = tabula.read_pdf(
        pdf_path,
        pages="all",
        multiple_tables=True,
        pandas_options={"header": None},
        silent=True,
    )
    if not dfs:
        return []

    combined = pd.concat(dfs, ignore_index=True)
    return _split_by_college_header_df(combined)


def _split_by_college_header_df(df: pd.DataFrame) -> list[dict]:
    """
    Given a combined DataFrame from camelot/tabula, find college header rows
    and split into per-college chunks.
    """
    colleges = []
    current_rows = []
    current_info = None

    for _, row in df.iterrows():
        row_str = " ".join(str(v) for v in row.values)
        m = COLLEGE_HEADER_RE.search(row_str)
        if m:
            if current_info and current_rows:
                sub_df = _rows_to_df([[str(v) for v in r] for r in current_rows])
                if sub_df is not None and not sub_df.empty:
                    colleges.append({**current_info, "table": sub_df})
            full = m.group(1).strip()
            cm = re.match(r"([A-Z]\d{3,})", full)
            current_info = {
                "college_code": cm.group(1) if cm else "UNKNOWN",
                "college_name": full,
                "college_header": m.group(0).strip(),
            }
            current_rows = []
        else:
            current_rows.append(list(row.values))

    if current_info and current_rows:
        sub_df = _rows_to_df([[str(v) for v in r] for r in current_rows])
        if sub_df is not None and not sub_df.empty:
            colleges.append({**current_info, "table": sub_df})

    return colleges


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _clean_table_rows(raw_table: list) -> list[list]:
    result = []
    for row in raw_table:
        if row is None:
            continue
        cells = []
        for c in row:
            if c is None:
                cells.append("")
            else:
                cells.append(str(c).strip().replace("\n", " "))
        if any(c for c in cells):
            result.append(cells)
    return result


def _rows_to_df(rows: list[list]) -> Optional[pd.DataFrame]:
    if not rows:
        return None

    # Find header row: must contain "1G" or "Course Name"
    header_idx = None
    for i, row in enumerate(rows):
        joined = " ".join(row).upper()
        if ("1G" in joined or "GM" in joined) and len(row) > 5:
            header_idx = i
            break
        if "COURSE NAME" in joined:
            header_idx = i
            break

    if header_idx is None:
        # Heuristic: use first row if it has enough columns
        if rows and len(rows[0]) > 5:
            header_idx = 0
        else:
            return None

    headers = [h.strip() for h in rows[header_idx]]
    data = rows[header_idx + 1:]

    if not data:
        return None

    # Pad / trim rows to match header length
    n = len(headers)
    normalised = []
    for row in data:
        if len(row) < n:
            row = row + [""] * (n - len(row))
        normalised.append(row[:n])

    df = pd.DataFrame(normalised, columns=headers)

    # Drop rows where all cols empty
    df.replace("", np.nan, inplace=True)
    df.dropna(how="all", inplace=True)
    df.replace(np.nan, "--", inplace=True)

    # Remove header-repeat rows
    first_col = df.columns[0]
    df = df[~df[first_col].str.upper().str.contains("COURSE NAME", na=False)]
    df = df.reset_index(drop=True)

    return df if not df.empty else None


def _normalize_table(df: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    if df is None or df.empty:
        return df

    # Standardise the first column name to "Course Name"
    first_col = df.columns[0]
    if first_col != "Course Name":
        df = df.rename(columns={first_col: "Course Name"})

    # Strip whitespace from all string cells
    for col in df.columns:
        df[col] = df[col].astype(str).str.strip()

    # Replace empty strings / None-like values with --
    df.replace({"": "--", "None": "--", "nan": "--", "NaN": "--"}, inplace=True)

    # Remove duplicate rows
    df = df.drop_duplicates().reset_index(drop=True)

    return df
