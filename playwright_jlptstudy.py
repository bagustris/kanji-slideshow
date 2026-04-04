import csv
import argparse
import time

def scrape_kanji(level):
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
            print(f"Found {len(kanji_boxes)} kanji boxes")

            total_to_process = len(kanji_boxes)

            for i, box in enumerate(kanji_boxes[:total_to_process], start=1):
                print(f"Processing kanji {i}/{total_to_process}...")

                try:
                    box.click()
                    time.sleep(0.5)

                    if page.query_selector("#kanji-body #kanji-data"):
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
                                print(f"  ✓ Completed {i} kanji so far...")

                        else:
                            print(f"  ✗ Could not find elements for kanji {i}")
                    else:
                        print(f"  ✗ Kanji data not found for kanji {i}")

                except Exception as e:
                    print(f"  ✗ Error processing kanji {i}: {e}")
        finally:
            browser.close()

    return results


def write_results_csv(level, results):
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
                            f'{compound["word"]} ({compound["kana"]}) = {compound["translation"]}'
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
    args = parser.parse_args()

    results = scrape_kanji(args.level)
    print(f"Scraped {len(results)} kanji successfully!")

    filename = write_results_csv(args.level, results)
    print(f"Data saved to {filename} with {len(results)} entries!")

if __name__ == "__main__":
    main()
