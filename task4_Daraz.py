

import os, re, time, shutil
from dataclasses import dataclass, asdict
from typing import List, Optional, Tuple, Set

import pandas as pd
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.firefox.options import Options as FxOptions
from selenium.webdriver.firefox.service import Service as FxService
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


BASE_URL = "https://www.daraz.pk"
QUERY = "iphone 15"
MIN_ITEMS = 20
MAX_PAGES = 4
HEADLESS = True
NAV_PAUSE = 0.8

BROWSER_ORDER = ["edge", "chrome", "firefox"]
ALLOW_DRIVER_DOWNLOADS = False   # keep False to avoid hangs

DELIVERY_KEYWORDS = [
    "Free Delivery", "Fulfilled by Daraz", "Daraz Verified", "Mall", "Global", "Cash on Delivery"
]


@dataclass
class Item:
    Title: str
    Price: Optional[str]
    Seller: Optional[str]
    Ratings: Optional[str]
    DeliveryOptions: Optional[str]
    ProductURL: Optional[str]


def _which(names: list) -> Optional[str]:
    here = os.getcwd()
    for n in names:
        p1 = os.path.join(here, n)
        if os.path.exists(p1):
            return p1
        p2 = shutil.which(n)
        if p2:
            return p2
    return None

def _edge_opts(headless: bool) -> EdgeOptions:
    o = EdgeOptions()
    if headless:
        o.add_argument("--headless=new")
    o.add_argument("--no-sandbox"); o.add_argument("--disable-dev-shm-usage")
    o.add_argument("--disable-gpu"); o.add_argument("--window-size=1366,900")
    o.add_argument("--lang=en-US");  o.page_load_strategy = "eager"
    return o

def _chrome_opts(headless: bool) -> ChromeOptions:
    o = ChromeOptions()
    if headless:
        o.add_argument("--headless=new")
    o.add_argument("--no-sandbox"); o.add_argument("--disable-dev-shm-usage")
    o.add_argument("--disable-gpu"); o.add_argument("--window-size=1366,900")
    o.add_argument("--lang=en-US");  o.add_argument("--disable-blink-features=AutomationControlled")
    o.page_load_strategy = "eager"
    o.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36")
    for p in [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
        r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
    ]:
        pp = os.path.expandvars(p)
        if os.path.exists(pp):
            o.binary_location = pp
            break
    return o

def _fx_opts(headless: bool) -> FxOptions:
    o = FxOptions()
    if headless:
        o.add_argument("-headless")
    return o

def build_driver(headless: bool = True) -> webdriver.Remote:
    print("[init] building driver (no downloads)…", flush=True)
    local_edge = _which(["msedgedriver.exe", "msedgedriver"])
    local_chrome = _which(["chromedriver.exe", "chromedriver"])
    local_fx = _which(["geckodriver.exe", "geckodriver"])

    for which in BROWSER_ORDER:
        try:
            if which == "edge" and local_edge:
                print(f"[init] using LOCAL Edge driver: {local_edge}", flush=True)
                d = webdriver.Edge(service=EdgeService(local_edge), options=_edge_opts(headless))
                d.set_page_load_timeout(45); return d
            if which == "chrome" and local_chrome:
                print(f"[init] using LOCAL Chrome driver: {local_chrome}", flush=True)
                d = webdriver.Chrome(service=ChromeService(local_chrome), options=_chrome_opts(headless))
                d.set_page_load_timeout(45); return d
            if which == "firefox" and local_fx:
                print(f"[init] using LOCAL Firefox driver: {local_fx}", flush=True)
                d = webdriver.Firefox(service=FxService(local_fx), options=_fx_opts(headless))
                d.set_page_load_timeout(45); return d
        except Exception as e:
            print(f"[init] local {which} driver failed: {e}", flush=True)

    for which in BROWSER_ORDER:
        try:
            if which == "edge":
                print("[init] trying Edge via Selenium Manager…", flush=True)
                d = webdriver.Edge(options=_edge_opts(headless))
                d.set_page_load_timeout(45); print("[init] Edge ✓", flush=True); return d
            if which == "chrome":
                print("[init] trying Chrome via Selenium Manager…", flush=True)
                d = webdriver.Chrome(options=_chrome_opts(headless))
                d.set_page_load_timeout(45); print("[init] Chrome ✓", flush=True); return d
            if which == "firefox":
                print("[init] trying Firefox via Selenium Manager…", flush=True)
                d = webdriver.Firefox(options=_fx_opts(headless))
                d.set_page_load_timeout(45); print("[init] Firefox ✓", flush=True); return d
        except Exception as e:
            print(f"[init] {which} via Selenium Manager failed: {e}", flush=True)

    if ALLOW_DRIVER_DOWNLOADS:
        try:
            from webdriver_manager.microsoft import EdgeChromiumDriverManager
            exe = EdgeChromiumDriverManager().install()
            d = webdriver.Edge(service=EdgeService(executable_path=exe), options=_edge_opts(headless))
            d.set_page_load_timeout(45); print("[init] Edge via webdriver_manager ✓", flush=True); return d
        except Exception as e:
            print(f"[init] Edge webdriver_manager failed: {e}", flush=True)

    raise RuntimeError("No browser driver could be started. Put msedgedriver.exe/chromedriver.exe in your folder, or keep using Edge via Selenium Manager.")


