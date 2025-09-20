

import re, time, random
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin

import requests
import pandas as pd
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeout

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException


QS_BASE = "https://www.topuniversities.com"
QS_ARTICLE = QS_BASE + "/student-info/choosing-university/worlds-top-100-universities"
COOKIE_TEXTS = ("Accept all cookies", "Accept all", "Accept", "I agree", "Got it")

BROWSER   = "edge"   # chrome or edge: On chrome it was not dealing with pop-ups idk why
HEADLESS  = True     # This is where I emailed you to inform that marking it false initiates the process but does  not complete
TARGET_N  = 50
PAGE_LOAD_TIMEOUT = 35
EXPLICIT_WAIT     = 10


MAX_WORKERS = 12
CONNECT_TIMEOUT = 1.5
READ_TIMEOUT    = 2.0
TOTAL_COUNTRY_FETCH_BUDGET = 45

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

SLEEP_RANGE = (0.04, 0.10)
def nap(a=None, b=None):
    lo, hi = SLEEP_RANGE if a is None else (a, b)
    time.sleep(random.uniform(lo, hi))

@dataclass
class UniRow:
    University: str
    Country: Optional[str]
    OverallScore: Optional[float]
    SubjectRanking: str
    URL: str

#  Selenium set up here
def build_driver(headless=True) -> webdriver.Remote:
    if BROWSER.lower() == "edge":
        from selenium.webdriver.edge.options import Options as EdgeOptions
        opts = EdgeOptions(); opts.use_chromium = True
    else:
        from selenium.webdriver.chrome.options import Options as ChromeOptions
        opts = ChromeOptions()

    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-notifications")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--window-size=1500,980")
    opts.add_argument("--lang=en-US,en;q=0.9")
    opts.add_argument("--user-agent=" + REQUEST_HEADERS["User-Agent"])
    opts.page_load_strategy = "eager"
    try:
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)
    except Exception:
        pass

    driver = webdriver.Edge(options=opts) if BROWSER.lower() == "edge" else webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    driver.implicitly_wait(2)
    driver.set_script_timeout(20)
    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"}
        )
    except Exception:
        pass
    return driver

def robust_get(driver, url):
    try:
        driver.get(url)
    except TimeoutException:
        try: driver.execute_script("window.stop();")
        except Exception: pass

def click_if_exists(driver, xpaths, timeout=4) -> bool:
    if isinstance(xpaths, str): xpaths = [xpaths]
    for xp in xpaths:
        try:
            el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((By.XPATH, xp)))
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            time.sleep(0.1)
            el.click()
            return True
        except Exception:
            continue
    return False

def accept_cookies(driver):
    for txt in COOKIE_TEXTS:
        if click_if_exists(driver, f"//button[contains(normalize-space(.), '{txt}')]", timeout=3):
            print("[cookies] accepted"); break

def kill_overlays(driver):
    # quiet overlay killer; no console spam
    try:
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
    except Exception:
        pass
    try:
        driver.execute_script("""
            const sel = "[role='dialog'],[aria-modal='true'],.modal,.Modal,.overlay,.Overlay,.modal-backdrop,.ReactModal__Overlay,[class*='newsletter'],[class*='signup']";
            document.querySelectorAll(sel).forEach(n=>{
              const cs = getComputedStyle(n);
              if (Number(cs.zIndex) >= 1000 || cs.position==='fixed' || cs.position==='sticky') {
                n.style.setProperty('display','none','important');
                n.style.setProperty('visibility','hidden','important');
                n.style.setProperty('pointer-events','none','important');
              }
            });
            document.documentElement.style.overflow='auto';
            document.body.style.overflow='auto';
        """)
    except Exception:
        pass

# Parsing article
BAD_TEXT = ("view programme","view programmes","view program","view programs","view courses","view course","find out more")
def is_valid_uni_name(name: str) -> bool:
    n = (name or "").strip().lower()
    return bool(n) and not any(b in n for b in BAD_TEXT)

def scrape_article_unis() -> List[UniRow]:
    driver = build_driver(HEADLESS)
    try:
        print(f"[nav] {QS_ARTICLE}")
        robust_get(driver, QS_ARTICLE)
        accept_cookies(driver)
        kill_overlays(driver)
        html = driver.page_source
    finally:
        try: driver.quit()
        except Exception: pass

    soup = BeautifulSoup(html, "lxml")
    anchors = soup.select("a[href*='/universities/']")
    seen = set()
    rows: List[UniRow] = []
    for a in anchors:
        name = a.get_text(strip=True)
        href = a.get("href","")
        if not name or "/universities/" not in href: continue
        if not is_valid_uni_name(name): continue
        if name in seen: continue
        seen.add(name)
        url = urljoin(QS_BASE, href)
        rows.append(UniRow(name, None, None, "Not listed", url))
        if len(rows) >= TARGET_N: break
    return rows


