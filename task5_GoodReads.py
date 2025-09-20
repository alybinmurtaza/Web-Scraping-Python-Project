
import time
import re
import random
from typing import List, Dict, Any, Optional, Tuple

import pandas as pd
import numpy as np

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchWindowException, ElementClickInterceptedException


GENRES = [
    "fiction",
    "mystery",

]

BOOKS_PER_GENRE = 12
HEADLESS = True

PAGE_LOAD_TIMEOUT = 90
IMPLICIT_WAIT = 2
EXPLICIT_WAIT = 25
SCROLL_PAUSE = 0.7

SLEEP_BETWEEN_REQUESTS = (0.6, 1.4)
PARTIAL_SAVE_EVERY = 8

def human_sleep(lo_hi=SLEEP_BETWEEN_REQUESTS):
    time.sleep(random.uniform(lo_hi[0], lo_hi[1]))



def make_driver(headless: bool = True) -> webdriver.Chrome:
    opts = ChromeOptions()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1600,1000")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--blink-settings=imagesEnabled=false")  # speed
    opts.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    opts.page_load_strategy = "eager"

    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    driver.implicitly_wait(IMPLICIT_WAIT)
    driver.set_script_timeout(30)
    return driver



def safe_text(el) -> str:
    try:
        return el.text.strip()
    except Exception:
        return ""

def click_if_exists(driver, by, value) -> bool:
    try:
        el = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((by, value)))
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        except Exception:
            pass
        el.click()
        return True
    except Exception:
        return False

def parse_int(s: str) -> Optional[int]:
    if not s:
        return None
    m = re.findall(r"\d[\d,]*", s.replace("\u202f","").replace("\xa0"," "))
    if not m:
        return None
    try:
        return int(m[-1].replace(",", ""))
    except Exception:
        return None

def parse_float(s: str) -> Optional[float]:
    if not s:
        return None
    m = re.search(r"(\d+\.\d+|\d+)", s)
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None

def scroll_for_more(driver, steps=4, pause=SCROLL_PAUSE):
    for _ in range(steps):
        driver.execute_script("window.scrollBy(0, document.body.scrollHeight);")
        time.sleep(pause)

def robust_get(driver, url: str, tries: int = 3):
    last_err = None
    for attempt in range(1, tries + 1):
        try:
            driver.get(url)
            return
        except TimeoutException as e:
            last_err = e
            try:
                driver.execute_script("window.stop();")
            except Exception:
                pass
            if attempt == tries:
                raise last_err
            time.sleep(1.4)



def handle_cookie_banner(driver):
    patterns = [
        (By.CSS_SELECTOR, "button[aria-label='Accept all']"),
        (By.CSS_SELECTOR, "button#onetrust-accept-btn-handler"),
        (By.XPATH, "//button[contains(., 'Accept') or contains(., 'I agree') or contains(., 'accept')]"),
    ]
    for by, sel in patterns:
        if click_if_exists(driver, by, sel):
            break

def kill_overlays(driver):

    candidates = [
        # modal close buttons and dismissals
        (By.CSS_SELECTOR, "button[aria-label='Close']"),
        (By.CSS_SELECTOR, "button[aria-label='Dismiss']"),
        (By.CSS_SELECTOR, "button[aria-label='Not now']"),
        (By.CSS_SELECTOR, "div.ReactModal__Overlay button"),
        (By.CSS_SELECTOR, "div.modal__content button"),
        (By.XPATH, "//button[contains(.,'Not now') or contains(.,'Close') or contains(.,'Maybe later')]"),
        # sign-in upsell drawers
        (By.CSS_SELECTOR, "div[class*='signup'] button"),
        (By.CSS_SELECTOR, "div[role='dialog'] button"),
    ]
    closed_any = False
    for by, sel in candidates:
        try:
            btns = driver.find_elements(by, sel)
            for b in btns[:3]:  # click at most a few
                if b.is_displayed():
                    try:
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", b)
                    except Exception:
                        pass
                    try:
                        b.click()
                        closed_any = True
                        time.sleep(0.3)
                    except Exception:
                        continue
        except Exception:
            continue
    return closed_any

