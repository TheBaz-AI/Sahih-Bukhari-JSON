"""
Scrape the entire Sahih al-Bukhari collection from sunnah.com and save it
as a single JSON file (same folder as this script), matching the schema:

{
    "Books": [
        {
            "Book_Name_Arabic": "...",
            "Book_Name_English": "...",
            "Book_Number": "1",
            "First_Hadith_Number": "1",
            "Last_Hadith_Number": "7",
            "Chapters": [ ... ]
        },
        ...
    ]
}

Usage:
    python3 scrape_bukhari.py

Requires:
    pip install requests beautifulsoup4
"""

import requests
from bs4 import BeautifulSoup
import json
import re
import time
import sys
import socket
import urllib3.util.connection as urllib3_cn

# --- Force IPv4-only DNS resolution ---------------------------------------
# On some systems (notably macOS), Python's `requests`/urllib3 doesn't do
# "happy eyeballs" like browsers do: if getaddrinfo() returns an IPv6
# address first and that route is slow/blocked, the connection attempt
# hangs for the full OS-level TCP timeout (commonly ~60-90s) before
# falling back to IPv4. Forcing IPv4-only resolution skips that entirely.
def _allowed_gai_family():
    return socket.AF_INET

urllib3_cn.allowed_gai_family = _allowed_gai_family
# ---------------------------------------------------------------------------

INDEX_URL = "https://sunnah.com/bukhari"
BOOK_URL = "https://sunnah.com/bukhari/{}"
OUTPUT_FILE = "bukhari_full.json"

# Be polite to sunnah.com's servers between requests.
REQUEST_DELAY_SECONDS = 1.5

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

# Elements we care about per hadith/chapter, in the order they appear on the page.
TARGET_CLASSES = [
    "echapno",
    "englishchapter",
    "arabicchapter",
    "echapintro",
    "achapintro",
    "hadith_reference_sticky",
    "hadith_narrated",
    "text_details",
    "arabic_sanad",
    "arabic_text_details",
]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def fetch_html(url):
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def clean_text(el):
    """Get readable text from an element, collapsing whitespace."""
    if el is None:
        return ""
    text = el.get_text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def extract_reference_number(ref_text):
    """
    'Sahih al-Bukhari 334' -> '334'
    'Sahih al-Bukhari 402b' -> '402b'          (lettered sub-numbering)
    'Sahih al-Bukhari 521, 522' -> '521, 522'  (one entry covering two numbers)
    Falls back to the raw text if the expected prefix isn't found.
    """
    match = re.search(r"Sahih al-Bukhari\s+(.+)$", ref_text)
    return match.group(1).strip() if match else ref_text.strip()


def expand_reference_numbers(ref):
    """
    Expand a Reference string into an ordered list of individual hadith
    identifiers. Handles both formats seen on the site:
      '522'          -> ['522']
      '402b'         -> ['402b']
      '521, 522'     -> ['521', '522']
      '5709-5712'    -> ['5709', '5710', '5711', '5712']
    """
    numbers = []
    for part in ref.split(","):
        part = part.strip()
        range_match = re.fullmatch(r"(\d+)-(\d+)", part)
        if range_match:
            start, end = int(range_match.group(1)), int(range_match.group(2))
            numbers.extend(str(n) for n in range(start, end + 1))
        else:
            numbers.append(part)
    return numbers


def extract_chapter_number(chap_text):
    """'(1)' -> '1'. Falls back to raw text if no digits found."""
    match = re.search(r"\d+", chap_text)
    return match.group(0) if match else chap_text.strip()


def extract_other_references(container):
    """
    Given a hadith's .actualHadithContainer element, find the
    'In-book reference' and 'USC-MSA web (English) reference' rows
    by matching on their label text (not their CSS class, which
    varies/overlaps between rows) and return them combined as one
    string, e.g.:
    "In-book reference: Book 1, Hadith 1; USC-MSA web (English) reference: Vol. 1, Book 1, Hadith 1"
    """
    wanted_labels = ["In-book reference", "USC-MSA web (English) reference"]
    parts = []

    for row in container.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        label = clean_text(cells[0])
        if label in wanted_labels:
            value = clean_text(cells[1])
            value = re.sub(r"^:\s*", "", value)  # strip leading ": "
            parts.append(f"{label}: {value}")

    return "; ".join(parts)