def wait_css(driver, selector: str, to=20):
    return WebDriverWait(driver, to).until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))

def safe_text(el) -> str:
    try:
        return (el.text or "").strip()
    except Exception:
        return ""

def clean_price(s: str) -> str:
    s = s.replace("\u00a0", " ").strip()
    m = re.search(r"(Rs\.?\s*[\d,]+(?:\.\d+)?)", s, flags=re.I)
    return m.group(1) if m else s


def accept_any_cookies_or_popups(driver):
    XPATHS = [
        "//button[contains(., 'Accept') or contains(., 'accept') or contains(., 'Got it') or contains(., 'OK') or contains(., 'Ok')]",
        "//a[contains(., 'Accept')]",
    ]
    for xp in XPATHS:
        try:
            for b in driver.find_elements(By.XPATH, xp):
                if b.is_displayed() and b.is_enabled():
                    b.click(); time.sleep(0.3); return True
        except Exception:
            continue
    return False

def find_search_box(driver):
    C = ["input[type='search']", "input#q", "input[placeholder*='Search']",
         "input[aria-label*='Search']", "input[class*='search']"]
    for sel in C:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            if el.is_displayed(): return el
        except Exception:
            continue
    try: return driver.find_element(By.TAG_NAME, "input")
    except Exception: return None

def perform_search(driver, query: str):
    print("[nav] Daraz HOME …", flush=True)
    driver.get(BASE_URL); time.sleep(NAV_PAUSE); accept_any_cookies_or_popups(driver)
    print(f"[action] typing query: {query!r}", flush=True)
    box = find_search_box(driver)
    if not box: raise RuntimeError("Could not locate Daraz search box.")
    box.clear(); box.send_keys(query); time.sleep(0.2); box.send_keys(Keys.ENTER); time.sleep(1.2)
    if driver.current_url.rstrip("/") == BASE_URL.rstrip("/"):
        print("[hint] ENTER didn’t navigate; trying search button …", flush=True)
        for sel in ["button[type='submit']", "button[class*='search']", "form button"]:
            try:
                btn = driver.find_element(By.CSS_SELECTOR, sel)
                if btn.is_displayed() and btn.is_enabled(): btn.click(); break
            except Exception:
                continue
        time.sleep(1.2)
    try:
        wait_css(driver, "div[data-qa-locator^='general-products']", to=20)
        print("[ok] search results loaded", flush=True)
    except TimeoutException:
        print("[warn] results container not detected — will still attempt to parse", flush=True)