def looks_like_captcha(driver) -> bool:
    html = driver.page_source.lower()
    return ("are you human" in html) or ("unusual traffic" in html) or ("captcha" in html)



def open_genre_list(driver, genre: str):
    robust_get(driver, "https://www.goodreads.com/?utm_source=chatgpt.com")
    handle_cookie_banner(driver)
    kill_overlays(driver)

    candidates = [
        f"https://www.goodreads.com/list/tag/{genre}",
        f"https://www.goodreads.com/shelf/show/{genre}?page=1",
    ]

    last_err = None
    for url in candidates:
        try:
            robust_get(driver, url)
            handle_cookie_banner(driver)
            kill_overlays(driver)

            WebDriverWait(driver, EXPLICIT_WAIT).until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR, ".tableList tr, .elementList, a.bookTitle"
                ))
            )
            return
        except Exception as e:
            last_err = e

    raise last_err

def collect_book_links_from_list(driver, need: int) -> List[str]:
    links = []
    tried_pages = 0

    while len(links) < need and tried_pages < 6:
        scroll_for_more(driver, steps=3)
        kill_overlays(driver)

        # Old Listopia table
        rows = driver.find_elements(By.CSS_SELECTOR, ".tableList tr")
        if rows:
            for r in rows:
                try:
                    a = r.find_element(By.CSS_SELECTOR, "a.bookTitle")
                    href = a.get_attribute("href")
                    if href and href not in links:
                        links.append(href)
                        if len(links) >= need:
                            break
                except Exception:
                    continue


        if len(links) < need:
            cards = driver.find_elements(By.CSS_SELECTOR, ".elementList a.bookTitle, a.bookTitle")
            for a in cards:
                try:
                    href = a.get_attribute("href")
                    if href and href not in links:
                        links.append(href)
                        if len(links) >= need:
                            break
                except Exception:
                    continue

        if len(links) >= need:
            break

        tried_pages += 1
        try:
            next_btn = None
            try:
                next_btn = driver.find_element(By.CSS_SELECTOR, "a.next_page")
            except Exception:
                try:
                    next_btn = driver.find_element(By.LINK_TEXT, "next »")
                except Exception:
                    next_btn = None

            if not next_btn:
                break

            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", next_btn)
            time.sleep(0.2)
            try:
                next_btn.click()
            except ElementClickInterceptedException:
                kill_overlays(driver)
                time.sleep(0.4)
                next_btn.click()

            WebDriverWait(driver, EXPLICIT_WAIT).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".tableList tr, .elementList, a.bookTitle"))
            )
        except Exception:
            break

    return links[:need]



def open_book_page(driver, url: str) -> Tuple[bool, str]:

    original = driver.current_window_handle
    handles_before = set(driver.window_handles)

    # Attempting new tab
    try:
        driver.execute_script("window.open(arguments[0], '_blank');", url)
        # waiting for a new handle
        for _ in range(20):
            handles_after = set(driver.window_handles)
            new_handles = handles_after - handles_before
            if new_handles:
                new_handle = list(new_handles)[0]
                driver.switch_to.window(new_handle)
                break
            time.sleep(0.1)
        else:

            driver.get(url)
            return (False, original)
    except Exception:
# popup blocked then stay on the same tab-This issue was also emailed to you but I tried this solution I found online
        driver.get(url)
        return (False, original)


    WebDriverWait(driver, EXPLICIT_WAIT).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    return (True, original)

def close_book_page(driver, is_new_tab: bool, return_handle: str):
    try:
        if is_new_tab and len(driver.window_handles) > 1:
            driver.close()
            driver.switch_to.window(return_handle)
        elif not is_new_tab:
            # navigating back to list if we used same tab
            try:
                driver.back()
            except Exception:

                try:
                    driver.switch_to.window(return_handle)
                except Exception:
                    pass
    except NoSuchWindowException:

        try:
            driver.switch_to.window(return_handle)
        except Exception:
            pass


