# 🎓 KCET Cutoff Analyser

A production-ready Streamlit application that extracts and filters specific engineering branches from large KCET cutoff PDFs.

---

## 📁 Project Structure

```
kcet_cutoff_analyser/
├── app.py                  ← Streamlit frontend (run this)
├── requirements.txt        ← Python dependencies
├── README.md
└── src/
    ├── __init__.py
    ├── table_extractor.py  ← Multi-strategy table extraction (pdfplumber → camelot → tabula)
    ├── branch_filter.py    ← Branch matching with alias support
    ├── export_pdf.py       ← Filtered PDF generation (ReportLab, landscape A3)
    └── export_excel.py     ← Filtered Excel + CSV generation (openpyxl)
```

---

## ⚙️ Installation

### Prerequisites

- Python 3.10 or higher
- Java (required by tabula-py) — [Download here](https://www.java.com/en/download/)
- Ghostscript (required by camelot) — [Download here](https://www.ghostscript.com/releases/gsdnld.html)
- Tesseract OCR (optional, for scanned PDFs) — [Download here](https://github.com/UB-Mannheim/tesseract/wiki)

### Step 1 — Create a virtual environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### Step 2 — Install dependencies

```bash
pip install -r requirements.txt
```

> If camelot fails to install, try:
> ```bash
> pip install camelot-py[cv]
> ```
> Or skip it — the app falls back to pdfplumber and tabula automatically.

### Step 3 — Run the app

```bash
streamlit run app.py
```

The app opens at **http://localhost:8501** in your browser.

---

## 🚀 How to Use

1. **Upload** your KCET cutoff PDF (supports 50–300+ page PDFs)
2. **Enter branches** — one per line:
   ```
   Mechanical Engineering
   Civil Engineering
   CSE
   Textile Technology
   Silk
   ```
3. **Click "Filter Branches"**
4. **Preview** results in the app
5. **Download** as PDF / Excel / CSV

---

## 🔤 Supported Aliases

| Shorthand | Full Name |
|-----------|-----------|
| `ME`, `MECH` | Mechanical Engineering |
| `CSE`, `CS` | Computer Science Engineering |
| `ECE`, `EC` | Electronics And Communication Engg |
| `CE`, `CIVIL` | Civil Engineering |
| `IT`, `IS` | Information Technology / Information Science |
| `EEE` | Electrical And Electronics Engineering |
| `AI`, `AIDS` | Artificial Intelligence And Data Science |
| `AIML` | Artificial Intelligence And Machine Learning |
| `TEXTILE`, `TE` | Textile Technology |
| `SILK` | Silk Technology |
| `BT`, `BIO` | Biotechnology |
| `AUTO`, `AE` | Automobile Engineering |

Partial names also work: type `Mechanical` to match `Mechanical Engineering`.

---

## 📊 Output

| Format | Contents |
|--------|----------|
| **PDF** | Landscape A3, KCET-style tables, one college per section |
| **Excel** | Summary sheet + one sheet per college, formatted |
| **CSV** | All data in a single flat CSV file |

---

## 🛠 Extraction Strategy

The app tries three extraction strategies in order:

1. **pdfplumber** — fast, accurate for text-based PDFs
2. **camelot** — lattice/stream mode for complex layouts
3. **tabula** — Java-based fallback

If all fail (scanned PDF), **Tesseract OCR** via PyMuPDF is used.

---

## 📌 Notes

- Output values are **never fabricated** — only values from the original PDF are used
- `--` is used where the original PDF has no data
- Column order is preserved exactly as in the source PDF
- Large PDFs (200–300 pages) may take 1–3 minutes to process

---

## 🐛 Troubleshooting

**"No colleges found"**
- Try uploading a smaller PDF to verify the format
- Make sure the PDF has selectable text (not a pure image scan)

**camelot import error**
- Install ghostscript and retry
- The app works without camelot (pdfplumber handles most KCET PDFs)

**tabula error**
- Make sure Java is installed and on your PATH

**Slow processing**
- Normal for large PDFs; watch the progress bar