def parse_results_page_html(html: str) -> List[Item]:

    soup = BeautifulSoup(html, "lxml")
    out: List[Item] = []
    seen: Set[str] = set()


    cards = soup.select("div[data-qa-locator='product-item'], div[data-qa-locator^='product-item']")
    if not cards:
        # Fallback to generic tiles if QA locator missing
        cards = soup.select("div.gridItem, div.box--ujueT, div.c2prKC")

    for c in cards:

        a = c.select_one("a[href*='/products/']")
        if not a:
            a = c.find("a")
        href = (a.get("href") if a else "") or ""
        if href and not href.startswith("http"):
            href = "https://www.daraz.pk" + href
        if href and href in seen:
            continue
        if href:
            seen.add(href)


        title = (a.get("title") if a and a.has_attr("title") else "") or ""
        if not title:
            # Often nested div with title class(got from online resource)
            tnode = c.select_one("[class*='title'], [data-qa-locator*='title']")
            if tnode:
                title = tnode.get_text(" ", strip=True)
        if not title and a:
            title = a.get_text(" ", strip=True)
        if not title:
            img = c.select_one("img[alt]")
            if img and img.get("alt"):
                title = img.get("alt").strip()


        price = None
        for node in c.find_all(True, recursive=True):
            txt = node.get_text(" ", strip=True)
            if not txt:
                continue
            m = re.search(r"(Rs\.?\s*[\d,]+(?:\.\d+)?)", txt, flags=re.I)
            if m:
                price = m.group(1)
                break

        # Ratings:
        rating_bits = []
        full_text = c.get_text(" ", strip=True)
        for m in re.finditer(r"\(\d+\)|\b\d+(\.\d+)?\b|\b\d+(?:\.\d+)?k?\s+sold\b", full_text, flags=re.I):
            token = m.group(0)
            if len(token) <= 8:  # keep brief tokens
                rating_bits.append(token)
        ratings = ", ".join(sorted(set(rating_bits))) if rating_bits else None

        # Delivery Options
        delivery = []
        lt = full_text.lower()
        for kw in DELIVERY_KEYWORDS:
            if kw.lower() in lt:
                delivery.append(kw)
        delivery_str = ", ".join(sorted(set(delivery))) if delivery else None

        if not title and not href:
            continue

        out.append(Item(
            Title=title or "",
            Price=price,
            Seller=None,  # filled later by product page
            Ratings=ratings,
            DeliveryOptions=delivery_str,
            ProductURL=href or ""
        ))
    return out


def open_and_parse_product(driver, url: str) -> Tuple[Optional[str], Optional[str]]:
    if not url.startswith("http"): return (None, None)
    try: driver.get(url)
    except WebDriverException: return (None, None)
    time.sleep(0.8)
    seller = None; delivery_found = set()
    # textual seller
    try:
        blocks = driver.find_elements(
            By.XPATH,
            "//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'sold by') or "
            "contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'seller')]")
        for b in blocks:
            try:
                link = b.find_element(By.XPATH, ".//following::a[1]")
                txt = link.text.strip()
                if txt: seller = txt; break
            except Exception:
                t = b.text.strip()
                if ":" in t: seller = t.split(':',1)[-1].strip(); break
    except Exception: pass
    # store link
    if not seller:
        try:
            for a in driver.find_elements(By.XPATH, "//a[contains(@href,'/shop/')]"):
                txt = a.text.strip()
                if txt and len(txt) > 2: seller = txt; break
        except Exception: pass

    try:
        soup = BeautifulSoup(driver.page_source, "lxml")
        for s in soup.select("script[type='application/ld+json']"):
            raw = s.string or s.text or ""
            if not raw: continue
            m = re.search(r'"seller"\s*:\s*{[^}]*"name"\s*:\s*"([^"]+)"', raw, flags=re.I)
            if m: seller = m.group(1).strip(); break
        page_text = soup.get_text(" ").lower()
        for kw in DELIVERY_KEYWORDS:
            if kw.lower() in page_text: delivery_found.add(kw)
    except Exception: pass
    return (seller, (", ".join(sorted(delivery_found)) if delivery_found else None))


def find_and_click_next(driver) -> bool:
    X = ["//a[@aria-label='Next' or @title='Next']",
         "//li[contains(@class,'ant-pagination-next')]//a",
         "//button[contains(., 'Next')]", "//a[contains(., 'Next')]"]
    for xp in X:
        try:
            el = driver.find_element(By.XPATH, xp)
            if el.is_displayed() and el.is_enabled():
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                time.sleep(0.2); el.click(); time.sleep(1.0); return True
        except Exception: continue
    return False