def extract_book_details(driver) -> Dict[str, Any]:
    d = {
        "Title": "Not Available",
        "Author": "Not Available",
        "Rating": np.nan,
        "Number of Reviews": "Not Available",
        "Publication Date": "Not Available",
        "URL": driver.current_url,
    }

    if looks_like_captcha(driver):
        return d

    # Wait for an <h1>
    try:
        WebDriverWait(driver, EXPLICIT_WAIT).until(
            EC.presence_of_element_located((By.XPATH,
                "//h1 | //h1[@id='bookTitle'] | //h1[@data-testid='bookTitle']"))
        )
    except Exception:
        return d

    # Title
    for by, sel in [
        (By.CSS_SELECTOR, "h1#bookTitle"),
        (By.CSS_SELECTOR, "h1[data-testid='bookTitle']"),
        (By.XPATH, "//h1"),
    ]:
        try:
            t = safe_text(driver.find_element(by, sel))
            if t:
                d["Title"] = t
                break
        except Exception:
            pass

    # Author
    for by, sel in [
        (By.CSS_SELECTOR, "a.authorName span[itemprop='name']"),
        (By.CSS_SELECTOR, "span.ContributorLink__name"),
        (By.CSS_SELECTOR, "a[data-testid='name']"),
        (By.CSS_SELECTOR, "a.authorName"),
    ]:
        try:
            t = safe_text(driver.find_element(by, sel))
            if t:
                d["Author"] = t
                break
        except Exception:
            pass

    # Rating
    for by, sel in [
        (By.CSS_SELECTOR, "span[itemprop='ratingValue']"),
        (By.CSS_SELECTOR, "div.RatingStatistics__rating"),
        (By.CSS_SELECTOR, "[data-testid='ratingValue']"),
    ]:
        try:
            val = parse_float(safe_text(driver.find_element(by, sel)))
            if val is not None:
                d["Rating"] = val
                break
        except Exception:
            pass

    # Reviews
    got_reviews = False
    for by, sel in [
        (By.CSS_SELECTOR, "meta[itemprop='reviewCount']"),
        (By.CSS_SELECTOR, "[data-testid='reviewsCount']"),
        (By.XPATH, "//*[contains(translate(., 'REVIEWS', 'reviews'),'reviews')]"),
    ]:
        try:
            el = driver.find_element(by, sel)
            if el.tag_name.lower() == "meta":
                cnt = parse_int(el.get_attribute("content") or "")
            else:
                cnt = parse_int(safe_text(el))
            if cnt is not None:
                d["Number of Reviews"] = cnt
                got_reviews = True
                break
        except Exception:
            pass
    if not got_reviews:
        d["Number of Reviews"] = "Not Available"

    # Publication date
    for by, sel in [
        (By.CSS_SELECTOR, "#details .row"),
        (By.CSS_SELECTOR, "p[data-testid='publicationInfo']"),
        (By.XPATH, "//*[contains(., 'Published') and not(self::script) and not(self::style)]"),
    ]:
        try:
            els = driver.find_elements(by, sel)
            for el in els:
                txt = safe_text(el)
                if "publish" in txt.lower():
                    d["Publication Date"] = re.sub(r"\s+", " ", txt)
                    raise StopIteration
        except StopIteration:
            break
        except Exception:
            pass

    return d



