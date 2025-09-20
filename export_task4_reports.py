# export_task4_report.py
# CS4048 – Task 4: Daraz "iPhone 15" — PDF report (fixed layout: wrapped cells + exact column widths)
# Requires: pip install pandas reportlab

import os
from pathlib import Path
from datetime import datetime

import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# ---------- Settings ----------
CSV_BASENAME = "daraz_iphone15_listings.csv"
OPEN_ON_SAVE = True  # auto-open PDF on Windows

# ---------- Small utils ----------
def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")

def safe_filename(stem: str, suffix: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{stem}_{ts}.{suffix.lstrip('.')}"

def ensure_columns(df: pd.DataFrame, columns):
    out = df.copy()
    for c in columns:
        if c not in out.columns:
            out[c] = ""
    return out[columns]

def script_dir() -> Path:
    return Path(__file__).resolve().parent

def find_csv() -> Path:
    candidates = [script_dir() / CSV_BASENAME, Path.cwd() / CSV_BASENAME]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(
        f"Could not find {CSV_BASENAME}. Looked in:\n - {candidates[0]}\n - {candidates[1]}"
    )

# ---------- PDF exporter ----------
def export_task4_pdf(df: pd.DataFrame, path: Path) -> Path:
    """
    Build a PDF report for Task 4 (Daraz iPhone 15).
    - All cells are Paragraphs (wraps long text)
    - Column widths are set to fit exactly within the printable width (no overlap)
    """
    base_cols = ["Title", "Price", "Seller", "Ratings", "DeliveryOptions", "ProductURL"]
    use_df = ensure_columns(df, base_cols).copy()
    use_df.insert(0, "#", range(1, len(use_df) + 1))
    columns = ["#", "Title", "Price", "Seller", "Ratings", "DeliveryOptions", "ProductURL"]

    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    normal = styles["Normal"]
    cell_style = ParagraphStyle(
        "Cell",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10.5,
        leading=14,          # generous leading prevents line collisions
    )

    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=36, rightMargin=36, topMargin=48, bottomMargin=48
    )

    story = []
    story.append(Paragraph("CS4048 – Task 4: Daraz iPhone 15 Listings", title_style))
    story.append(Paragraph(f"Generated: {now_iso()}", normal))
    story.append(Paragraph(f"Rows: {len(use_df)} | Source: daraz.pk (searched at runtime from homepage)", normal))
    story.append(Spacer(1, 10))

    # ---- Column widths that fit the printable width exactly ----
    # doc.width = page_width - leftMargin - rightMargin
    # Fractions sum to 1.0
    fractions = [0.05, 0.34, 0.09, 0.14, 0.10, 0.13, 0.15]
    col_widths = [f * doc.width for f in fractions]

    # ---- Build table data with Paragraphs in *every* cell (so they wrap) ----
    data = []
    # header row
    data.append([Paragraph(h, cell_style) for h in columns])

    # body rows
    for _, row in use_df.iterrows():
        title_p   = Paragraph(str(row["Title"]).strip(), cell_style)
        price_p   = Paragraph("" if pd.isna(row["Price"]) else str(row["Price"]), cell_style)
        seller_p  = Paragraph("" if pd.isna(row["Seller"]) else str(row["Seller"]), cell_style)
        ratings_p = Paragraph("" if pd.isna(row["Ratings"]) else str(row["Ratings"]), cell_style)
        deliv_p   = Paragraph("" if pd.isna(row["DeliveryOptions"]) else str(row["DeliveryOptions"]), cell_style)

        url_val = (row["ProductURL"] or "").strip()
        if url_val.startswith(("http://", "https://")):
            url_p = Paragraph(f'<link href="{url_val}">{url_val}</link>', cell_style)
        else:
            url_p = Paragraph("Not available", cell_style)

        data.append([
            Paragraph(str(row["#"]), cell_style),
            title_p, price_p, seller_p, ratings_p, deliv_p, url_p
        ])

    # Use explicit widths to avoid overflow; let ReportLab handle page splitting
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("WORDWRAP", (0, 0), (-1, -1), "CJK"),  # extra wrap help for long words/URLs
    ]))

    story.append(table)
    doc.build(story)
    return path

# ---------- Main ----------
def main():
    csv_path = find_csv()
    print(f"[info] Loading CSV from: {csv_path}")

    df = pd.read_csv(csv_path)
    expected = ["Title", "Price", "Seller", "Ratings", "DeliveryOptions", "ProductURL"]
    df = ensure_columns(df, expected)

    out_dir = script_dir() / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[info] Output folder: {out_dir}")

    pdf_path = out_dir / safe_filename("Task4_Daraz_Listings_Report", "pdf")
    export_task4_pdf(df, pdf_path)

    abs_path = pdf_path.resolve()
    print("\nSaved PDF:")
    print(" -", abs_path)
    print(" - file:///" + str(abs_path).replace("\\", "/"))

    if OPEN_ON_SAVE and os.name == "nt":
        try:
            os.startfile(str(abs_path))
            print("[info] Auto-opened PDF in your default viewer.")
        except Exception as e:
            print(f"[warn] Could not auto-open PDF: {e}")

if __name__ == "__main__":
    main()