COUNTRY_NORMALIZE = {
    "Hong Kong SAR":"Hong Kong",
    "Hong Kong SAR China":"Hong Kong",
    "Mainland China":"China",
    "U.A.E.":"UAE",
    "Korea, South":"South Korea",
    "Russian Federation":"Russia",
}
# idk why but this is how it went
REGION_MAP = {
    # Europe
    "United Kingdom":"Europe","UK":"Europe","England":"Europe","Scotland":"Europe","Wales":"Europe",
    "Ireland":"Europe","France":"Europe","Germany":"Europe","Netherlands":"Europe","Switzerland":"Europe",
    "Sweden":"Europe","Denmark":"Europe","Finland":"Europe","Norway":"Europe","Italy":"Europe","Spain":"Europe",
    "Portugal":"Europe","Belgium":"Europe","Austria":"Europe","Poland":"Europe","Czechia":"Europe","Czech Republic":"Europe",
    "Hungary":"Europe","Greece":"Europe","Turkey":"Europe","Russia":"Europe",
    # North America
    "United States":"North America","USA":"North America","Canada":"North America",
    # Asia
    "China":"Asia","Hong Kong":"Asia","Macao":"Asia","Macau":"Asia","Taiwan":"Asia",
    "Japan":"Asia","Singapore":"Asia","South Korea":"Asia","Republic of Korea":"Asia",
    "India":"Asia","Pakistan":"Asia","Malaysia":"Asia","Thailand":"Asia","United Arab Emirates":"Asia","UAE":"Asia",
    "Saudi Arabia":"Asia","Qatar":"Asia","Kuwait":"Asia","Bangladesh":"Asia","Sri Lanka":"Asia","Indonesia":"Asia",
    # Oceania
    "Australia":"Oceania","New Zealand":"Oceania",
    # South America
    "Brazil":"South America","Argentina":"South America","Chile":"South America","Colombia":"South America","Peru":"South America",
    # Africa
    "South Africa":"Africa","Egypt":"Africa","Morocco":"Africa","Kenya":"Africa","Nigeria":"Africa","Ghana":"Africa","Tunisia":"Africa",
}

def normalize_country(c: Optional[str]) -> Optional[str]:
    if not c: return None
    c = c.strip()
    return COUNTRY_NORMALIZE.get(c, c)

def map_region(country: Optional[str]) -> str:
    c = normalize_country(country)
    if not c: return "Unknown"
    return REGION_MAP.get(c, "Unknown")

def _safe_json_parse(s: str) -> Optional[Any]:
    try:
        import json
        return json.loads(s)
    except Exception:
        return None

def _extract_country_via_jsonld(soup: BeautifulSoup) -> Optional[str]:
    for script in soup.select('script[type="application/ld+json"]'):
        data = _safe_json_parse(script.string or "")
        if not data:
            continue
        candidates = data if isinstance(data, list) else [data]
        for obj in candidates:
            if not isinstance(obj, dict):
                continue
            addr = obj.get("address")
            if isinstance(addr, dict):
                c = addr.get("addressCountry") or addr.get("addressCountryCode")
                if isinstance(c, str) and c.strip():
                    return c.strip()
            # Some pages have nested array for address
            if isinstance(addr, list):
                for a in addr:
                    if isinstance(a, dict):
                        c = a.get("addressCountry") or a.get("addressCountryCode")
                        if isinstance(c, str) and c.strip():
                            return c.strip()
    return None

def _extract_country_via_locations_links(soup: BeautifulSoup) -> Optional[str]:
    # Prefer the *last* sensible /locations/... anchor text (often Country in QS breadcrumbs)
    anchors = soup.select('a[href^="/locations/"], a[href*="topuniversities.com/locations/"]')
    texts = []
    for a in anchors:
        t = a.get_text(" ", strip=True)
        if t and len(t) >= 3 and re.search(r"[A-Za-z]", t):
            # Filter obvious city/area words only if they look like "City, Country" chains; we pick the longest later.
            texts.append(t)
    if not texts:
        return None
    # Heuristic: the longest text is often "Country" (e.g., "United Kingdom", "United States")
    texts = sorted(set(texts), key=lambda x: len(x), reverse=True)
    for t in texts:
        tt = t.strip()
        # Avoid over-specific phrases like "Study in ..." if present
        tt = re.sub(r"^(Study in|Universities in)\s+", "", tt, flags=re.I).strip()
        if 3 <= len(tt) <= 40:  # sane country name length
            return tt
    return None

