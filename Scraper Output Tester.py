"""
Quality-control checks for a scraped bukhari_full.json produced by
scrape_bukhari.py. Run this after the scrape finishes and read through
the report before trusting the data.

Usage:
    python3 validate_bukhari.py bukhari_full.json
"""

import json
import sys
import re
from collections import Counter

EXPECTED_BOOK_COUNT = 97

HADITH_FIELDS = [
    "Reference", "Isnad_Arabic", "Matn_Arabic", "Rest_Arabic",
    "Narrator_English", "Matn_English", "Other_References",
]
CHAPTER_FIELDS = [
    "Chapter_Number", "Chapter_Name_Arabic", "Chapter_Name_English",
    "Chapter_Intro_Arabic", "Chapter_Intro_English",
]


def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def has_mojibake(text):
    # crude check: replacement char, or common UTF-8-read-as-Latin1 garbage
    return "�" in text or bool(re.search(r"Ã.|â€", text))


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "bukhari_full.json"
    data = load(path)
    books = data.get("Books", [])

    print(f"=== Structural summary ===")
    print(f"Books found: {len(books)} (expected {EXPECTED_BOOK_COUNT})")

    all_hadiths = []          # (book_num, chapter_num, hadith_dict)
    all_references = []       # int references (digit-only, for gap analysis)
    all_reference_strings = []  # exact Reference text (for duplicate detection)
    empty_field_counts = Counter()
    placeholder_only_count = 0  # combined-pair placeholders, e.g. "521" in "521, 522"
    mojibake_examples = []
    missing_book_numbers = []

    seen_book_numbers = set()

    for book in books:
        bn = book.get("Book_Number", "?")
        seen_book_numbers.add(str(bn))

        chapters = book.get("Chapters", [])
        if not chapters:
            print(f"  WARNING: Book {bn} has 0 chapters.")

        prev_chapter_num = None
        for chapter in chapters:
            cn = chapter.get("Chapter_Number", "?")

            # chapter number monotonic check (informational only — Bukhari
            # numbering can legitimately have gaps in some editions)
            try:
                cn_int = int(cn)
                if prev_chapter_num is not None and cn_int < prev_chapter_num:
                    print(f"  WARNING: Book {bn} chapter numbers out of order "
                          f"({prev_chapter_num} -> {cn_int}).")
                prev_chapter_num = cn_int
            except ValueError:
                pass

            for field in CHAPTER_FIELDS:
                if not chapter.get(field, "").strip():
                    empty_field_counts[f"Chapter.{field}"] += 1

            hadiths = chapter.get("Hadith_List", [])
            if not hadiths:
                print(f"  WARNING: Book {bn} Chapter {cn} has 0 hadiths.")

            for hadith in hadiths:
                all_hadiths.append((bn, cn, hadith))

                ref = hadith.get("Reference", "")
                ref_numbers = re.findall(r"\d+", ref)
                if ref_numbers:
                    all_references.extend(int(n) for n in ref_numbers)
                else:
                    print(f"  WARNING: No digits found in Reference '{ref}' in "
                          f"Book {bn} Chapter {cn}.")
                all_reference_strings.append(ref)

                for field in HADITH_FIELDS:
                    val = hadith.get(field, "")
                    if not val.strip():
                        empty_field_counts[f"Hadith.{field}"] += 1
                    elif has_mojibake(val) and len(mojibake_examples) < 10:
                        mojibake_examples.append((bn, cn, ref, field, val[:60]))

                # a hadith with zero Arabic content is only suspicious if it
                # also has no English content — a hadith with English fields
                # filled but no Arabic is a real gap. A hadith with literally
                # everything blank except Reference is an expected
                # combined-pair placeholder (e.g. the "521" in "521, 522"),
                # not a parsing failure — count it separately instead of
                # warning on every single one.
                no_arabic = not (
                    hadith.get("Isnad_Arabic", "").strip()
                    or hadith.get("Matn_Arabic", "").strip()
                    or hadith.get("Rest_Arabic", "").strip()
                )
                if no_arabic:
                    has_other_content = (
                        hadith.get("Narrator_English", "").strip()
                        or hadith.get("Matn_English", "").strip()
                        or hadith.get("Other_References", "").strip()
                    )
                    if has_other_content:
                        print(f"  WARNING: Book {bn} Hadith {ref} has English "
                              f"content but NO Arabic at all — likely a real "
                              f"parsing gap, not a combined-pair placeholder.")
                    else:
                        placeholder_only_count += 1

        # cross-check stated First/Last hadith numbers against what was
        # actually parsed for this book
        book_refs = []
        for chapter in chapters:
            for hadith in chapter.get("Hadith_List", []):
                book_refs.extend(int(n) for n in re.findall(r"\d+", hadith.get("Reference", "")))
        if book_refs:
            actual_first, actual_last = min(book_refs), max(book_refs)
            stated_first = book.get("First_Hadith_Number", "")
            stated_last = book.get("Last_Hadith_Number", "")
            try:
                if int(stated_first) != actual_first:
                    print(f"  WARNING: Book {bn} stated First_Hadith_Number="
                          f"{stated_first} but parsed hadiths start at {actual_first}.")
                if int(stated_last) != actual_last:
                    print(f"  WARNING: Book {bn} stated Last_Hadith_Number="
                          f"{stated_last} but parsed hadiths end at {actual_last}.")
            except ValueError:
                pass

    for i in range(1, EXPECTED_BOOK_COUNT + 1):
        if str(i) not in seen_book_numbers:
            missing_book_numbers.append(i)

    print(f"\nMissing book numbers: {missing_book_numbers or 'none'}")
    print(f"Total chapters: {sum(len(b.get('Chapters', [])) for b in books)}")
    print(f"Total hadiths: {len(all_hadiths)}")
    print(f"Combined-pair placeholders (expected, empty by design): {placeholder_only_count}")

    print(f"\n=== Reference number checks ===")
    dupes = [ref for ref, count in Counter(all_reference_strings).items() if count > 1]
    print(f"Duplicate Reference values (exact string match): {dupes if dupes else 'none'}")
    print("  Note: hadiths like '402' and '402b' are DIFFERENT, legitimate "
          "entries — this check only flags an exact repeated string.")

    if all_references:
        sorted_refs = sorted(set(all_references))
        expected_range = set(range(sorted_refs[0], sorted_refs[-1] + 1))
        gaps = sorted(expected_range - set(sorted_refs))
        print(f"Reference range: {sorted_refs[0]} to {sorted_refs[-1]}")
        print(f"Missing numbers within that range ({len(gaps)} total): "
              f"{gaps[:30]}{' ...' if len(gaps) > 30 else ''}")
        print("  Note: Bukhari's own numbering has a few known gaps "
              "(e.g. hadith 1066 doesn't exist), so some gaps here are "
              "expected — not necessarily scraping errors. Worth spot-"
              "checking a few against sunnah.com directly.")

    print(f"\n=== Empty field report (count of blank values) ===")
    for field, count in empty_field_counts.most_common():
        print(f"  {field}: {count}")

    if mojibake_examples:
        print(f"\n=== Possible encoding issues (showing up to 10) ===")
        for bn, cn, ref, field, snippet in mojibake_examples:
            print(f"  Book {bn} Chapter {cn} Hadith {ref} [{field}]: {snippet!r}")
    else:
        print(f"\nNo obvious encoding/mojibake issues detected.")

    print(f"\n=== Spot-check sample (first hadith of book 1) ===")
    if books and books[0].get("Chapters") and books[0]["Chapters"][0].get("Hadith_List"):
        print(json.dumps(books[0]["Chapters"][0]["Hadith_List"][0], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()