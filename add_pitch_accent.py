#!/usr/bin/env python3
"""Add pitch accent notation to compound entries in JLPT CSV files.

Uses the kanjium pitch accent database (accents_kanjium.txt).
Format added to compounds: word (reading·N) = meaning
where N is the accent kernel position (0 = heiban/flat).
"""

import csv
import re
import sys
from pathlib import Path

COMPOUND_RE = re.compile(r"^(.*?)\s*\(([^)]+)\)\s*=\s*(.*)$")


def load_accent_db(path):
    """Load kanjium accent database.

    Returns:
        db: dict (word, reading) -> accent_str
        word_only: dict word -> list of (reading, accent_str)
    """
    db = {}
    word_only = {}

    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 3:
                continue
            word, reading, accent = parts
            db[(word, reading)] = accent
            word_only.setdefault(word, []).append((reading, accent))

    return db, word_only


def lookup_accent(word, reading, db, word_only):
    """Return accent string for (word, reading) or None."""
    # Exact match
    key = (word, reading)
    if key in db:
        return db[key]

    # Word-only fallback
    entries = word_only.get(word)
    if not entries:
        return None
    if len(entries) == 1:
        return entries[0][1]
    # Multiple readings — prefer matching reading
    for r, a in entries:
        if r == reading:
            return a
    # Return first entry as last resort
    return entries[0][1]


def add_accent_to_compounds(compounds_str, db, word_only, stats):
    """Process a full compound cell; return updated string."""
    if not compounds_str or not compounds_str.strip():
        return compounds_str

    parts = compounds_str.split(";")
    result = []
    for part in parts:
        part_stripped = part.strip()
        m = COMPOUND_RE.match(part_stripped)
        if not m:
            result.append(part)
            continue

        word = m.group(1).strip()
        reading = m.group(2).strip()
        meaning = m.group(3).strip()

        # Skip if accent already added (contains ·)
        if "·" in reading:
            result.append(part)
            stats["skipped"] += 1
            continue

        stats["total"] += 1
        accent = lookup_accent(word, reading, db, word_only)
        if accent:
            stats["found"] += 1
            result.append(f"{word} ({reading}·{accent}) = {meaning}")
        else:
            stats["missing"] += 1
            result.append(part_stripped)

    return "; ".join(result)


def process_csv(csv_path, db, word_only):
    """Process one CSV file in-place."""
    print(f"Processing {csv_path.name} ...", end=" ", flush=True)

    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    stats = {"total": 0, "found": 0, "missing": 0, "skipped": 0}

    for row in rows:
        if row.get("compounds"):
            row["compounds"] = add_accent_to_compounds(
                row["compounds"], db, word_only, stats
            )

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    t = stats["total"]
    found = stats["found"]
    pct = f"{found / t * 100:.1f}%" if t else "n/a"
    print(
        f"{t} compounds — {found} matched ({pct}), "
        f"{stats['missing']} missing, {stats['skipped']} already done"
    )
    return stats


def main():
    db_path = Path("accents_kanjium.txt")
    if not db_path.exists():
        print("ERROR: accents_kanjium.txt not found. Run download step first.")
        sys.exit(1)

    print("Loading accent database ...", end=" ", flush=True)
    db, word_only = load_accent_db(db_path)
    print(f"{len(db):,} entries, {len(word_only):,} unique words")

    csv_files = sorted(Path(".").glob("kanji_n*.csv"))
    if not csv_files:
        print("No kanji_n*.csv files found in current directory.")
        sys.exit(1)

    totals = {"total": 0, "found": 0, "missing": 0, "skipped": 0}
    for csv_file in csv_files:
        s = process_csv(csv_file, db, word_only)
        for k in totals:
            totals[k] += s[k]

    t = totals["total"]
    found = totals["found"]
    pct = f"{found / t * 100:.1f}%" if t else "n/a"
    print(
        f"\nTotal: {t} compounds — {found} with accent ({pct}), "
        f"{totals['missing']} missing"
    )


if __name__ == "__main__":
    main()
