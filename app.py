"""
app.py
KCET Cutoff Analyser — Streamlit frontend.
"""

import sys
import os
import logging
import tempfile
import time
from pathlib import Path

import streamlit as st
import pandas as pd

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from table_extractor import extract_all_colleges
from branch_filter import filter_colleges, BRANCH_ALIASES
from export_pdf import export_to_pdf
from export_excel import export_to_excel, export_to_csv

# ──────────────────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(levelname)s — %(message)s")
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Page config
# ──────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="KCET Cutoff Analyser",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────────────────────────────────────
# Custom CSS
# ──────────────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@400;500;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* Main header */
.main-header {
    background: linear-gradient(135deg, #1a3a5c 0%, #2563a8 100%);
    color: white;
    padding: 2rem 2.5rem;
    border-radius: 12px;
    margin-bottom: 1.5rem;
    box-shadow: 0 4px 20px rgba(26,58,92,0.3);
}
.main-header h1 {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 2rem;
    font-weight: 700;
    margin: 0 0 0.25rem 0;
    letter-spacing: -0.5px;
}
.main-header p {
    font-size: 0.95rem;
    opacity: 0.85;
    margin: 0;
}

/* Step cards */
.step-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-left: 4px solid #2563a8;
    border-radius: 10px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 1rem;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.step-card h3 {
    color: #1a3a5c;
    font-size: 1rem;
    font-weight: 600;
    margin: 0 0 0.5rem 0;
}
.step-num {
    display: inline-block;
    background: #2563a8;
    color: white;
    border-radius: 50%;
    width: 24px;
    height: 24px;
    line-height: 24px;
    text-align: center;
    font-size: 0.8rem;
    font-weight: 700;
    margin-right: 0.5rem;
}

/* College result block */
.college-block {
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    overflow: hidden;
    margin-bottom: 1.25rem;
    box-shadow: 0 2px 8px rgba(0,0,0,0.05);
}
.college-block-header {
    background: #f0f4f8;
    border-bottom: 2px solid #2563a8;
    padding: 0.75rem 1rem;
    font-weight: 600;
    color: #1a3a5c;
    font-size: 0.9rem;
}

/* Stats badges */
.stat-badge {
    display: inline-block;
    background: #e8f0fe;
    color: #2563a8;
    border-radius: 20px;
    padding: 0.25rem 0.75rem;
    font-size: 0.8rem;
    font-weight: 600;
    margin: 0.15rem;
}

/* Alias hint */
.alias-hint {
    background: #fffbeb;
    border: 1px solid #fcd34d;
    border-radius: 8px;
    padding: 0.75rem 1rem;
    font-size: 0.82rem;
    color: #92400e;
    margin-top: 0.5rem;
}

/* Download button strip */
.download-strip {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 1rem 1.5rem;
    margin: 1rem 0;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background: #1a3a5c !important;
}
section[data-testid="stSidebar"] * {
    color: #e2e8f0 !important;
}
section[data-testid="stSidebar"] .stTextArea textarea {
    background: #243d5c !important;
    color: #e2e8f0 !important;
    border-color: #3d5a80 !important;
}

/* Progress */
.stProgress > div > div {
    background: linear-gradient(90deg, #2563a8, #60a5fa) !important;
}

/* Dataframe style override */
div[data-testid="stDataFrame"] {
    border-radius: 8px;
    overflow: hidden;
    border: 1px solid #e2e8f0;
}

/* Success message */
.success-banner {
    background: linear-gradient(90deg, #065f46, #047857);
    color: white;
    padding: 0.75rem 1.25rem;
    border-radius: 8px;
    font-weight: 600;
    font-size: 0.9rem;
    margin: 1rem 0;
}
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
# Session state
# ──────────────────────────────────────────────────────────────────────────────

def init_state():
    defaults = {
        "colleges": None,
        "filtered": None,
        "pdf_bytes": None,
        "excel_bytes": None,
        "csv_bytes": None,
        "last_pdf_name": None,
        "processing": False,
        "error": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_state()


# ──────────────────────────────────────────────────────────────────────────────
# Sidebar
# ──────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🎓 KCET Cutoff Analyser")
    st.markdown("---")

    st.markdown("### 📖 How it works")
    st.markdown("""
1. Upload the KCET PDF
2. Enter branch names
3. Click **Filter**
4. Download filtered results
    """)

    st.markdown("---")
    st.markdown("### 🔤 Supported Aliases")

    alias_data = [
        ("ME / MECH", "Mechanical Engineering"),
        ("CSE / CS", "Computer Science Engg"),
        ("ECE / EC", "Electronics & Comm."),
        ("CE / CIVIL", "Civil Engineering"),
        ("IT / IS", "Information Technology"),
        ("EEE", "Electrical & Electronics"),
        ("AI / AIDS / AIML", "AI & Data Science"),
        ("TEXTILE / TE", "Textile Technology"),
        ("SILK", "Silk Technology"),
    ]
    for alias, full in alias_data:
        st.markdown(f"**`{alias}`** → {full}")

    st.markdown("---")
    st.markdown("### ⚠️ Notes")
    st.caption("""
- Large PDFs (300+ pages) may take 1–3 min
- Only exact/partial matching is used — no data is fabricated
- All original column values are preserved
    """)


# ──────────────────────────────────────────────────────────────────────────────
# Main layout
# ──────────────────────────────────────────────────────────────────────────────

st.markdown("""
<div class="main-header">
  <h1>🎓 KCET Cutoff Analyser</h1>
  <p>Upload a KCET cutoff PDF → select branches → download filtered results as PDF, Excel, or CSV</p>
</div>
""", unsafe_allow_html=True)

col_left, col_right = st.columns([1.2, 1.8], gap="large")

# ── LEFT COLUMN: Controls ──
with col_left:
    # Step 1 — Upload
    st.markdown("""
    <div class="step-card">
      <h3><span class="step-num">1</span> Upload KCET PDF</h3>
    </div>
    """, unsafe_allow_html=True)

    uploaded_file = st.file_uploader(
        "Upload PDF",
        type=["pdf"],
        label_visibility="collapsed",
        help="Supports text-based and scanned PDFs up to 300+ pages",
    )

    if uploaded_file:
        file_size_mb = uploaded_file.size / (1024 * 1024)
        st.markdown(
            f'<span class="stat-badge">📄 {uploaded_file.name}</span>'
            f'<span class="stat-badge">💾 {file_size_mb:.1f} MB</span>',
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # Step 2 — Branches
    st.markdown("""
    <div class="step-card">
      <h3><span class="step-num">2</span> Enter Branches to Filter</h3>
    </div>
    """, unsafe_allow_html=True)

    branch_input = st.text_area(
        "One branch per line",
        placeholder="Mechanical Engineering\nCivil Engineering\nCSE\nTextile Technology\nSilk",
        height=160,
        label_visibility="collapsed",
    )

    st.markdown("""
    <div class="alias-hint">
    💡 <b>Tip:</b> You can use shortcuts like <code>ME</code>, <code>CSE</code>, <code>ECE</code>, <code>CIVIL</code>, <code>AIDS</code>, <code>AIML</code> etc.
    Partial names like "Mechanical" or "Civil" also work.
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Step 3 — Filter button
    st.markdown("""
    <div class="step-card">
      <h3><span class="step-num">3</span> Run Filter</h3>
    </div>
    """, unsafe_allow_html=True)

    fuzzy_threshold = st.slider(
        "Match sensitivity (higher = stricter)",
        min_value=0.50,
        max_value=1.00,
        value=0.75,
        step=0.05,
        help="0.75 recommended. Lower = more fuzzy matches. Higher = exact only.",
    )

    do_filter = st.button(
        "🔍 Filter Branches",
        type="primary",
        use_container_width=True,
        disabled=(uploaded_file is None or not branch_input.strip()),
    )


# ──────────────────────────────────────────────────────────────────────────────
# Processing
# ──────────────────────────────────────────────────────────────────────────────

if do_filter and uploaded_file and branch_input.strip():
    branches = [b.strip() for b in branch_input.strip().split("\n") if b.strip()]

    with col_right:
        st.markdown("### ⚙️ Processing...")
        progress_bar = st.progress(0, text="Starting extraction...")
        status_text = st.empty()

        def progress_cb(current, total, msg):
            pct = int((current / total) * 100) if total > 0 else 0
            progress_bar.progress(min(pct, 100), text=msg)
            status_text.caption(msg)

        try:
            # Save uploaded PDF to temp file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(uploaded_file.read())
                tmp_path = tmp.name

            status_text.caption("📄 Reading PDF structure...")
            t0 = time.time()

            # Extract
            colleges = extract_all_colleges(tmp_path, progress_callback=progress_cb)
            st.session_state.colleges = colleges

            elapsed_extract = time.time() - t0
            progress_bar.progress(80, text="🔍 Filtering branches...")

            # Filter
            filtered = filter_colleges(colleges, branches, similarity_threshold=fuzzy_threshold)
            st.session_state.filtered = filtered

            progress_bar.progress(90, text="📊 Generating exports...")

            # Generate exports
            if filtered:
                pdf_title = uploaded_file.name.replace(".pdf", "") + " — Filtered"
                st.session_state.pdf_bytes = export_to_pdf(filtered, title=pdf_title)
                st.session_state.excel_bytes = export_to_excel(filtered, title=pdf_title)
                st.session_state.csv_bytes = export_to_csv(filtered)

            st.session_state.last_pdf_name = uploaded_file.name
            st.session_state.error = None

            progress_bar.progress(100, text="✅ Done!")
            status_text.caption(
                f"Extraction: {elapsed_extract:.1f}s | "
                f"{len(colleges)} colleges found | "
                f"{len(filtered)} colleges matched"
            )

        except Exception as e:
            logger.exception("Processing error")
            st.session_state.error = str(e)
            progress_bar.progress(0)
            status_text.error(f"Error: {e}")

        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


# ──────────────────────────────────────────────────────────────────────────────
# Results display
# ──────────────────────────────────────────────────────────────────────────────

with col_right:
    if st.session_state.error:
        st.error(f"❌ {st.session_state.error}")

    filtered = st.session_state.filtered

    if filtered is not None:
        if not filtered:
            st.warning(
                "⚠️ No matching branches found. "
                "Try lower match sensitivity or check branch name spelling."
            )
        else:
            # Success banner
            n_colleges = len(filtered)
            n_branches = sum(
                len(c["table"]) for c in filtered
                if c["table"] is not None and not c["table"].empty
            )
            st.markdown(
                f'<div class="success-banner">'
                f'✅ Found <b>{n_branches}</b> branch rows across <b>{n_colleges}</b> colleges'
                f'</div>',
                unsafe_allow_html=True,
            )

            # ── Download strip ──
            st.markdown("### 📥 Step 4 — Download Results")
            st.markdown('<div class="download-strip">', unsafe_allow_html=True)

            dl1, dl2, dl3 = st.columns(3)

            base_name = (st.session_state.last_pdf_name or "kcet_filtered").replace(".pdf", "")

            with dl1:
                if st.session_state.pdf_bytes:
                    st.download_button(
                        label="⬇️ Download PDF",
                        data=st.session_state.pdf_bytes,
                        file_name=f"{base_name}_filtered.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                    )

            with dl2:
                if st.session_state.excel_bytes:
                    st.download_button(
                        label="⬇️ Download Excel",
                        data=st.session_state.excel_bytes,
                        file_name=f"{base_name}_filtered.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                    )

            with dl3:
                if st.session_state.csv_bytes:
                    st.download_button(
                        label="⬇️ Download CSV",
                        data=st.session_state.csv_bytes,
                        file_name=f"{base_name}_filtered.csv",
                        mime="text/csv",
                        use_container_width=True,
                    )

            st.markdown("</div>", unsafe_allow_html=True)

            # ── Preview ──
            st.markdown("### 👁️ Step 5 — Preview Results")

            # Filter options
            preview_col, search_col = st.columns([1, 2])
            with preview_col:
                max_preview = st.selectbox(
                    "Show colleges",
                    options=[5, 10, 20, 50, len(filtered)],
                    index=0,
                    label_visibility="collapsed",
                )
            with search_col:
                search_q = st.text_input(
                    "Search college name",
                    placeholder="🔍 Search college...",
                    label_visibility="collapsed",
                )

            visible = filtered
            if search_q.strip():
                q = search_q.strip().lower()
                visible = [
                    c for c in filtered
                    if q in c.get("college_name", "").lower()
                ]

            for college in visible[:max_preview]:
                df = college.get("table")
                if df is None or df.empty:
                    continue

                header = college.get("college_header", college.get("college_name", ""))
                code = college.get("college_code", "")

                with st.expander(
                    f"🏫 {header}  —  {len(df)} branch(es)",
                    expanded=(len(visible) <= 3),
                ):
                    st.dataframe(
                        df,
                        use_container_width=True,
                        hide_index=True,
                        height=min(40 + len(df) * 38, 400),
                    )

            if len(visible) > max_preview:
                st.caption(
                    f"Showing {max_preview} of {len(visible)} colleges. "
                    "Use the dropdown above to show more."
                )

    elif st.session_state.colleges is None:
        # Welcome state
        st.markdown("""
        <div style="text-align:center; padding:3rem; color:#64748b;">
            <div style="font-size:4rem; margin-bottom:1rem;">📄</div>
            <h3 style="color:#1a3a5c; font-family:'Space Grotesk',sans-serif;">
                Upload a PDF and select branches to get started
            </h3>
            <p style="max-width:400px; margin:0 auto; line-height:1.6;">
                The analyser will scan the entire KCET cutoff PDF and extract only 
                the branches you care about — preserving all original columns and values.
            </p>
        </div>
        """, unsafe_allow_html=True)