def scrape_goodreads(genres: List[str], books_per_genre: int = 12) -> pd.DataFrame:
    driver = make_driver(HEADLESS)
    all_rows = []
    scraped_count = 0
    try:
        for genre in genres:
            print(f"[Genre] {genre} — opening list page…")
            open_genre_list(driver, genre)
            human_sleep()
            links = collect_book_links_from_list(driver, books_per_genre)
            print(f"  collected {len(links)} book links")

            for i, url in enumerate(links, 1):
                print(f"   → [{genre}] book {i}/{len(links)}")
                # try up to 2 attempts per book
                row = None
                for attempt in range(2):
                    try:
                        is_new, ret_handle = open_book_page(driver, url)
                        WebDriverWait(driver, EXPLICIT_WAIT).until(
                            EC.presence_of_element_located((By.TAG_NAME, "body"))
                        )
                        kill_overlays(driver)
                        human_sleep()
                        row = extract_book_details(driver)
                        close_book_page(driver, is_new, ret_handle)
                        break
                    except TimeoutException:
                        try:
                            driver.execute_script("window.stop();")
                        except Exception:
                            pass
                        if attempt == 0:
                            try:
                                driver.refresh()
                            except Exception:
                                pass
                            time.sleep(1.0)
                        else:
                            close_book_page(driver, is_new, ret_handle)
                    except NoSuchWindowException:

                        try:
                            driver.switch_to.window(ret_handle)
                        except Exception:
                            pass
                        try:
                            robust_get(driver, url)
                            row = extract_book_details(driver)
                            driver.back()
                        except Exception:
                            pass
                        break
                    except ElementClickInterceptedException:
                        kill_overlays(driver)
                        time.sleep(0.5)

                    except Exception as e:

                        if attempt == 0:
                            time.sleep(0.8)
                        else:
                            # give up on this book- aftr doing everything :(
                            try:
                                close_book_page(driver, True, ret_handle)
                            except Exception:
                                pass

                if row is None:
                    row = {
                        "Genre": genre, "Title": "Not Available", "Author": "Not Available",
                        "Rating": np.nan, "Number of Reviews": "Not Available",
                        "Publication Date": "Not Available", "URL": url
                    }
                else:
                    row["Genre"] = genre

                all_rows.append(row)
                scraped_count += 1

                # periodic partial save
                if scraped_count % PARTIAL_SAVE_EVERY == 0:
                    pd.DataFrame(all_rows).to_csv("goodreads_books_partial.csv", index=False)
                    print("   [partial save] goodreads_books_partial.csv")

                human_sleep()
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    df = pd.DataFrame(all_rows, columns=[
        "Genre", "Title", "Author", "Rating", "Number of Reviews", "Publication Date", "URL"
    ])

    # Normalize
    df["Title"] = df["Title"].replace("", "Not Available")
    df["Author"] = df["Author"].replace("", "Not Available")

    def norm_reviews(x):
        if isinstance(x, (int, np.integer)):
            return x
        if isinstance(x, str):
            xi = parse_int(x)
            return xi if xi is not None else "Not Available"
        return "Not Available"

    df["Number of Reviews"] = df["Number of Reviews"].apply(norm_reviews)
    return df


def analyze_by_genre(df: pd.DataFrame) -> pd.DataFrame:

    summary = (df.groupby("Genre", as_index=False)["Rating"]
                 .mean(skipna=True)  # all-NaN => NaN mean, but the row stays
                 .rename(columns={"Rating": "Average Rating"}))


    counts = (df.groupby("Genre")["Rating"]
                .apply(lambda s: s.notna().sum())
                .rename("Rated Books"))

    summary = summary.merge(counts, on="Genre", how="left")
    return summary.sort_values(["Average Rating"], ascending=[False], na_position="last")




if __name__ == "__main__":
    df_books = scrape_goodreads(GENRES, BOOKS_PER_GENRE)

    print("\n[DataFrame] First 10 rows:")
    print(df_books.head(10).to_string(index=False))

    out_csv = "goodreads_books.csv"
    df_books.to_csv(out_csv, index=False)
    print(f"\nSaved: {out_csv}")

    summary = analyze_by_genre(df_books)
    print("\n[Average Ratings by Genre]")
    print(summary.to_string(index=False))

    best = summary.dropna(subset=["Average Rating"])
    if not best.empty:
        top = best.iloc[0]
        print(f"\nHighest-rated genre: {top['Genre']} (avg {top['Average Rating']:.2f})")
    else:
        print("No comparable ratings yet. Try another run or different genres.")

