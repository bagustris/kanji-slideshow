#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kanji CSV Enrichment Script  (no API key required)
Adds new columns to kanji CSV files:
  sentence     : example Japanese sentence from Tatoeba
  kana         : hiragana reading of the sentence
  translation  : English translation of the sentence
  radicals     : component radicals from KRADFILE
  confusables  : visually similar kanji (computed from shared radicals)

Usage:
    python enrich_kanji_csv.py kanji_n5.csv
    python enrich_kanji_csv.py                   # all N1-N5 CSVs
    python enrich_kanji_csv.py --only radicals
    python enrich_kanji_csv.py --only sentences
    python enrich_kanji_csv.py --only confusables

Optional: if you have a Gemini free API key (https://aistudio.google.com):
    pip install google-generativeai
    export GEMINI_API_KEY="..."
    python enrich_kanji_csv.py --llm gemini
"""

import argparse
import csv
import json
import logging
import os
import sys
import time
import urllib.parse
import urllib.request
from typing import Dict, List, Optional, Tuple

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

KRADFILE_URL = "https://www.edrdg.org/pub/Nihongo/kradfile.gz"
KRADFILE_PATH = "kradfile"
KRADFILE_GZ_PATH = "kradfile.gz"
TANAKA_URL = "https://www.edrdg.org/pub/Nihongo/examples.utf.gz"
TANAKA_GZ_PATH = "examples.utf.gz"
TANAKA_PATH = "examples.utf"
MAX_SENTENCE_LEN = 30  # max Japanese chars in an example sentence

JLPT_FILES = [
    ("kanji_n5.csv", "N5"),
    ("kanji_n4.csv", "N4"),
    ("kanji_n3.csv", "N3"),
    ("kanji_n2.csv", "N2"),
    ("kanji_n1.csv", "N1"),
]

# ---------------------------------------------------------------------------
# KRADFILE
# ---------------------------------------------------------------------------


def download_kradfile():
    if os.path.exists(KRADFILE_PATH):
        return
    print("Downloading KRADFILE...")
    try:
        urllib.request.urlretrieve(KRADFILE_URL, KRADFILE_GZ_PATH)
        import gzip

        with gzip.open(KRADFILE_GZ_PATH, "rb") as gz_in:
            with open(KRADFILE_PATH, "wb") as f_out:
                f_out.write(gz_in.read())
        os.remove(KRADFILE_GZ_PATH)
        print("KRADFILE ready ({} bytes).".format(os.path.getsize(KRADFILE_PATH)))
    except Exception as e:
        print("Warning: Could not download KRADFILE: {}".format(e))


def load_kradfile():
    decomp = {}
    if not os.path.exists(KRADFILE_PATH):
        return decomp
    try:
        with open(KRADFILE_PATH, encoding="euc-jp", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or " : " not in line:
                    continue
                kanji, _, radicals = line.partition(" : ")
                kanji = kanji.strip()
                rads = [r for r in radicals.strip().split() if r and r != kanji]
                if kanji and rads:
                    decomp[kanji] = rads
    except Exception as e:
        print("Warning: Error reading KRADFILE: {}".format(e))
    return decomp


# ---------------------------------------------------------------------------
# Confusables: Jaccard similarity on radical sets
# ---------------------------------------------------------------------------


def build_confusables(kradfile, all_kanji):
    """
    For each kanji in all_kanji, find the top-3 most similar kanji
    based on Jaccard similarity of their radical sets.
    Only compares against kanji in all_kanji (JLPT corpus).
    """
    result = {}
    kanji_list = [k for k in all_kanji if k in kradfile]

    for kanji in kanji_list:
        rads_a = set(kradfile[kanji])
        if not rads_a:
            result[kanji] = ""
            continue

        scores = []
        for other in kanji_list:
            if other == kanji:
                continue
            rads_b = set(kradfile.get(other, []))
            if not rads_b:
                continue
            intersection = len(rads_a & rads_b)
            union = len(rads_a | rads_b)
            jaccard = intersection / union if union else 0
            # Boost score if they share most radicals relative to the smaller set
            overlap = (
                intersection / min(len(rads_a), len(rads_b))
                if min(len(rads_a), len(rads_b))
                else 0
            )
            combined = (jaccard + overlap) / 2
            if combined > 0:
                scores.append((combined, other))

        scores.sort(reverse=True)
        top = [k for _, k in scores[:3]]
        result[kanji] = ",".join(top)

    return result


# ---------------------------------------------------------------------------
# Tanaka Corpus: offline sentence lookup (no rate limits)
# ---------------------------------------------------------------------------


def download_tanaka():
    """Download and extract the Tanaka Corpus (examples.utf.gz) if not present."""
    if os.path.exists(TANAKA_PATH):
        return True
    print("Downloading Tanaka Corpus (~8 MB)...")
    try:
        urllib.request.urlretrieve(TANAKA_URL, TANAKA_GZ_PATH)
        import gzip

        with gzip.open(TANAKA_GZ_PATH, "rb") as gz_in:
            with open(TANAKA_PATH, "wb") as f_out:
                f_out.write(gz_in.read())
        os.remove(TANAKA_GZ_PATH)
        print(
            "Tanaka Corpus ready ({:.1f} MB).".format(
                os.path.getsize(TANAKA_PATH) / 1e6
            )
        )
        return True
    except Exception as e:
        print("Warning: Could not download Tanaka Corpus: {}".format(e))
        return False


def load_tanaka():
    """
    Parse examples.utf into a list of (jp, en) pairs.
    Format: alternating A-lines (Japanese) and B-lines (English).
      A: 日本語の文。 Nihongo no bun.
      B: English sentence.#ID=...
    """
    pairs = []
    if not os.path.exists(TANAKA_PATH):
        return pairs
    try:
        with open(TANAKA_PATH, encoding="utf-8", errors="ignore") as f:
            jp = ""
            for line in f:
                line = line.rstrip("\n")
                if line.startswith("A: "):
                    # Japanese text is between "A: " and the first tab/space before romaji
                    body = line[3:]
                    jp = body.split("\t")[0].strip()
                elif line.startswith("B: ") and jp:
                    en = line[3:].split("#ID=")[0].strip()
                    if jp and en:
                        pairs.append((jp, en))
                    jp = ""
        print("Loaded {:,} sentence pairs from Tanaka Corpus.".format(len(pairs)))
    except Exception as e:
        print("Warning: Error reading Tanaka Corpus: {}".format(e))
    return pairs


def build_sentence_index(pairs):
    """
    Build a dict: kanji_char -> list of (jp, en) sorted by sentence length.
    Only indexes CJK characters present in sentences.
    """
    import collections, re

    def _clean_en(text):
        """Strip Tanaka markup: {alt}, [num], ~ from English gloss."""
        text = re.sub(r"\{[^}]*\}", "", text)  # remove {alternate}
        text = re.sub(r"\[\d+\]", "", text)  # remove [01] sense numbers
        text = re.sub(r"~", "", text)  # remove conjugation markers
        return " ".join(text.split())  # normalise whitespace

    index = collections.defaultdict(list)
    for jp, en in pairs:
        en_clean = _clean_en(en)
        seen = set()
        for ch in jp:
            if "\u4e00" <= ch <= "\u9fff" and ch not in seen:
                index[ch].append((len(jp), jp, en_clean))
                seen.add(ch)
    # Sort each list by sentence length ascending
    for ch in index:
        index[ch].sort()
    return index


def lookup_sentence(index, kanji):
    """Return the shortest sentence containing kanji within MAX_SENTENCE_LEN."""
    candidates = index.get(kanji, [])
    for length, jp, en in candidates:
        if length <= MAX_SENTENCE_LEN:
            return jp, en
    # Relax limit if nothing short enough
    if candidates:
        _, jp, en = candidates[0]
        return jp, en
    return "", ""


# ---------------------------------------------------------------------------
# Optional: Gemini LLM (if key is set)
# ---------------------------------------------------------------------------


def make_gemini_client():
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    try:
        import google.generativeai as genai

        genai.configure(api_key=key)
        return genai.GenerativeModel("gemini-1.5-flash")
    except ImportError:
        print(
            "Warning: google-generativeai not installed. pip install google-generativeai"
        )
        return None


def gemini_sentence(model, kanji, meaning, level):
    prompt = (
        "Create ONE simple Japanese example sentence for the kanji {} ({}) "
        "appropriate for JLPT {} learners.\n"
        "Rules: sentence must contain {}, under 20 characters, everyday vocabulary.\n"
        "Reply in EXACTLY this format:\n"
        "JP: <sentence>\nKANA: <full hiragana reading>\nEN: <English translation>"
    ).format(kanji, meaning, level, kanji)
    try:
        resp = model.generate_content(prompt)
        text = resp.text.strip()
        result = {"sentence": "", "kana": "", "translation": ""}
        for line in text.splitlines():
            if line.startswith("JP:"):
                result["sentence"] = line[3:].strip()
            elif line.startswith("KANA:"):
                result["kana"] = line[5:].strip()
            elif line.startswith("EN:"):
                result["translation"] = line[3:].strip()
        return result
    except Exception as e:
        print("    Gemini error for {}: {}".format(kanji, e))
        return {"sentence": "", "kana": "", "translation": ""}


def gemini_confusables(model, kanji, meaning):
    prompt = (
        "List up to 3 Japanese kanji commonly confused with {} ({}) by learners "
        "due to visual similarity. Reply with ONLY kanji separated by commas, e.g.: 土,士,工 "
        "If none, reply: none"
    ).format(kanji, meaning)
    try:
        resp = model.generate_content(prompt)
        text = resp.text.strip()
        if text.lower() == "none":
            return ""
        cleaned = "".join(c for c in text if "\u4e00" <= c <= "\u9fff" or c == ",")
        return cleaned.strip(",")
    except Exception as e:
        print("    Gemini confusables error for {}: {}".format(kanji, e))
        return ""


# ---------------------------------------------------------------------------
# CSV processing
# ---------------------------------------------------------------------------


def collect_all_kanji(files: List[Tuple[str, str]]) -> set:
    """Collect every kanji from all CSV files for the confusables corpus."""
    all_kanji = set()
    for filepath, _ in files:
        if not os.path.exists(filepath):
            continue
        with open(filepath, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                k = row.get("kanji", "").strip()
                if k:
                    all_kanji.add(k)
    return all_kanji


def enrich_csv(
    filepath,
    level,
    kradfile,
    confusables_map,
    run_sentences,
    run_confusables,
    run_radicals,
    sentence_index=None,
    gemini_model=None,
):
    if not os.path.exists(filepath):
        print("Skipping (not found): {}".format(filepath))
        return

    print("\n=== Enriching: {} ===".format(filepath))

    with open(filepath, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    # Add missing columns
    for col in ["sentence", "kana", "translation", "radicals", "confusables"]:
        if col not in fieldnames:
            fieldnames.append(col)

    total = len(rows)
    for i, row in enumerate(rows):
        kanji = row.get("kanji", "").strip()
        meaning = row.get("meaning", "").strip()
        if not kanji:
            continue

        print("  [{}/{}] {}".format(i + 1, total, kanji), end="", flush=True)

        # Radicals
        if run_radicals and not row.get("radicals"):
            rads = kradfile.get(kanji, [])
            row["radicals"] = " ".join(rads)
            print("  radicals: {}".format(row["radicals"] or "—"), end="")

        # Confusables
        if run_confusables and not row.get("confusables"):
            if gemini_model:
                row["confusables"] = gemini_confusables(gemini_model, kanji, meaning)
                time.sleep(1.0)
            else:
                row["confusables"] = confusables_map.get(kanji, "")
            print("  confusables: {}".format(row["confusables"] or "—"), end="")

        # Sentences
        if run_sentences and not row.get("sentence"):
            if gemini_model:
                res = gemini_sentence(gemini_model, kanji, meaning, level)
                row["sentence"] = res["sentence"]
                row["kana"] = res["kana"]
                row["translation"] = res["translation"]
                time.sleep(1.0)
            elif sentence_index is not None:
                jp, en = lookup_sentence(sentence_index, kanji)
                row["sentence"] = jp
                row["kana"] = ""
                row["translation"] = en
            print("  sentence: {}".format(row["sentence"] or "—"), end="")

        print()

        # Ensure all fields exist
        for field in fieldnames:
            row.setdefault(field, "")

    with open(filepath, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print("  Saved: {}".format(filepath))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Enrich kanji CSVs with sentences, radicals, and confusables (no API key needed)."
    )
    parser.add_argument(
        "csv", nargs="?", help="CSV file to enrich (default: all N1-N5)."
    )
    parser.add_argument(
        "--only",
        choices=["sentences", "radicals", "confusables"],
        help="Run only one enrichment type.",
    )
    parser.add_argument(
        "--llm",
        choices=["gemini"],
        help="Use an LLM for higher-quality sentences/confusables (requires GEMINI_API_KEY).",
    )
    args = parser.parse_args()

    run_sentences = args.only in (None, "sentences")
    run_confusables = args.only in (None, "confusables")
    run_radicals = args.only in (None, "radicals")

    # Determine files
    if args.csv:
        basename = os.path.splitext(os.path.basename(args.csv))[0]
        level = basename.split("_")[-1].upper() if "_" in basename else "N5"
        files = [(args.csv, level)]
    else:
        files = [(f, lvl) for f, lvl in JLPT_FILES if os.path.exists(f)]

    # KRADFILE
    download_kradfile()
    kradfile = load_kradfile()
    print("Loaded {} kanji from KRADFILE.".format(len(kradfile)))

    # Tanaka Corpus (offline sentences, no rate limit)
    sentence_index = None
    if run_sentences and not args.llm:
        if download_tanaka():
            pairs = load_tanaka()
            sentence_index = build_sentence_index(pairs)
            print(
                "Sentence index ready ({} unique kanji indexed).".format(
                    len(sentence_index)
                )
            )

    # Confusables map (computed once from all JLPT kanji)
    confusables_map = {}
    if run_confusables and not args.llm:
        print("Computing confusables from radical similarity...")
        all_kanji = collect_all_kanji(JLPT_FILES)
        confusables_map = build_confusables(kradfile, all_kanji)
        print("Confusables ready for {} kanji.".format(len(confusables_map)))

    # Optional Gemini client
    gemini_model = None
    if args.llm == "gemini":
        gemini_model = make_gemini_client()
        if gemini_model:
            print("Using Gemini for LLM-generated content.")
        else:
            print("Gemini unavailable — falling back to Tatoeba / KRADFILE.")

    for filepath, level in files:
        enrich_csv(
            filepath,
            level,
            kradfile,
            confusables_map,
            run_sentences,
            run_confusables,
            run_radicals,
            sentence_index=sentence_index,
            gemini_model=gemini_model,
        )

    print("\nDone.")
    if run_sentences and not gemini_model:
        print("Note: 'kana' column is blank (Tanaka Corpus doesn't include furigana).")
        print("Fill it manually or rerun with --llm gemini if you obtain a free key.")


if __name__ == "__main__":
    main()