def _extract_country_via_microdata(soup: BeautifulSoup) -> Optional[str]:
    meta = soup.select_one('[itemprop="addressCountry"]')
    if meta:
        txt = meta.get_text(strip=True)
        if txt:
            return txt
    return None

def _extract_country_via_textprobe(soup: BeautifulSoup) -> Optional[str]:
    # Safer text probe: look for "Location" or "Address" blocks and capture a trailing country token
    blocks = soup.select("[class*='location'], [class*='contact'], header, main, footer")
    txt = " ".join([b.get_text(" ", strip=True) for b in blocks])
    # Look for patterns like ", Country" near end; ensure the token is alphabetic (avoid "Si")
    m = re.search(r",\s*([A-Za-z][A-Za-z\.\-\s&\(\)]+)(?:\s*$|[\.]|,)", txt)
    if m:
        c = m.group(1).strip()
        # Prune obviously incomplete tiny tokens
        if len(c) >= 4:
            return c
    return None

def parse_country_from_html(html: str) -> Optional[str]:
    soup = BeautifulSoup(html, "lxml")
    for extractor in (
        _extract_country_via_jsonld,
        _extract_country_via_locations_links,
        _extract_country_via_microdata,
        _extract_country_via_textprobe,
    ):
        c = extractor(soup)
        if c and isinstance(c, str) and c.strip():
            return c.strip()
    return None

def fetch_country(url: str) -> Optional[str]:
    try:
        r = requests.get(url, headers=REQUEST_HEADERS, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
        if r.status_code != 200:
            return None
        return parse_country_from_html(r.text)
    except Exception:
        return None

def fill_countries_parallel(rows: List[UniRow], total_budget_sec=TOTAL_COUNTRY_FETCH_BUDGET) -> None:
    if not rows: return
    start = time.time()
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        future_by_idx = {ex.submit(fetch_country, r.URL): i for i, r in enumerate(rows)}
        done_count = 0
        try:
            for fut in as_completed(future_by_idx, timeout=total_budget_sec):
                idx = future_by_idx[fut]
                c = None
                try:
                    c = fut.result()
                except Exception:
                    c = None
                rows[idx].Country = normalize_country(c) or rows[idx].Country
                done_count += 1
                if done_count % 10 == 0:
                    print(f"[country] fetched {done_count}/{len(rows)}")
                if time.time() - start > total_budget_sec:
                    break
        except FuturesTimeout:
            pass


if __name__ == "__main__":
    # Getting 50 universities from the article via Selenium
    rows = scrape_article_unis()
    print(f"[article] extracted {len(rows)} universities")

    #  Filling countries in parallel
    print("[country] fetching profile countries (parallel, short timeouts)...")
    fill_countries_parallel(rows)

    # Building dataframe with required columns
    df = pd.DataFrame([r.__dict__ for r in rows],
                      columns=["University", "Country", "OverallScore", "SubjectRanking", "URL"])


    df["Country"] = df["Country"].apply(lambda x: normalize_country(x) if pd.notna(x) else None)
    df["Country"] = df["Country"].fillna("Unknown")
    df["Region"]  = df["Country"].apply(lambda c: map_region(None if c=="Unknown" else c))

    #  Saving CSVs
    df.to_csv("qs_top50.csv", index=False, encoding="utf-8")
    print(f"[done] qs_top50.csv saved ({len(df)} rows)")

    if not df.empty:
        by_country = (df.groupby("Country", dropna=False)
                        .agg(Universities=("University","count"),
                             AvgScore=("OverallScore","mean"))
                        .sort_values(["Universities","AvgScore"], ascending=[False,False])
                        .reset_index())
        by_region = (df.groupby("Region", dropna=False)
                        .agg(Universities=("University","count"),
                             AvgScore=("OverallScore","mean"))
                        .sort_values(["Universities","AvgScore"], ascending=[False,False])
                        .reset_index())
        by_country.head(15).to_csv("qs_by_country_top15.csv", index=False)
        by_region.to_csv("qs_by_region.csv", index=False)
        print("[done] summaries → qs_by_country_top15.csv, qs_by_region.csv")
    else:
        print("[info] skip summaries; dataframe empty")


    print(df.head(12).to_string(index=False))
