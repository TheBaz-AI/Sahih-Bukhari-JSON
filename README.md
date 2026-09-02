# Sahih al-Bukhari — Structured JSON Dataset

A complete, structured JSON export of **Sahih al-Bukhari** (English translation by Dr. Muhammad Muhsin Khan, with original Arabic text), covering all 97 books, ~4,096 chapters, and all 7,563 hadith reference numbers.

## Source

Scraped from [sunnah.com](https://sunnah.com/bukhari) — specifically:
- The book index at `https://sunnah.com/bukhari` (book titles, numbers, and stated hadith ranges)
- Each individual book page at `https://sunnah.com/bukhari/<book_number>` (1 through 97)

This is a derivative of sunnah.com's own presentation of the Khan translation. All credit for the underlying text belongs to sunnah.com and the original translator; this repo just restructures their HTML into clean, queryable JSON. If you plan to redistribute or build a product on this data, check sunnah.com's terms first.

## File structure

```json
{
    "Books": [
        {
            "Book_Name_Arabic": "كتاب بدء الوحى",
            "Book_Name_English": "Revelation",
            "Book_Number": "1",
            "First_Hadith_Number": "1",
            "Last_Hadith_Number": "7",
            "Chapters": [
                {
                    "Chapter_Number": "1",
                    "Chapter_Name_Arabic": "باب كَيْفَ كَانَ بَدْءُ الْوَحْىِ...",
                    "Chapter_Name_English": "Chapter: How the Divine Revelation started...",
                    "Chapter_Intro_Arabic": "",
                    "Chapter_Intro_English": "",
                    "Hadith_List": [
                        {
                            "Reference": "1",
                            "Isnad_Arabic": "حَدَّثَنَا الْحُمَيْدِيُّ...",
                            "Matn_Arabic": "إِنَّمَا الأَعْمَالُ بِالنِّيَّاتِ...",
                            "Rest_Arabic": "",
                            "Narrator_English": "Narrated 'Umar bin Al-Khattab:",
                            "Matn_English": "I heard Allah's Messenger (ﷺ) saying...",
                            "Other_References": "In-book reference: Book 1, Hadith 1; USC-MSA web (English) reference: Vol. 1, Book 1, Hadith 1"
                        }
                    ]
                }
            ]
        }
    ]
}
```

## Field reference

### Book level
| Field | Description |
|---|---|
| `Book_Name_Arabic` / `Book_Name_English` | The book's title, e.g. "Revelation" |
| `Book_Number` | 1–97 |
| `First_Hadith_Number` / `Last_Hadith_Number` | The hadith range as *stated on sunnah.com's index page*. In a handful of books this is off by one from the true last hadith in `Chapters` — see **Known quirks** below. |
| `Chapters` | Array of chapter objects, in page order |

### Chapter level
| Field | Description |
|---|---|
| `Chapter_Number` | As shown on the page, digits only (parenthesized "(12)" style is stripped) |
| `Chapter_Name_Arabic` / `Chapter_Name_English` | Chapter/bāb title |
| `Chapter_Intro_Arabic` / `Chapter_Intro_English` | Optional commentary text between the chapter title and the first hadith. Empty for most chapters — that's normal, not missing data. |
| `Hadith_List` | Array of hadith objects in this chapter |

### Hadith level
| Field | Description |
|---|---|
| `Reference` | The hadith number as sunnah.com displays it — usually a plain integer, but see **Known quirks** for lettered (`402b`) and multi-number entries |
| `Isnad_Arabic` | The chain of narration (sanad), Arabic |
| `Matn_Arabic` | The hadith text (matn), Arabic |
| `Rest_Arabic` | A second sanad, when a hadith cites more than one chain (rare) |
| `Narrator_English` | The "Narrated X:" line |
| `Matn_English` | The English translation of the hadith text |
| `Other_References` | Combines the page's "In-book reference" and "USC-MSA web (English) reference" lines into one string |

## Known quirks (read before filing a bug)

**1. Combined/merged hadith entries.** Some hadiths on sunnah.com share a single page entry across two or more official numbers, in two formats:
- Comma pairs: `Sahih al-Bukhari 521, 522`
- Dash ranges: `Sahih al-Bukhari 5709-5712`

In these cases, only the *last* number in the group has real content — the earlier numbers had no independent text of their own on the original page. This dataset represents that faithfully: each earlier number gets its own hadith object with `Reference` filled in and every other field empty, and the final number carries the actual text. If you're iterating over hadiths and expect every record to have content, filter out records where all content fields are empty — these are legitimate placeholders, not scraping failures.

**2. Lettered reference numbers.** Some hadiths are numbered like `402b` — a secondary narration of the same event as `402`, with its own distinct chain but referencing the same matn. These appear as their own separate hadith objects with `Reference: "402b"`.

**3. Chapters with zero hadiths.** Many chapter headings in Bukhari exist purely to state a ruling or theme (sometimes derived from a Qur'an verse quoted in the chapter itself) without a hadith directly underneath. An empty `Hadith_List` in these cases is expected, not a parsing gap.

**4. Book 65 (Tafsir) chapter numbering.** This book is organized by Qur'anic Sūrah, and chapter numbers restart from 1 for each new Sūrah section. If you're using `Chapter_Number` as a global sort key, this book will look "out of order" — that's the source material's own structure, not a bug.

**5. `First_Hadith_Number` / `Last_Hadith_Number` occasionally off by one.** In a few books (16, 25, 37, 42, 48, 86), sunnah.com's own index page states a range that's one short of the true last hadith — this happens specifically when the last hadith is a combined pair (see quirk #1) and the index widget only counted the first number. The `Chapters` data itself is complete and correct; only these two summary fields inherit the site's own minor inconsistency.

**6. Book 96 has an extra empty chapter entry** (`Chapter_Number: "0"`, no hadiths). Cosmetic only — no hadith content is lost.

## Data quality

This dataset was scraped, then validated against:
- All 7,563 official hadith reference numbers present, zero gaps, zero unexpected duplicates
- All 97 books, 4,096 chapters accounted for
- No encoding/mojibake issues detected in Arabic or English text

A validation script (see `validate_bukhari.py` in the scraper repo) is available if you want to re-run these checks yourself after any re-scrape.

## Usage

Load it like any JSON file:

```python
import json

with open("bukhari_full.json", encoding="utf-8") as f:
    data = json.load(f)

for book in data["Books"]:
    for chapter in book["Chapters"]:
        for hadith in chapter["Hadith_List"]:
            if hadith["Matn_English"]:  # skip combined-entry placeholders
                print(hadith["Reference"], hadith["Narrator_English"])
```

```javascript
const data = require("./bukhari_full.json");

for (const book of data.Books) {
  for (const chapter of book.Chapters) {
    for (const hadith of chapter.Hadith_List) {
      if (hadith.Matn_English) {
        console.log(hadith.Reference, hadith.Narrator_English);
      }
    }
  }
}
```

## Regenerating this dataset

The scraper (`main.py`) and validator (`validate_bukhari.py`) used to produce this file are included in this repo. Requirements: Python 3, `requests`, `beautifulsoup4`.

```bash
pip install requests beautifulsoup4
python3 main.py           # scrapes all 97 books, writes bukhari_full.json
python3 validate_bukhari.py bukhari_full.json   # runs the QC checks above
```

## License / attribution

The hadith text (Arabic and English) originates from sunnah.com and the Khan translation of Sahih al-Bukhari. This repository only contains scraping/parsing code and a structured re-presentation of that publicly available text — no license is claimed over the hadith content itself.
