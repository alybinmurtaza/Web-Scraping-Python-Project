# export_task5_report.py
# CS4048 – Task 5: Goodreads Genres — PDF report (wrapped cells + exact column widths)
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
CSV_BASENAME = "goodreads_books.csv"
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

# ---------- Summary (optional but tiny) ----------
def summarize_avg_ratings(df: pd.DataFrame) -> pd.DataFrame:
    # Keep genres even if they had only NaNs
    grp = (df.groupby("Genre", as_index=False)["Rating"]
             .mean(skipna=True)
             .rename(columns={"Rating": "Average Rating"}))
    rated_counts = (df.groupby("Genre")["Rating"].apply(lambda s: s.notna().sum())
                      .rename("Rated Books"))
    out = grp.merge(rated_counts, on="Genre", how="left")
    # Sort: highest average first; NaNs last
    return out.sort_values(["Average Rating"], ascending=[False], na_position="last")

# ---------- PDF exporter ----------
def export_task5_pdf(df: pd.DataFrame, path: Path) -> Path:
    """
    Build a PDF report for Task 5 (Goodreads Genres).
    - All cells are Paragraphs (wraps long text)
    - Column widths fit exactly within the printable width
    - Includes a small 'Average Ratings by Genre' table at the top
    """
    base_cols = ["Genre", "Title", "Author", "Rating", "Number of Reviews", "Publication Date", "URL"]
    use_df = ensure_columns(df, base_cols).copy()
    use_df.insert(0, "#", range(1, len(use_df) + 1))
    columns = ["#", "Genre", "Title", "Author", "Rating", "Number of Reviews", "Publication Date", "URL"]

    # Styles
    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    normal = styles["Normal"]
    cell_style = ParagraphStyle(
        "Cell",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10.0,
        leading=13,  # generous leading helps long URLs/lines
    )

    # Document
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=36, rightMargin=36, topMargin=48, bottomMargin=48
    )

    story = []
    # Header
    story.append(Paragraph("CS4048 – Task 5: Goodreads Genres — Books", title_style))
    genres_used = ", ".join(sorted(str(g) for g in use_df["Genre"].unique()))
    rated_count = use_df["Rating"].notna().sum()
    story.append(Paragraph(f"Generated: {now_iso()}", normal))
    story.append(Paragraph(
        f"Rows: {len(use_df)} | Genres: {genres_used} | Rated rows: {rated_count}",
        normal
    ))
    story.append(Spacer(1, 10))

    # ---- Average Ratings by Genre (small table) ----
    try:
        summary = summarize_avg_ratings(use_df.rename(columns={"Number of Reviews": "Reviews"}))
        if not summary.empty:
            story.append(Paragraph("Average Ratings by Genre", styles["Heading3"]))
            # Convert to table rows
            sum_data = [[Paragraph(h, cell_style) for h in ["Genre", "Average Rating", "Rated Books"]]]
            for _, r in summary.iterrows():
                avg = "" if pd.isna(r["Average Rating"]) else f"{float(r['Average Rating']):.2f}"
                sum_data.append([
                    Paragraph(str(r["Genre"]), cell_style),
                    Paragraph(avg, cell_style),
                    Paragraph(str(int(r["Rated Books"])), cell_style),
                ])
            sum_table = Table(sum_data, colWidths=[0.35*doc.width, 0.25*doc.width, 0.4*doc.width], repeatRows=1)
            sum_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]))
            story.append(sum_table)
            story.append(Spacer(1, 12))
    except Exception:
        # If summary fails for any reason, just skip it — the main table still exports
        story.append(Paragraph("Average Ratings by Genre: not available", normal))
        story.append(Spacer(1, 12))

    # ---- Column widths that fit the printable width exactly ----
    # Fractions sum to 1.0. Tweak as you like; these are balanced for readability.
    fractions = [
        0.05,  # #
        0.10,  # Genre
        0.28,  # Title
        0.17,  # Author
        0.07,  # Rating
        0.10,  # Number of Reviews
        0.13,  # Publication Date
        0.10,  # URL (wrapped with link)
    ]
    assert abs(sum(fractions) - 1.0) < 1e-6, "Column fractions must sum to 1.0"
    col_widths = [f * doc.width for f in fractions]

    # ---- Build table data with Paragraphs in every cell (so they wrap) ----
    data = []
    data.append([Paragraph(h, cell_style) for h in columns])  # header

    def fmt_rating(x):
        if pd.isna(x):
            return ""
        try:
            return f"{float(x):.2f}"
        except Exception:
            return str(x)

    def fmt_reviews(x):
        if pd.isna(x) or str(x).strip().lower() == "not available":
            return "Not Available"
        try:
            return f"{int(float(x)):,}"
        except Exception:
            return str(x)

    for _, row in use_df.iterrows():
        # URL as clickable link if it looks like a URL
        url_val = str(row["URL"]).strip()
        if url_val.startswith(("http://", "https://")):
            url_p = Paragraph(f'<link href="{url_val}">{url_val}</link>', cell_style)
        else:
            url_p = Paragraph("Not available", cell_style)

        data.append([
            Paragraph(str(row["#"]), cell_style),
            Paragraph(str(row["Genre"]), cell_style),
            Paragraph(str(row["Title"]).strip(), cell_style),
            Paragraph(str(row["Author"]).strip(), cell_style),
            Paragraph(fmt_rating(row["Rating"]), cell_style),
            Paragraph(fmt_reviews(row["Number of Reviews"]), cell_style),
            Paragraph(str(row["Publication Date"]).strip(), cell_style),
            url_p
        ])

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
        ("WORDWRAP", (0, 0), (-1, -1), "CJK"),  # helps with long words/URLs
    ]))

    story.append(table)
    doc.build(story)
    return path

# ---------- Main ----------
def main():
    csv_path = find_csv()
    print(f"[info] Loading CSV from: {csv_path}")

    df = pd.read_csv(csv_path)
    expected = ["Genre", "Title", "Author", "Rating", "Number of Reviews", "Publication Date", "URL"]
    df = ensure_columns(df, expected)

    out_dir = script_dir() / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[info] Output folder: {out_dir}")

    pdf_path = out_dir / safe_filename("Task5_Goodreads_Report", "pdf")
    export_task5_pdf(df, pdf_path)

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
