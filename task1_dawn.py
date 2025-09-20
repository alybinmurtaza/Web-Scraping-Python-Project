# task1_dawn.py
import time
import random
from urllib.parse import urljoin
from datetime import datetime

import requests
from bs4 import BeautifulSoup
import pandas as pd


BASE_URLS = [
    "https://www.dawn.com",
    "https://www.dawn.com/latest-news",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


def get_html(url, retries=3, timeout=15, backoff=1.6):

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


def parse_dawn_articles(html, base="https://www.dawn.com"):

    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for a in soup.select("h1 a[href], h2 a[href], h3 a[href]"):
        href = (a.get("href") or "").strip()
        if "/news/" not in href:
            continue
        headline = a.get_text(" ", strip=True).replace("Image:", "").strip()
        if not headline or len(headline) < 5:
            continue
        url = urljoin(base, href)
        rows.append({"headline": headline, "url": url})

    # deduplicate by URL, keeping thr order maintained
    seen = set()
    unique_rows = []
    for row in rows:
        if row["url"] not in seen:
            seen.add(row["url"])
            unique_rows.append(row)
    return unique_rows


def collect_dawn_headlines(n=30):
    collected = []
    for u in BASE_URLS:
        try:
            html = get_html(u)
            collected.extend(parse_dawn_articles(html))
            if len(collected) >= n:
                break
        except Exception as e:
            print(f"[warn] {u}: {e}")

    df = pd.DataFrame(collected[:n], columns=["headline", "url"])
    if df.empty:
        df = pd.DataFrame(columns=["headline", "url"])
    df["url"] = df["url"].fillna("No URL available")


    df["scraped_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df["source"] = "dawn.com"
    return df


def main():
    df = collect_dawn_headlines(30)
    print(f"Collected {len(df)} rows")
    # quick preview
    print(df.head(10).to_string(index=False))


    df.to_csv("dawn_top30_headlines.csv", index=False)
    df.to_json("dawn_top30_headlines.json", orient="records", force_ascii=False)
    print("\nSaved: dawn_top30_headlines.csv and dawn_top30_headlines.json")


if __name__ == "__main__":
    main()
