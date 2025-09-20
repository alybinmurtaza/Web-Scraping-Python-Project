# export_task3_reports.py
# Creates ONLY a PDF report for Task 3 (QS WUR Top 50)
# pip install reportlab pandas

import os
from datetime import datetime
import pandas as pd

# ---------------- Helpers ----------------
def now_iso() -> str:
    # Local time with timezone offset, second precision
    return datetime.now().astimezone().isoformat(timespec="seconds")

def safe_filename(stem: str, suffix: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{stem}_{ts}.{suffix.lstrip('.')}"

def maybe_read_csv(path: str) -> pd.DataFrame:
    return pd.read_csv(path) if os.path.exists(path) else pd.DataFrame()

# ---------------- Load Data ----------------
MAIN_CSV = "qs_top50.csv"  # produced by your Task 3 scraper
if os.path.exists(MAIN_CSV):
    df = pd.read_csv(MAIN_CSV)
else:
    raise FileNotFoundError(
        "qs_top50.csv not found. Run your Task 3 scraper first to create it."
    )

# Ensure expected columns exist (for transparency)
expected_cols = ["University", "Country", "OverallScore", "SubjectRanking", "Region"]
for col in expected_cols:
    if col not in df.columns:
        df[col] = ""  # fill missing columns so the PDF has a stable schema

# Optional summaries (silently skipped if missing)
by_country = maybe_read_csv("qs_by_country_top15.csv")
by_region = maybe_read_csv("qs_by_region.csv")

# ---------------- Build PDF ----------------
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

def _format_numeric_cols(df_: pd.DataFrame) -> pd.DataFrame:
    df_fmt = df_.copy()
    for col in df_fmt.select_dtypes(include="number"):
        df_fmt[col] = df_fmt[col].round(2)
    return df_fmt

def export_pdf_task3(df_top: pd.DataFrame,
                     df_by_country: pd.DataFrame,
                     df_by_region: pd.DataFrame,
                     out_path: str) -> str:
    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    normal = styles["Normal"]
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontName="Helvetica", fontSize=10.5, leading=14)

    doc = SimpleDocTemplate(
        out_path,
        pagesize=A4,
        leftMargin=36, rightMargin=36, topMargin=48, bottomMargin=48
    )
    story = []

    # Title + meta
    story.append(Paragraph("CS4048 – Task 3: QS World University Rankings (Top 50)", title_style))
    story.append(Paragraph(f"Generated: {now_iso()}", normal))
    story.append(Paragraph(f"Rows: {len(df_top)} | Source: topuniversities.com", normal))
    story.append(Spacer(1, 12))
    story.append(Paragraph(
        "This report includes the top 50 entries scraped from QS World University Rankings. "
        "Columns: University, Country, OverallScore, SubjectRanking, Region. "
        "SubjectRanking is joined from a QS subject page; missing entries show ‘Not listed’.",
        body
    ))
    story.append(Spacer(1, 12))

    # ---- Table 1: Top 50 (main) ----
    df_show = df_top.copy()
    # Add serial number column for readability
    df_show.insert(0, "#", range(1, len(df_show) + 1))
    # Reorder/limit columns to expected
    ordered_cols = ["#", "University", "Country", "OverallScore", "SubjectRanking", "Region"]
    df_show = df_show.reindex(columns=[c for c in ordered_cols if c in df_show.columns])
    df_show = _format_numeric_cols(df_show)

    data = [list(df_show.columns)]
    for _, row in df_show.iterrows():
        data.append([("" if pd.isna(v) else str(v)) for v in row.values])

    table_main = Table(
        data,
        colWidths=[25, 210, 100, 60, 85, 75]  # fits A4 with margins; tweak if needed
    )
    table_main.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(table_main)

    # ---- Optional: By-country summary ----
    if not df_by_country.empty:
        story.append(PageBreak())
        story.append(Paragraph("Summary — Universities by Country (Top 15)", styles["Heading2"]))
        df_c = _format_numeric_cols(df_by_country)
        data_c = [list(df_c.columns)] + [[("" if pd.isna(v) else str(v)) for v in r] for _, r in df_c.iterrows()]
        table_c = Table(data_c)
        table_c.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(table_c)

    # ---- Optional: By-region summary ----
    if not df_by_region.empty:
        story.append(PageBreak())
        story.append(Paragraph("Summary — Avg Score by Region", styles["Heading2"]))
        df_r = _format_numeric_cols(df_by_region)
        data_r = [list(df_r.columns)] + [[("" if pd.isna(v) else str(v)) for v in r] for _, r in df_r.iterrows()]
        table_r = Table(data_r)
        table_r.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(table_r)

    doc.build(story)
    return out_path

# ---------------- Run ----------------
pdf_out = safe_filename("Task3_QS_Report", "pdf")
export_pdf_task3(df_top=df, df_by_country=by_country, df_by_region=by_region, out_path=pdf_out)
print(f"Saved PDF: {pdf_out}")
