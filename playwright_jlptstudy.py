from playwright.sync_api import sync_playwright
import csv
import time
import argparse

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Scrape JLPT kanji data')
    parser.add_argument('-n', '--level', type=int, default=2, choices=[1, 2, 3, 4, 5], 
                       help='JLPT level (2-5, default: 2)')
    args = parser.parse_args()

    # Navigate to the appropriate JLPT level page
    page.goto(f"https://www.jlptstudy.net/N{args.level}/?kanji-list")
    page.wait_for_load_state("networkidle")

    kanji_boxes = page.query_selector_all("#kanji-body .kanji-box")
    print(f"Found {len(kanji_boxes)} kanji boxes")

    results = []

    # Process all kanji (adjust as needed)
    total_to_process = len(kanji_boxes)
    
    for i, box in enumerate(kanji_boxes[:total_to_process], start=1):
        print(f"Processing kanji {i}/{total_to_process}...")
        
        try:
            box.click()
            time.sleep(0.5)  # Small delay for content to load
            
            # Check if kanji data exists
            if page.query_selector("#kanji-body #kanji-data"):
                # Use JavaScript evaluation to force extract text (works even for hidden elements)
                kanji_el = page.query_selector("#kanji-body #kanji-data .data-header .char")
                meaning_el = page.query_selector("#kanji-body #kanji-data .data-header .meaning")
                
                if kanji_el and meaning_el:
                    kanji = page.evaluate("(el) => el.textContent || el.innerText", kanji_el).strip()
                    meaning = page.evaluate("(el) => el.textContent || el.innerText", meaning_el).strip()
                    
                    # Get readings using force extraction
                    readings = []
                    reading_elements = page.query_selector_all("#kanji-body .reading")
                    for r in reading_elements:
                        reading = page.evaluate("(el) => el.textContent || el.innerText", r)
                        if reading and reading.strip():
                            readings.append(reading.strip())
                    
                    # Get compounds using force extraction
                    compounds = []
                    compound_elements = page.query_selector_all("#kanji-body .compound")
                    for c in compound_elements:
                        word_el = c.query_selector(".char")
                        kana_el = c.query_selector(".kana")
                        trans_el = c.query_selector(".translation")
                        
                        if word_el and kana_el and trans_el:
                            word = page.evaluate("(el) => el.textContent || el.innerText", word_el)
                            kana = page.evaluate("(el) => el.textContent || el.innerText", kana_el)
                            translation = page.evaluate("(el) => el.textContent || el.innerText", trans_el)
                            
                            if word and kana and translation:
                                compounds.append({
                                    "word": word.strip(),
                                    "kana": kana.strip(),
                                    "translation": translation.strip()
                                })

                    results.append({
                        "kanji": kanji,
                        "meaning": meaning,
                        "readings": readings,
                        "compounds": compounds
                    })
                    
                    if i % 10 == 0:  # Progress update every 10 kanji
                        print(f"  ✓ Completed {i} kanji so far...")
                        
                else:
                    print(f"  ✗ Could not find elements for kanji {i}")
            else:
                print(f"  ✗ Kanji data not found for kanji {i}")
                
        except Exception as e:
            print(f"  ✗ Error processing kanji {i}: {e}")

    browser.close()

print(f"Scraped {len(results)} kanji successfully!")

# Save as CSV (flattening compound info)
filename = f"kanji_n{args.level}.csv"
with open(filename, "w", newline='', encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=["kanji", "meaning", "readings", "compounds"])
    writer.writeheader()
    for r in results:
        writer.writerow({
            "kanji": r["kanji"],
            "meaning": r["meaning"],
            "readings": "; ".join(r["readings"]),
            "compounds": "; ".join([f'{c["word"]} ({c["kana"]}) = {c["translation"]}' for c in r["compounds"]])
        })

print(f"Data saved to {filename} with {len(results)} entries!")
with open("kanji_n2.csv", "w", newline='', encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=["kanji", "meaning", "readings", "compounds"])
    writer.writeheader()
    for r in results:
        writer.writerow({
            "kanji": r["kanji"],
            "meaning": r["meaning"],
            "readings": "; ".join(r["readings"]),
            "compounds": "; ".join([f"{c['word']} ({c['kana']}) = {c['translation']}" for c in r["compounds"]])
        })
