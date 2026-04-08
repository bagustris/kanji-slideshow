#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JLPT N2 Kanji Image Generator
Processes kanji data from CSV file and creates wallpaper images.

Input format expected (CSV file with header):
```
kanji,meaning,readings,compounds
腕,"arm, ability, talent",ワン; うで,"右腕 (うわん) = right arm; 手腕 (しゅわん) = ability; ..."
```
"""

import csv
import os
import re
import sys
import argparse

from PIL import Image, ImageDraw, ImageFont

# Default image configuration (wallpaper baseline)
BASE_IMAGE_WIDTH = 1920
BASE_IMAGE_HEIGHT = 1080
BACKGROUND_COLOR = (0, 0, 0, 255)  # Black background with alpha
TEXT_COLOR = (255, 255, 255)  # White text
COMPOUND_BOX_COLOR = (20, 20, 20, 255)  # Slightly lighter black for subtle contrast
COMPOUND_TEXT_COLOR = (255, 255, 255)  # White text for compounds
COMPOUND_READING_COLOR = (
    255,
    165,
    0,
)  # Orange color for hiragana readings in compounds
ACCENT_COLOR = (100, 149, 237)  # Cornflower blue for section headers
HIGHLIGHT_COLOR = (80, 200, 255)  # Bright blue for target kanji in compounds
KANJI_COLOR = (255, 255, 255)  # White for main kanji
STROKE_ORDER_COLOR = (128, 128, 128)  # Gray for stroke order info
READING_BG_COLOR = (45, 45, 45, 255)  # Subtle background for readings


class KanjiImageGenerator:
    def __init__(self, image_width=BASE_IMAGE_WIDTH, image_height=BASE_IMAGE_HEIGHT):
        self.image_width = int(image_width)
        self.image_height = int(image_height)
        self.scale = min(
            self.image_width / float(BASE_IMAGE_WIDTH),
            self.image_height / float(BASE_IMAGE_HEIGHT),
        )
        self.font_large = None
        self.font_medium = None
        self.font_small = None
        self._load_fonts()

    def _s(self, px, minimum=1):
        """Scale a pixel value from the 1920x1080 baseline."""
        return max(int(round(px * self.scale)), minimum)

    def _load_fonts(self):
        """Load suitable fonts for Japanese characters."""
        font_paths = [
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",  # Now using regular (non-bold) font
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",  # Fallback Bold
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Regular.ttf",  # Fallback Regular
            "/System/Library/Fonts/Hiragino Sans GB.ttc",  # macOS
            "/Windows/Fonts/msgothic.ttc",  # Windows
        ]

        # Try to load fonts in different sizes.
        # Font sizes are scaled based on the chosen output resolution.
        for font_path in font_paths:
            if os.path.exists(font_path):
                try:
                    self.font_large = ImageFont.truetype(
                        font_path, self._s(300, minimum=40)
                    )  # Main kanji (increased to 300px)
                    self.font_medium = ImageFont.truetype(
                        font_path, self._s(42, minimum=15)
                    )  # Meaning (increased to 42px)
                    self.font_reading = ImageFont.truetype(
                        font_path, self._s(42, minimum=15)
                    )  # Readings (increased to 42px)
                    self.font_small = ImageFont.truetype(
                        font_path, self._s(42, minimum=15)
                    )  # Compounds (42px)
                    self.font_jis = ImageFont.truetype(
                        font_path, self._s(16, minimum=9)
                    )  # JIS code
                    print("Successfully loaded font: {}".format(font_path))
                    return
                except Exception as e:
                    print("Failed to load font {}: {}".format(font_path, e))
                    continue

        # Fallback to default font
        print(
            "Warning: Using default font. Japanese characters may not display correctly."
        )
        try:
            self.font_large = ImageFont.load_default()
            self.font_medium = ImageFont.load_default()
            self.font_reading = ImageFont.load_default()
            self.font_small = ImageFont.load_default()
            self.font_jis = ImageFont.load_default()
        except Exception:
            print("Error: Could not load any font")

    def parse_csv_entry(self, row):
        """
        Parse a kanji entry from CSV format.

        Args:
            row (dict): CSV row with keys: kanji, meaning, readings, compounds

        Returns:
            dict: Parsed kanji data
        """
        kanji = self._get_csv_value(row, "kanji")
        meaning = self._get_csv_value(row, "meaning")
        readings_str = self._get_csv_value(row, "readings")
        compounds_str = self._get_csv_value(row, "compounds")

        # Parse readings - separate hiragana and katakana
        hiragana_readings = []
        katakana_readings = []

        if readings_str:
            # Split by semicolon and comma
            reading_parts = []
            for part in readings_str.split(";"):
                reading_parts.extend([p.strip() for p in part.split(",") if p.strip()])

            for reading in reading_parts:
                reading = reading.strip()
                if reading:
                    # Check if it's hiragana or katakana
                    if re.match(r"^[\u3040-\u309F\s・.,ー]+$", reading):  # Hiragana
                        hiragana_readings.append(reading)
                    elif re.match(r"^[\u30A0-\u30FF\s・,ー]+$", reading):  # Katakana
                        katakana_readings.append(reading)
                    else:
                        # Mixed or other - try to separate
                        hiragana_part = re.findall(r"[\u3040-\u309F・.,ー]+", reading)
                        katakana_part = re.findall(r"[\u30A0-\u30FF・,ー]+", reading)
                        if hiragana_part:
                            hiragana_readings.extend(hiragana_part)
                        if katakana_part:
                            katakana_readings.extend(katakana_part)

        # Parse compounds - format: "右腕 (うわん) = right arm; 手腕 (しゅわん) = ability; ..."
        compounds = []
        if compounds_str:
            # Split by semicolon first
            compound_parts = [
                part.strip() for part in compounds_str.split(";") if part.strip()
            ]

            for compound_part in compound_parts:
                # Match pattern: "kanji (reading) = meaning"
                match = re.match(
                    r"([^\s(]+)\s*\(([^)]+)\)\s*=\s*(.+)", compound_part.strip()
                )
                if match:
                    compounds.append(
                        {
                            "kanji": match.group(1).strip(),
                            "reading": match.group(2).strip(),
                            "meaning": match.group(3).strip(),
                        }
                    )

        return {
            "kanji": kanji,
            "meaning": meaning,
            "hiragana_readings": hiragana_readings,
            "katakana_readings": katakana_readings,
            "compounds": compounds,
        }

    @staticmethod
    def _get_csv_value(row, field_name):
        """Return a normalized CSV field value or raise a clear error."""
        if field_name not in row:
            raise KeyError("Missing required CSV column: {}".format(field_name))

        value = row[field_name]
        if value is None:
            return ""

        return value.strip()

    def create_kanji_image(self, kanji_data, output_path):
        """
        Create a kanji wallpaper image with the specified layout.

        Args:
            kanji_data (dict): Parsed kanji data
            output_path (str): Path to save the image
        """
        if not kanji_data or not kanji_data.get("kanji"):
            print("Warning: Invalid kanji data for {}".format(output_path))
            return False

        # Create image
        image = Image.new(
            "RGBA", (self.image_width, self.image_height), BACKGROUND_COLOR
        )
        draw = ImageDraw.Draw(image)

        kanji = kanji_data["kanji"]

        # Collect target readings for highlighting in compounds
        target_readings = []
        all_raw_readings = kanji_data.get("hiragana_readings", []) + kanji_data.get(
            "katakana_readings", []
        )
        for r in all_raw_readings:
            # Remove okurigana markers (dot or anything after)
            clean_r = re.split(r"[.・]", r)[0].strip()
            if not clean_r:
                continue
            # Convert to hiragana for matching (compound readings in CSV are usually hiragana)
            h_r = "".join(
                chr(ord(c) - 0x60) if 0x30A1 <= ord(c) <= 0x30F6 else c for c in clean_r
            )
            target_readings.append(h_r)
        # Sort by length descending to match longest possible reading first
        target_readings = sorted(list(set(target_readings)), key=len, reverse=True)

        # --- Text Positioning ---
        x_margin = self._s(80)
        # Center content vertically on the 1920x1080 canvas
        # Estimate total content height and center it
        estimated_content_height = self._s(400)  # Approximate height of all content
        y_center_offset = (self.image_height - estimated_content_height) // 2
        y_margin = max(self._s(50), y_center_offset)  # Ensure minimum margin
        vertical_spacing = self._s(20)  # Additional vertical space between elements

        # Left alignment for all text elements
        left_x = x_margin

        # Draw the main Kanji character (large, left side) - centered vertically
        kanji_y = y_margin + self._s(30)
        draw.text((left_x, kanji_y), kanji, font=self.font_large, fill=KANJI_COLOR)

        # Calculate position for right column (next to kanji with some spacing)
        right_x = left_x + self._s(350)  # Position right column next to kanji
        right_y = y_margin

        # Draw JIS code at top-right corner - aligned with top (skip if not available)
        if kanji_data.get("jis_code") and kanji_data["jis_code"].strip():
            jis_text = kanji_data["jis_code"]
            bbox = draw.textbbox((0, 0), jis_text, font=self.font_jis)
            jis_width = bbox[2] - bbox[0]
            jis_x = self.image_width - x_margin - jis_width
            draw.text((jis_x, right_y), jis_text, font=self.font_jis, fill=TEXT_COLOR)

        # Draw meaning - left-aligned in right column (no label)
        draw.text(
            (right_x, right_y),
            kanji_data["meaning"],
            font=self.font_medium,
            fill=TEXT_COLOR,
        )
        right_y += self._s(55) + vertical_spacing

        pill_padding_x = self._s(6)
        pill_padding_y = self._s(4)
        pill_gap = self._s(16)
        max_reading_x = self.image_width - x_margin
        reading_line_step = self._s(55)

        def _draw_text_background(x, y, text_width, text_bbox, padding_x, padding_y):
            """Draw a padded background behind text drawn at (x, y)."""
            # text_bbox is a (left, top, right, bottom) bbox for the text at origin.
            x0 = x - padding_x
            y0 = y + text_bbox[1] - padding_y
            x1 = x + text_width + padding_x
            y1 = y + text_bbox[3] + padding_y
            try:
                draw.rounded_rectangle(
                    (x0, y0, x1, y1), radius=self._s(10), fill=READING_BG_COLOR
                )
            except Exception:
                draw.rectangle((x0, y0, x1, y1), fill=READING_BG_COLOR)

        def _draw_readings(readings, y):
            current_x = right_x

            for reading in readings:
                # Determine pill dimensions up front for wrapping.
                if "・" in reading or "." in reading:
                    if "・" in reading:
                        parts = reading.split("・", 1)
                    else:
                        parts = reading.split(".", 1)

                    bbox_before = draw.textbbox(
                        (0, 0), parts[0], font=self.font_reading
                    )
                    bbox_after = draw.textbbox((0, 0), parts[1], font=self.font_reading)
                    width_before = bbox_before[2] - bbox_before[0]
                    width_after = bbox_after[2] - bbox_after[0]

                    combined_width = width_before + width_after
                    pill_total_width = combined_width + (2 * pill_padding_x)

                    if (
                        current_x + pill_total_width > max_reading_x
                        and current_x != right_x
                    ):
                        y += reading_line_step
                        current_x = right_x

                    combined_bbox = (
                        0,
                        min(bbox_before[1], bbox_after[1]),
                        combined_width,
                        max(bbox_before[3], bbox_after[3]),
                    )
                    _draw_text_background(
                        current_x,
                        y,
                        combined_width,
                        combined_bbox,
                        pill_padding_x,
                        pill_padding_y,
                    )

                    # Before dot: bright blue (the kanji reading); after dot: white (okurigana)
                    draw.text(
                        (current_x, y),
                        parts[0],
                        font=self.font_reading,
                        fill=HIGHLIGHT_COLOR,
                    )
                    draw.text(
                        (current_x + width_before, y),
                        parts[1],
                        font=self.font_reading,
                        fill=TEXT_COLOR,
                    )
                    current_x += pill_total_width + pill_gap
                else:
                    bbox = draw.textbbox((0, 0), reading, font=self.font_reading)
                    width = bbox[2] - bbox[0]
                    pill_total_width = width + (2 * pill_padding_x)

                    if (
                        current_x + pill_total_width > max_reading_x
                        and current_x != right_x
                    ):
                        y += reading_line_step
                        current_x = right_x

                    _draw_text_background(
                        current_x,
                        y,
                        width,
                        bbox,
                        pill_padding_x,
                        pill_padding_y,
                    )
                    draw.text(
                        (current_x, y),
                        reading,
                        font=self.font_reading,
                        fill=HIGHLIGHT_COLOR,
                    )
                    current_x += pill_total_width + pill_gap

            return y + reading_line_step + vertical_spacing

        # Draw katakana readings first (onyomi)
        if kanji_data.get("katakana_readings"):
            right_y = _draw_readings(kanji_data["katakana_readings"], right_y)

        # Draw hiragana readings second (kunyomi)
        if kanji_data.get("hiragana_readings"):
            right_y = _draw_readings(kanji_data["hiragana_readings"], right_y)

        # --- Compounds Box ---
        # Remove compounds label, start box directly
        box_padding = self._s(15)
        line_spacing = self._s(55)  # Increased spacing for larger compound font
        box_x0 = right_x - box_padding  # Left-aligned with other text
        box_y0 = right_y + vertical_spacing

        # Calculate available box width more conservatively to prevent overflow
        available_width = (
            self.image_width - right_x - x_margin - self._s(20)
        )  # Extra margin for safety
        max_box_width = available_width - (box_padding * 2)

        # Process compounds and handle text wrapping with colored components
        wrapped_compound_lines = []
        for compound in kanji_data["compounds"]:
            # Calculate widths of each component
            kanji_bbox = draw.textbbox((0, 0), compound["kanji"], font=self.font_small)
            kanji_width = kanji_bbox[2] - kanji_bbox[0]

            reading_bbox = draw.textbbox(
                (0, 0), compound["reading"], font=self.font_small
            )
            reading_width = reading_bbox[2] - reading_bbox[0]

            # Check if kanji + reading + some meaning fits on one line
            kanji_reading_width = (
                kanji_width + self._s(8) + reading_width + self._s(12)
            )  # Including spacing
            available_for_meaning = max_box_width - kanji_reading_width

            # Try to fit as much meaning as possible on the first line
            meaning_words = compound["meaning"].split()
            first_line_meaning = ""
            remaining_meaning = ""

            for i, word in enumerate(meaning_words):
                test_meaning = (
                    first_line_meaning + (" " if first_line_meaning else "") + word
                )
                meaning_bbox = draw.textbbox((0, 0), test_meaning, font=self.font_small)
                meaning_width = meaning_bbox[2] - meaning_bbox[0]

                if meaning_width <= available_for_meaning * 0.9:  # Conservative limit
                    first_line_meaning = test_meaning
                else:
                    # This word doesn't fit, put remaining words on next lines
                    remaining_meaning = " ".join(meaning_words[i:])
                    break
            else:
                # All meaning words fit on first line
                first_line_meaning = compound["meaning"]
                remaining_meaning = ""

            # Add the first line with kanji, reading, and partial meaning
            if first_line_meaning:
                wrapped_compound_lines.append(
                    {
                        "kanji": compound["kanji"],
                        "reading": compound["reading"],
                        "meaning": first_line_meaning,
                    }
                )
            else:
                # Even first word doesn't fit, just put kanji and reading
                wrapped_compound_lines.append(
                    {
                        "kanji": compound["kanji"],
                        "reading": compound["reading"],
                        "meaning": "",
                    }
                )
                remaining_meaning = compound["meaning"]

            # Handle remaining meaning on subsequent lines
            if remaining_meaning:
                # Split remaining meaning into lines that fit
                remaining_words = remaining_meaning.split()
                current_line = ""

                for word in remaining_words:
                    test_line = current_line + (" " if current_line else "") + word
                    test_bbox = draw.textbbox((0, 0), test_line, font=self.font_small)
                    test_width = test_bbox[2] - test_bbox[0]

                    if test_width <= max_box_width * 0.9:
                        current_line = test_line
                    else:
                        # Line is full, save it and start new line
                        if current_line:
                            wrapped_compound_lines.append(
                                {"kanji": "", "reading": "", "meaning": current_line}
                            )
                        current_line = word

                # Add the last line
                if current_line:
                    wrapped_compound_lines.append(
                        {"kanji": "", "reading": "", "meaning": current_line}
                    )

        # Calculate box height based on actual wrapped lines + ensure bottom is visible
        if wrapped_compound_lines:
            # Reserve space at bottom of image to ensure box is fully visible
            max_available_height = (
                self.image_height - box_y0 - self._s(30)
            )  # From bottom edge
            ideal_content_height = len(wrapped_compound_lines) * line_spacing
            actual_content_height = min(
                ideal_content_height, max_available_height - (box_padding * 2)
            )

            box_height = actual_content_height + (box_padding * 2)
            box_y1 = box_y0 + box_height
        else:
            box_y1 = box_y0 + (box_padding * 2) + 30  # Minimum height for empty box

        # Define the box dimensions
        box_x1 = self.image_width - x_margin

        # Draw the filled rectangle with visible borders
        draw.rectangle(
            (box_x0, box_y0, box_x1, box_y1),
            fill=COMPOUND_BOX_COLOR,
            outline=TEXT_COLOR,
            width=2,
        )

        # Now draw the wrapped compound text with colored components
        if wrapped_compound_lines:
            compound_y = box_y0 + box_padding
            for line_parts in wrapped_compound_lines:
                current_x = right_x

                # Handle different line types
                if (
                    line_parts["kanji"]
                    and line_parts["reading"]
                    and line_parts["meaning"]
                ):
                    # Full compound line with all parts - reading enclosed in brackets
                    # Draw kanji part character by character, highlighting target kanji
                    target_kanji = kanji_data["kanji"]
                    compound_has_target = target_kanji in line_parts["kanji"]
                    for char in line_parts["kanji"]:
                        char_color = (
                            HIGHLIGHT_COLOR
                            if char == target_kanji
                            else COMPOUND_READING_COLOR
                        )
                        draw.text(
                            (current_x, compound_y),
                            char,
                            font=self.font_small,
                            fill=char_color,
                        )
                        char_bbox = draw.textbbox((0, 0), char, font=self.font_small)
                        current_x += char_bbox[2] - char_bbox[0]
                    current_x += self._s(8)  # spacing after kanji word

                    # Draw reading part in white brackets (learning kanji and okurigana in blue)
                    reading_text = line_parts["reading"]

                    # Draw opening bracket in white
                    draw.text(
                        (current_x, compound_y),
                        "(",
                        font=self.font_small,
                        fill=COMPOUND_TEXT_COLOR,
                    )
                    bbox = draw.textbbox((0, 0), "(", font=self.font_small)
                    current_x += bbox[2] - bbox[0]

                    # Find all non-overlapping matches within reading_text (no brackets)
                    reading_matches = []
                    for tr in target_readings:
                        if not tr:
                            continue
                        start_search = 0
                        while True:
                            idx = reading_text.find(tr, start_search)
                            if idx == -1:
                                break
                            if not any(
                                idx < e and idx + len(tr) > s
                                for s, e in reading_matches
                            ):
                                reading_matches.append((idx, idx + len(tr)))
                            start_search = idx + 1

                    reading_matches.sort()

                    # Draw the reading segments: matched parts in blue, others in orange
                    last_idx = 0
                    for start, end in reading_matches:
                        if start > last_idx:
                            seg = reading_text[last_idx:start]
                            draw.text(
                                (current_x, compound_y),
                                seg,
                                font=self.font_small,
                                fill=COMPOUND_READING_COLOR,
                            )
                            bbox = draw.textbbox((0, 0), seg, font=self.font_small)
                            current_x += bbox[2] - bbox[0]

                        seg = reading_text[start:end]
                        draw.text(
                            (current_x, compound_y),
                            seg,
                            font=self.font_small,
                            fill=HIGHLIGHT_COLOR,
                        )
                        bbox = draw.textbbox((0, 0), seg, font=self.font_small)
                        current_x += bbox[2] - bbox[0]
                        last_idx = end

                    # Draw remaining text after last match (okurigana or non-matched reading)
                    if last_idx < len(reading_text):
                        remaining = reading_text[last_idx:]
                        remaining_color = (
                            HIGHLIGHT_COLOR if reading_matches else COMPOUND_READING_COLOR
                        )
                        draw.text(
                            (current_x, compound_y),
                            remaining,
                            font=self.font_small,
                            fill=remaining_color,
                        )
                        bbox = draw.textbbox((0, 0), remaining, font=self.font_small)
                        current_x += bbox[2] - bbox[0]

                    # Draw closing bracket in white
                    draw.text(
                        (current_x, compound_y),
                        ")",
                        font=self.font_small,
                        fill=COMPOUND_TEXT_COLOR,
                    )
                    bbox = draw.textbbox((0, 0), ")", font=self.font_small)
                    current_x += bbox[2] - bbox[0]

                    current_x += 12  # Add more spacing before meaning

                    # Draw meaning part (white) - no equals sign
                    draw.text(
                        (current_x, compound_y),
                        line_parts["meaning"],
                        font=self.font_small,
                        fill=COMPOUND_TEXT_COLOR,
                    )

                elif line_parts["meaning"]:
                    # Continuation line with just meaning (or overflow text)
                    draw.text(
                        (current_x, compound_y),
                        line_parts["meaning"],
                        font=self.font_small,
                        fill=COMPOUND_TEXT_COLOR,
                    )

                compound_y += line_spacing

                # Safety check: don't draw text outside the box
                if compound_y > box_y1 - box_padding:
                    break

        # Save the image
        try:
            image.save(output_path, "PNG")
            print("✓ Created: {}".format(output_path))
            return True
        except Exception as e:
            print("✗ Error saving {}: {}".format(output_path, e))
            return False


def parse_kanji_csv_file(file_path, parser=None):
    """
    Parse the CSV file containing kanji data.

    Args:
        file_path (str): Path to the CSV file

    Returns:
        list: List of parsed kanji data dictionaries
    """
    if not os.path.exists(file_path):
        print("Error: File {} not found.".format(file_path))
        return []

    parsed_kanji = []
    parser = parser or KanjiImageGenerator()

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row_num, row in enumerate(
                reader, start=2
            ):  # Start at 2 since header is row 1
                try:
                    kanji_data = parser.parse_csv_entry(row)
                    if kanji_data and kanji_data.get("kanji"):
                        parsed_kanji.append(kanji_data)
                    else:
                        print("Warning: Invalid kanji data at row {}".format(row_num))
                except Exception as e:
                    print("Error parsing row {}: {}".format(row_num, e))
                    continue

    except Exception as e:
        print("Error reading CSV file: {}".format(e))
        return []

    return parsed_kanji


def main():
    """Generate kanji images from one or more CSV files."""

    def _detect_screen_size():
        try:
            import tkinter as tk

            root = tk.Tk()
            root.withdraw()
            width = root.winfo_screenwidth()
            height = root.winfo_screenheight()
            root.destroy()
            return int(width), int(height)
        except Exception:
            return None

    parser = argparse.ArgumentParser(
        description="Generate JLPT kanji wallpaper images from CSV files."
    )
    parser.add_argument(
        "csv",
        nargs="?",
        help="Optional input CSV file. If omitted, processes kanji_n2.csv..kanji_n5.csv",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=BASE_IMAGE_WIDTH,
        help="Output image width in pixels (default: 1920)",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=BASE_IMAGE_HEIGHT,
        help="Output image height in pixels (default: 1080)",
    )
    parser.add_argument(
        "--screen",
        action="store_true",
        help="Auto-detect screen resolution (requires a GUI session).",
    )

    args = parser.parse_args()

    if args.width <= 0 or args.height <= 0:
        parser.error("--width and --height must be positive integers")

    if args.csv:
        input_files = [args.csv]
    else:
        input_files = [
            "kanji_n1.csv",
            "kanji_n2.csv",
            "kanji_n3.csv",
            "kanji_n4.csv",
            "kanji_n5.csv",
        ]

    if args.screen:
        detected = _detect_screen_size()
        if detected:
            args.width, args.height = detected
            print("Using detected screen size: {}x{}".format(args.width, args.height))
        else:
            print(
                "Warning: Could not detect screen size; using {}x{}".format(
                    args.width, args.height
                )
            )

    generator = KanjiImageGenerator(image_width=args.width, image_height=args.height)

    for input_file in input_files:
        if not os.path.exists(input_file):
            print("Error: Input file not found: {}".format(input_file))
            if args.csv:
                return
            continue

        print("\n=== Processing: {} ===".format(input_file))
        print("Parsing kanji CSV data...")
        kanji_list = parse_kanji_csv_file(input_file, parser=generator)

        if not kanji_list:
            print("No valid kanji data found in the CSV file.")
            continue

        print("Found {} kanji entries.".format(len(kanji_list)))

        # Determine output directory based on input
        # pattern: kanji_xxx.csv -> JLPT-XXX
        input_basename = os.path.splitext(os.path.basename(input_file))[0]

        # Find first underscore and extract everything after it
        if "_" in input_basename:
            after_first_underscore = input_basename.split("_", 1)[1]
            # Convert to uppercase and replace remaining underscores with hyphens
            suffix = after_first_underscore.upper().replace("_", "-")
        else:
            # Fallback if no underscore found
            suffix = input_basename.upper()

        output_dir = "JLPT-{}".format(suffix)
        os.makedirs(output_dir, exist_ok=True)

        successful = 0
        failed = 0

        for i, kanji_data in enumerate(kanji_list):
            # Generate filename with zero-padding (5 digits like in N3)
            file_number = i + 1
            filename = "JLPT_{}_{:05d}.png".format(suffix, file_number)
            output_path = os.path.join(output_dir, filename)

            if generator.create_kanji_image(kanji_data, output_path):
                successful += 1
            else:
                failed += 1
                print(
                    "Failed to create image for kanji: {}".format(
                        kanji_data.get("kanji", "unknown")
                    )
                )

        print("\n=== Generation Complete ({}) ===".format(input_file))
        print("✓ Successfully created: {} images".format(successful))
        print("✗ Failed: {} images".format(failed))
        print("📁 Output directory: {}".format(output_dir))


if __name__ == "__main__":
    main()
