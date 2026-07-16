import csv
import argparse
import logging
from typing import List, Dict, Optional

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def scrape_kanji(level: int, max_retries: int = 3) -> List[Dict]:
    """Scrape JLPT kanji data from jlptstudy.net with retry logic."""
    results = []
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit(
            "Playwright is required. Install it with: python3 -m pip install playwright"
        ) from exc

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            page.goto(f"https://www.jlptstudy.net/N{level}/?kanji-list")
            page.wait_for_load_state("networkidle")

            kanji_boxes = page.query_selector_all("#kanji-body .kanji-box")
            logger.info(f"Found {len(kanji_boxes)} kanji boxes")

            total_to_process = len(kanji_boxes)

            for i, box in enumerate(kanji_boxes[:total_to_process], start=1):
                logger.info(f"Processing kanji {i}/{total_to_process}...")

                for attempt in range(max_retries):
                    try:
                        box.click()
                        # Wait for kanji data to appear (replaces time.sleep)
                        page.wait_for_selector("#kanji-body #kanji-data", timeout=5000)

                        kanji_el = page.query_selector(
                            "#kanji-body #kanji-data .data-header .char"
                        )
                        meaning_el = page.query_selector(
                            "#kanji-body #kanji-data .data-header .meaning"
                        )

                        if kanji_el and meaning_el:
                            kanji = page.evaluate(
                                "(el) => el.textContent || el.innerText", kanji_el
                            ).strip()
                            meaning = page.evaluate(
                                "(el) => el.textContent || el.innerText", meaning_el
                            ).strip()

                            readings = []
                            reading_elements = page.query_selector_all(
                                "#kanji-body .reading"
                            )
                            for r in reading_elements:
                                reading = page.evaluate(
                                    "(el) => el.textContent || el.innerText", r
                                )
                                if reading and reading.strip():
                                    readings.append(reading.strip())

                            compounds = []
                            compound_elements = page.query_selector_all(
                                "#kanji-body .compound"
                            )
                            for c in compound_elements:
                                word_el = c.query_selector(".char")
                                kana_el = c.query_selector(".kana")
                                trans_el = c.query_selector(".translation")

                                if word_el and kana_el and trans_el:
                                    word = page.evaluate(
                                        "(el) => el.textContent || el.innerText",
                                        word_el,
                                    )
                                    kana = page.evaluate(
                                        "(el) => el.textContent || el.innerText",
                                        kana_el,
                                    )
                                    translation = page.evaluate(
                                        "(el) => el.textContent || el.innerText",
                                        trans_el,
                                    )

                                    if word and kana and translation:
                                        compounds.append(
                                            {
                                                "word": word.strip(),
                                                "kana": kana.strip(),
                                                "translation": translation.strip(),
                                            }
                                        )

                            results.append(
                                {
                                    "kanji": kanji,
                                    "meaning": meaning,
                                    "readings": readings,
                                    "compounds": compounds,
                                }
                            )

                            if i % 10 == 0:
                                logger.info(f"  ✓ Completed {i} kanji so far...")

                            break  # Success, exit retry loop

                        else:
                            logger.warning(f"  ✗ Could not find elements for kanji {i}")
                            if attempt < max_retries - 1:
                                page.wait_for_timeout(1000)  # Wait before retry
                                continue
                            break

                    except Exception as e:
                        logger.error(
                            f"  ✗ Error processing kanji {i} (attempt {attempt + 1}): {e}"
                        )
                        if attempt < max_retries - 1:
                            page.wait_for_timeout(2000)  # Wait before retry
                        else:
                            logger.error(
                                f"  ✗ Failed to process kanji {i} after {max_retries} attempts"
                            )

        finally:
            browser.close()

    return results


def write_results_csv(level: int, results: List[Dict]) -> str:
    """Write scraped results to CSV file."""
    filename = f"kanji_n{level}.csv"
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["kanji", "meaning", "readings", "compounds"]
        )
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "kanji": result["kanji"],
                    "meaning": result["meaning"],
                    "readings": "; ".join(result["readings"]),
                    "compounds": "; ".join(
                        [
                            f"{compound['word']} ({compound['kana']}) = {compound['translation']}"
                            for compound in result["compounds"]
                        ]
                    ),
                }
            )

    return filename


def main():
    parser = argparse.ArgumentParser(description="Scrape JLPT kanji data")
    parser.add_argument(
        "-n",
        "--level",
        type=int,
        default=2,
        choices=[1, 2, 3, 4, 5],
        help="JLPT level to scrape (1-5, default: 2)",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Maximum retry attempts per kanji (default: 3)",
    )
    args = parser.parse_args()

    results = scrape_kanji(args.level, max_retries=args.max_retries)
    logger.info(f"Scraped {len(results)} kanji successfully!")

    filename = write_results_csv(args.level, results)
    logger.info(f"Data saved to {filename} with {len(results)} entries!")


if __name__ == "__main__":
    main()