# ---------------------------------------------------------------------------
# Index page (book list) parsing
# ---------------------------------------------------------------------------

def parse_book_range(range_el):
    """
    <div class="book_range"><div>1</div><div> to </div><div>7</div></div>
    -> ("1", "7")
    Takes the first and last child divs, ignoring whatever's between them
    (normally just the " to " separator).
    """
    if range_el is None:
        return "", ""
    divs = range_el.find_all("div")
    if len(divs) < 2:
        return "", ""
    first = clean_text(divs[0])
    last = clean_text(divs[-1])
    return first, last


def parse_book_index(html):
    """
    Parse https://sunnah.com/bukhari and return a list of book metadata
    dicts (without Chapters yet), in book-number order.
    """
    soup = BeautifulSoup(html, "html.parser")

    numbers = soup.find_all(class_="book_number")
    english_names = soup.find_all(class_="english_book_name")
    arabic_names = soup.find_all(class_="arabic_book_name")
    ranges = soup.find_all(class_="book_range")

    counts = {
        "book_number": len(numbers),
        "english_book_name": len(english_names),
        "arabic_book_name": len(arabic_names),
        "book_range": len(ranges),
    }
    if len(set(counts.values())) != 1:
        print(f"Warning: mismatched element counts on index page: {counts}")

    books = []
    for i in range(len(numbers)):
        first_hadith, last_hadith = parse_book_range(ranges[i]) if i < len(ranges) else ("", "")
        books.append({
            "Book_Number": clean_text(numbers[i]),
            "Book_Name_English": clean_text(english_names[i]) if i < len(english_names) else "",
            "Book_Name_Arabic": clean_text(arabic_names[i]) if i < len(arabic_names) else "",
            "First_Hadith_Number": first_hadith,
            "Last_Hadith_Number": last_hadith,
        })

    return books


# ---------------------------------------------------------------------------
# Per-book page (chapters/hadiths) parsing
# ---------------------------------------------------------------------------

def parse_chapters(html):
    soup = BeautifulSoup(html, "html.parser")
    elements = soup.find_all(class_=TARGET_CLASSES)

    chapters = []
    current_chapter = {
        "Chapter_Number": "",
        "Chapter_Name_Arabic": "",
        "Chapter_Name_English": "",
        "Chapter_Intro_Arabic": "",
        "Chapter_Intro_English": "",
        "Hadith_List": [],
    }  # catches any hadith that appears before the page's first .echapno
    current_hadith = None
    sanad_count = 0

    def close_hadith():
        nonlocal current_hadith
        if current_hadith is not None and current_chapter is not None:
            ref = current_hadith.get("Reference", "")
            # Some hadiths are displayed as a combined entry — either a
            # comma pair ("521, 522") or a dash range ("5709-5712") —
            # covering multiple official numbers with only the last one
            # carrying real content. Split these so no number disappears.
            numbers = expand_reference_numbers(ref)

            if len(numbers) > 1:
                for num in numbers[:-1]:
                    placeholder = {key: "" for key in current_hadith.keys()}
                    placeholder["Reference"] = num
                    placeholder["_is_placeholder"] = True  # no matching .actualHadithContainer
                    current_chapter["Hadith_List"].append(placeholder)
                current_hadith["Reference"] = numbers[-1]

            current_chapter["Hadith_List"].append(current_hadith)
        current_hadith = None

    def close_chapter():
        nonlocal current_chapter
        close_hadith()
        if current_chapter is not None:
            has_content = (
                current_chapter["Hadith_List"]
                or current_chapter["Chapter_Number"]
                or current_chapter["Chapter_Name_English"]
                or current_chapter["Chapter_Name_Arabic"]
            )
            # Skip appending the initial placeholder chapter when nothing
            # ever landed in it (the normal case — most books start
            # cleanly with a real .echapno).
            if has_content:
                chapters.append(current_chapter)
        current_chapter = None

    for el in elements:
        classes = el.get("class", [])
        matched = next((c for c in TARGET_CLASSES if c in classes), None)
        if matched is None:
            continue

        if matched == "echapno":
            close_chapter()
            current_chapter = {
                "Chapter_Number": extract_chapter_number(clean_text(el)),
                "Chapter_Name_Arabic": "",
                "Chapter_Name_English": "",
                "Chapter_Intro_Arabic": "",
                "Chapter_Intro_English": "",
                "Hadith_List": [],
            }
            continue

        if current_chapter is None:
            continue  # stray content before the first chapter marker

        if matched == "englishchapter":
            current_chapter["Chapter_Name_English"] = clean_text(el)
        elif matched == "arabicchapter":
            current_chapter["Chapter_Name_Arabic"] = clean_text(el)
        elif matched == "echapintro":
            current_chapter["Chapter_Intro_English"] = clean_text(el)
        elif matched == "achapintro":
            current_chapter["Chapter_Intro_Arabic"] = clean_text(el)
        elif matched == "hadith_reference_sticky":
            close_hadith()
            current_hadith = {
                "Reference": extract_reference_number(clean_text(el)),
                "Isnad_Arabic": "",
                "Matn_Arabic": "",
                "Rest_Arabic": "",
                "Narrator_English": "",
                "Matn_English": "",
                "Other_References": "",
            }
            sanad_count = 0
        elif matched == "hadith_narrated":
            if current_hadith is not None:
                current_hadith["Narrator_English"] = clean_text(el)
        elif matched == "text_details":
            if current_hadith is not None:
                current_hadith["Matn_English"] = clean_text(el)
        elif matched == "arabic_sanad":
            if current_hadith is not None:
                sanad_count += 1
                if sanad_count == 1:
                    current_hadith["Isnad_Arabic"] = clean_text(el)
                elif sanad_count == 2:
                    current_hadith["Rest_Arabic"] = clean_text(el)
        elif matched == "arabic_text_details":
            if current_hadith is not None:
                current_hadith["Matn_Arabic"] = clean_text(el)

    close_chapter()

    # Second pass: fill Other_References by scanning each hadith's
    # .actualHadithContainer wrapper and aligning by position. Placeholder
    # hadiths (from split combined-reference entries, e.g. "521, 522") have
    # no container of their own, so they're excluded from this alignment.
    containers = soup.find_all(class_="actualHadithContainer")
    flat_hadiths = [h for chapter in chapters for h in chapter["Hadith_List"]]
    real_hadiths = [h for h in flat_hadiths if not h.pop("_is_placeholder", False)]

    if len(containers) != len(real_hadiths):
        print(
            f"Warning: found {len(containers)} .actualHadithContainer "
            f"blocks but parsed {len(real_hadiths)} content-bearing hadiths — "
            "Other_References may be misaligned or incomplete for this book."
        )

    for hadith, container in zip(real_hadiths, containers):
        hadith["Other_References"] = extract_other_references(container)

    return chapters


