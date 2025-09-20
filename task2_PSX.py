
import re
import time
import random
from datetime import datetime
from typing import List, Optional, Tuple

import requests
import pandas as pd
from bs4 import BeautifulSoup


PSX_MARKET_SUMMARY_URL = "https://www.psx.com.pk/market-summary/"
PSX_INDICES_URL        = "https://dps.psx.com.pk/indices"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")

def get_html(url: str, retries: int = 3, timeout: int = 20, backoff: float = 1.6) -> str:
    last_err = None
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            if r.status_code == 200:
                return r.text
            if r.status_code in (403, 429, 502, 503, 504):
                time.sleep((backoff ** attempt) + random.uniform(0, 0.4))
                continue
            r.raise_for_status()
        except requests.RequestException as e:
            last_err = e
            time.sleep((backoff ** attempt) + random.uniform(0, 0.3))
    raise RuntimeError(f"Failed to fetch {url}: {last_err}")

_num_cleaner = re.compile(r"[^0-9+\-\.eE]")

def _to_float(x):
    if pd.isna(x): return pd.NA
    s = str(x).strip()
    if s in ("", "-", "--"): return pd.NA
    s = s.replace(",", "")
    s = _num_cleaner.sub("", s)
    if s in ("", "+", "-"): return pd.NA
    try:
        return float(s)
    except Exception:
        return pd.NA

def _to_percent(x):
    if pd.isna(x): return pd.NA
    s = str(x)
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*%", s)
    if m:
        try:
            return float(m.group(1))
        except Exception:
            return pd.NA
    return _to_float(s)


def _pick_indices_table(html: str) -> pd.DataFrame:
    # Here I am Parsing all tables and picking the one containing typical index headers
    tables = pd.read_html(html, flavor="lxml")
    best_df, best_score = None, -1
    for df in tables:
        cols = [str(c).strip().lower() for c in df.columns]
        score = sum(int("index" in c) for c in cols) \
              + sum(int("high" in c) for c in cols) \
              + sum(int("low" in c) for c in cols) \
              + sum(int("current" in c) for c in cols) \
              + sum(int("change" in c) for c in cols) \
              + sum(int("%" in c) for c in cols)
        if score > best_score and len(df) > 0:
            best_df, best_score = df, score
    if best_df is None or best_df.empty:
        raise RuntimeError("Could not locate Indices table on DPS page.")
    return best_df

def collect_indices_from_dps() -> pd.DataFrame:

    html = get_html(PSX_INDICES_URL)
    soup = BeautifulSoup(html, "lxml")
    raw = _pick_indices_table(html)

    rename = {}
    for c in raw.columns:
        lc = str(c).strip().lower()
        if lc in ("index", "indices"): rename[c] = "Index Name"
        elif lc == "high":              rename[c] = "High"
        elif lc == "low":               rename[c] = "Low"
        elif "current" in lc:           rename[c] = "Current"
        elif "change%" in lc or "%" in lc:
            rename[c] = "Change %"
        elif lc == "change":            rename[c] = "Change"

    df = raw.rename(columns=rename).copy()

    #  here I am ensuring full schema
    target = ["Index Name","LDCP","Open","High","Low","Current","Change","Change %","Volume"]
    for col in target:
        if col not in df.columns:
            df[col] = pd.NA


    for col in ["High","Low","Current","Change"]:
        df[col] = df[col].map(_to_float)
    df["Change %"] = df["Change %"].map(_to_percent)


    def derive_ldcp(row):
        cur = row.get("Current", pd.NA)
        chg = row.get("Change",  pd.NA)
        if pd.notna(cur) and pd.notna(chg):
            try:
                return float(cur) - float(chg)
            except Exception:
                return pd.NA
        return pd.NA
    df["LDCP"] = df.apply(derive_ldcp, axis=1)


    df["Open"]   = pd.NA
    df["Volume"] = pd.NA


    asof = None
    txt = soup.get_text(" ", strip=True)
    m = re.search(r"As of\s+([A-Za-z]{3}\s+\d{1,2},\s+\d{4}\s+\d{1,2}:\d{2}\s*(?:AM|PM)?)", txt, flags=re.I)
    if m: asof = m.group(1)

    df["scraped_at"] = now_iso()
    df["source"] = "dps.psx.com.pk/indices"
    if asof: df["source_as_of"] = asof


    df = df[["Index Name","LDCP","Open","High","Low","Current","Change","Change %","Volume","scraped_at","source"] + (["source_as_of"] if asof else [])]
    return df.reset_index(drop=True)


def collect_mainboard_from_market_summary() -> pd.DataFrame:
    # summary
    html = get_html(PSX_MARKET_SUMMARY_URL)
    try:
        all_tables = pd.read_html(html, flavor="lxml")
    except ValueError:
        return pd.DataFrame(columns=["Index Name","LDCP","Open","High","Low","Current","Change","Volume"])

    picked = []
    for df in all_tables:
        cols = [str(c).strip().upper() for c in df.columns]
        header = " ".join(cols)
        # A decent match for main-board tables
        if ("SCRIP" in header) and sum(k in header for k in ["LDCP","OPEN","HIGH","LOW","CURRENT","CHANGE","VOLUME"]) >= 5:
            picked.append(df)

    if not picked:
        return pd.DataFrame(columns=["Index Name","LDCP","Open","High","Low","Current","Change","Volume"])

    big = pd.concat(picked, ignore_index=True)


    rename = {}
    for c in big.columns:
        u = str(c).strip().upper()
        if   u == "SCRIP":   rename[c] = "Index Name"  # assignment header says "Index Name / Scrip"
        elif u == "LDCP":    rename[c] = "LDCP"
        elif u == "OPEN":    rename[c] = "Open"
        elif u == "HIGH":    rename[c] = "High"
        elif u == "LOW":     rename[c] = "Low"
        elif u == "CURRENT": rename[c] = "Current"
        elif u == "CHANGE":  rename[c] = "Change"
        elif u == "VOLUME":  rename[c] = "Volume"

    big = big.rename(columns=rename)


    for col in ["Index Name","LDCP","Open","High","Low","Current","Change","Volume"]:
        if col not in big.columns:
            big[col] = pd.NA


    for col in ["LDCP","Open","High","Low","Current","Change","Volume"]:
        big[col] = big[col].map(_to_float)

    big["scraped_at"] = now_iso()
    big["source"] = "psx.com.pk/market-summary"
    return big[["Index Name","LDCP","Open","High","Low","Current","Change","Volume","scraped_at","source"]].reset_index(drop=True)


def main():
    # Indices High/Low/Current/Change/% and derived LDCP; Open/Volume = NA meaning they arw not published
    df_idx = collect_indices_from_dps()
    print(f"[Indices] rows: {len(df_idx)}")
    print(df_idx.head(10).to_string(index=False))
    df_idx.to_csv("psx_indices.csv", index=False)
    df_idx.to_json("psx_indices.json", orient="records", force_ascii=False)


    df_mb = collect_mainboard_from_market_summary()
    print(f"\n[Main Board] rows: {len(df_mb)}")
    print(df_mb.head(10).to_string(index=False))
    df_mb.to_csv("psx_mainboard.csv", index=False)
    df_mb.to_json("psx_mainboard.json", orient="records", force_ascii=False)

    print("\nSaved files:")
    print(" - psx_indices.csv / psx_indices.json   (Indices: High/Low/Current/Change/% + LDCP=Current-Change; Open/Volume not published → NA)")
    print(" - psx_mainboard.csv / psx_mainboard.json (Scrips: LDCP/Open/High/Low/Current/Change/Volume)")

if __name__ == "__main__":
    main()