def perform_search(driver, query: str):
    print("[nav] Daraz HOME …", flush=True)
    driver.get(BASE_URL); time.sleep(NAV_PAUSE); accept_any_cookies_or_popups(driver)
    print(f"[action] typing query: {query!r}", flush=True)
    box = find_search_box(driver)
    if not box: raise RuntimeError("Could not locate Daraz search box.")
    box.clear(); box.send_keys(query); time.sleep(0.2); box.send_keys(Keys.ENTER); time.sleep(1.2)
    if driver.current_url.rstrip("/") == BASE_URL.rstrip("/"):
        print("[hint] ENTER didn’t navigate; trying search button …", flush=True)
        for sel in ["button[type='submit']", "button[class*='search']", "form button"]:
            try:
                btn = driver.find_element(By.CSS_SELECTOR, sel)
                if btn.is_displayed() and btn.is_enabled(): btn.click(); break
            except Exception:
                continue
        time.sleep(1.2)
    try:
        wait_css(driver, "div[data-qa-locator^='general-products']", to=20)
        print("[ok] search results loaded", flush=True)
    except TimeoutException:
        print("[warn] results container not detected — will still attempt to parse", flush=True)

def scrape_daraz_from_home(query=QUERY, n_min=MIN_ITEMS, headless=HEADLESS) -> pd.DataFrame:
    print("[run] Task 4 starting (TA-compliant: HOME → search) …", flush=True)
    driver = build_driver(headless=headless)
    rows: List[Item] = []
    seen_urls: Set[str] = set()
    try:
        perform_search(driver, query)

        page = 1
        while len(rows) < n_min and page <= MAX_PAGES:
            # Parse full page HTML (robust to nested markup)
            html = driver.page_source
            page_items = parse_results_page_html(html)
            print(f"[page {page}] parsed items from HTML: {len(page_items)}", flush=True)

            for it in page_items:
                if it.ProductURL and it.ProductURL in seen_urls:
                    continue
                seen_urls.add(it.ProductURL)
                rows.append(it)
                if len(rows) >= n_min:
                    break

            if len(rows) >= n_min:
                break

            moved = find_and_click_next(driver)
            print(f"[page {page}] next clicked: {moved}", flush=True)
            if not moved:
                break
            page += 1
            time.sleep(NAV_PAUSE)

        print(f"[info] collected base rows: {len(rows)}", flush=True)


        for i in range(min(n_min, len(rows))):
            it = rows[i]
            if it.Seller and it.DeliveryOptions:
                continue
            s, d = open_and_parse_product(driver, it.ProductURL or "")
            if s and not it.Seller:
                it.Seller = s
            if d:
                existing = set((it.DeliveryOptions or "").split(", ")) if it.DeliveryOptions else set()
                for piece in d.split(", "):
                    if piece:
                        existing.add(piece)
                it.DeliveryOptions = ", ".join(sorted(existing)) if existing else it.DeliveryOptions
            time.sleep(0.3)

        df = pd.DataFrame([asdict(x) for x in rows])
        if df.empty:
            print("[warn] No rows scraped. Markup may have changed or the page uses heavy client rendering.", flush=True)

        # Required fallbacks
        for col, default in [
            ("Price", "Not available"),
            ("Seller", "Not available"),
            ("Ratings", "Not available"),
            ("DeliveryOptions", "Not available"),
            ("ProductURL", ""),
        ]:
            if col in df.columns:
                df[col] = df[col].fillna(default)

        df.to_csv("daraz_iphone15_listings.csv", index=False, encoding="utf-8")
        print(f"[DONE] Scraped {len(df)} rows -> daraz_iphone15_listings.csv", flush=True)
        if not df.empty:
            print(df.head(10).to_string(index=False), flush=True)
        return df

    finally:
        try:
            driver.quit(); print("[close] browser closed", flush=True)
        except Exception:
            pass


if __name__ == "__main__":
    scrape_daraz_from_home()