# ---------------------------------------------------------------------------
# Main scrape
# ---------------------------------------------------------------------------

def scrape_full_bukhari():
    print(f"Fetching book index: {INDEX_URL}")
    index_html = fetch_html(INDEX_URL)
    book_metadata = parse_book_index(index_html)
    print(f"Found {len(book_metadata)} books on the index page.")

    books = []
    for meta in book_metadata:
        book_number = meta["Book_Number"]
        url = BOOK_URL.format(book_number)
        print(f"Scraping book {book_number}: {meta['Book_Name_English']} ({url})")

        try:
            t0 = time.time()
            html = fetch_html(url)
            t1 = time.time()
            chapters = parse_chapters(html)
            t2 = time.time()
            print(f"  fetch: {t1 - t0:.2f}s | parse: {t2 - t1:.2f}s | "
                  f"page size: {len(html) / 1024:.0f} KB")
        except Exception as exc:
            print(f"  ERROR scraping book {book_number}: {exc} — skipping.")
            time.sleep(REQUEST_DELAY_SECONDS)
            continue

        book_entry = {
            "Book_Name_Arabic": meta["Book_Name_Arabic"],
            "Book_Name_English": meta["Book_Name_English"],
            "Book_Number": book_number,
            "First_Hadith_Number": meta["First_Hadith_Number"],
            "Last_Hadith_Number": meta["Last_Hadith_Number"],
            "Chapters": chapters,
        }
        books.append(book_entry)

        time.sleep(REQUEST_DELAY_SECONDS)

    return {"Books": books}


def main():
    data = scrape_full_bukhari()

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    total_chapters = sum(len(b["Chapters"]) for b in data["Books"])
    total_hadiths = sum(len(c["Hadith_List"]) for b in data["Books"] for c in b["Chapters"])
    print(f"\nDone. Saved {len(data['Books'])} books, {total_chapters} chapters, "
          f"{total_hadiths} hadiths to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()