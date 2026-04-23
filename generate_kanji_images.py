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
import math
import os
import re
import sys
import argparse

# ---------------------------------------------------------------------------
# Pitch-accent helpers
# ---------------------------------------------------------------------------

# Small kana that attach to the preceding character to form a single mora
# (e.g. き + ょ → "きょ")
_COMBINING_SMALL_KANA = frozenset("ゃゅょぁぃぅぇぉゎャュョァィゥェォヮ")


def split_into_morae(text):
    """Split kana text into mora units, grouping digraphs such as きょ."""
    morae = []
    i = 0
    while i < len(text):
        if i + 1 < len(text) and text[i + 1] in _COMBINING_SMALL_KANA:
            morae.append(text[i] + text[i + 1])
            i += 2
        else:
            morae.append(text[i])
            i += 1
    return morae


def pitch_pattern(n_morae, accent):
    """Return a list of bool (True = HIGH pitch) for each mora.

    accent 0  – heiban:    mora 1 LOW,  morae 2..n HIGH,  no drop
    accent 1  – atamadaka: mora 1 HIGH, morae 2..n LOW
    accent N  – (naka/odaka): mora 1 LOW, morae 2..N HIGH, morae N+1.. LOW
    """
    result = []
    for k in range(1, n_morae + 1):
        if accent == 0:
            high = k > 1
        elif accent == 1:
            high = k == 1
        else:
            high = 2 <= k <= accent
        result.append(high)
    return result

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
ACCENT_COLOR = (80, 200, 255)  # Bright blue
PITCH_ACCENT_COLOR = (255, 210, 60)  # Yellow-gold for pitch accent number
HIGHLIGHT_COLOR = (80, 200, 255)  # Bright blue for target kanji in compounds
KANJI_COLOR = (255, 255, 255)  # White for main kanji
STROKE_ORDER_COLOR = (128, 128, 128)  # Gray for stroke order info
READING_BG_COLOR = (45, 45, 45, 255)  # Subtle background for readings
KUN_LABEL_COLOR = (140, 210, 80)  # Green for kun'yomi label
ON_LABEL_COLOR = KUN_LABEL_COLOR  # Same green as kun'yomi label

MAX_KUN_READINGS = 8  # Cap kun'yomi pills to avoid multi-line overflow


class KanjiImageGenerator:
    def __init__(self, image_width=BASE_IMAGE_WIDTH, image_height=BASE_IMAGE_HEIGHT,
                 show_pitch_accent=False):
        self.image_width = int(image_width)
        self.image_height = int(image_height)
        self.show_pitch_accent = show_pitch_accent
        self.scale = min(
            self.image_width / float(BASE_IMAGE_WIDTH),
            self.image_height / float(BASE_IMAGE_HEIGHT),
        )
        self.font_large = None
        self.font_medium = None
        self.font_meaning = None
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
                    )  # Main kanji
                    self.font_meaning = ImageFont.truetype(
                        font_path, self._s(52, minimum=18)
                    )  # Meaning (prominent)
                    self.font_medium = ImageFont.truetype(
                        font_path, self._s(42, minimum=15)
                    )  # Readings / badge
                    self.font_reading = ImageFont.truetype(
                        font_path, self._s(42, minimum=15)
                    )  # Reading pills
                    self.font_small = ImageFont.truetype(
                        font_path, self._s(42, minimum=15)
                    )  # Compounds
                    self.font_label = ImageFont.truetype(
                        font_path, self._s(30, minimum=11)
                    )  # ON/KUN section labels
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
            self.font_meaning = ImageFont.load_default()
            self.font_medium = ImageFont.load_default()
            self.font_reading = ImageFont.load_default()
            self.font_small = ImageFont.load_default()
            self.font_label = ImageFont.load_default()
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

        # Deduplicate while preserving order
        hiragana_readings = list(dict.fromkeys(hiragana_readings))
        katakana_readings = list(dict.fromkeys(katakana_readings))

        # Cap kun'yomi to avoid overwhelming the layout
        if len(hiragana_readings) > MAX_KUN_READINGS:
            hiragana_readings = hiragana_readings[:MAX_KUN_READINGS]

        # Parse compounds - format: "右腕 (うわん) = right arm; 手腕 (しゅわん) = ability; ..."
        compounds = []
        if compounds_str:
            # Split by semicolon first
            compound_parts = [
                part.strip() for part in compounds_str.split(";") if part.strip()
            ]

            for compound_part in compound_parts:
                # Match pattern: "kanji (reading[·accent]) = meaning"
                match = re.match(
                    r"([^\s(]+)\s*\(([^)·]+)(?:·([^)]*))?\)\s*=\s*(.+)",
                    compound_part.strip(),
                )
                if match:
                    compound_kanji = match.group(1).strip()
                    # Skip entries that are just the learned kanji alone
                    if compound_kanji == kanji:
                        continue
                    compounds.append(
                        {
                            "kanji": compound_kanji,
                            "reading": match.group(2).strip(),
                            "pitch_accent": match.group(3).strip() if match.group(3) else None,
                            "meaning": match.group(4).strip(),
                        }
                    )

        # Optional enrichment fields (added by enrich_kanji_csv.py)
        sentence    = row.get("sentence", "").strip()    if "sentence"    in row else ""
        translation = row.get("translation", "").strip() if "translation" in row else ""
        radicals    = row.get("radicals", "").strip()    if "radicals"    in row else ""
        confusables = row.get("confusables", "").strip() if "confusables" in row else ""

        return {
            "kanji": kanji,
            "meaning": meaning,
            "hiragana_readings": hiragana_readings,
            "katakana_readings": katakana_readings,
            "compounds": compounds,
            "sentence": sentence,
            "translation": translation,
            "radicals": radicals.split() if radicals else [],
            "confusables": [c for c in confusables.split(",") if c] if confusables else [],
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

    def _truncate_text(self, text, font, max_width, draw):
        """Truncate text to fit max_width by removing comma-separated segments or using ellipsis."""
        if not text:
            return ""

        # Initial check
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return text

        # Try removing segments separated by commas
        parts = [p.strip() for p in text.split(",")]
        while len(parts) > 1:
            parts.pop()
            truncated = ", ".join(parts)
            if not truncated:
                break
            bbox = draw.textbbox((0, 0), truncated, font=font)
            if bbox[2] - bbox[0] <= max_width:
                return truncated

        # If still too long or no commas, hard truncate with ellipsis
        current_text = parts[0] if parts else text
        while len(current_text) > 0:
            test_text = current_text + "..."
            bbox = draw.textbbox((0, 0), test_text, font=font)
            if bbox[2] - bbox[0] <= max_width:
                return test_text
            current_text = current_text[:-1]

        return ""

    def _estimate_content_height(self, kanji_data):
        """Estimate the taller of the two columns to use for vertical centering."""
        line_h = self._s(55)
        label_h = self._s(36)
        vertical_spacing = self._s(20)

        # Left column: kanji glyph + optional radicals + optional confusables
        left_h = self._s(320)  # main kanji glyph
        if kanji_data.get("radicals"):
            left_h += vertical_spacing + label_h + line_h
        if kanji_data.get("confusables"):
            left_h += vertical_spacing + label_h + line_h

        # Right column: meaning + readings + compounds + sentence
        right_h = self._s(62) + vertical_spacing  # meaning line

        if kanji_data.get("katakana_readings"):
            right_h += label_h + line_h + vertical_spacing

        if kanji_data.get("hiragana_readings"):
            right_h += label_h
            n_kun = len(kanji_data["hiragana_readings"])
            rows = math.ceil(n_kun / 6)
            right_h += rows * line_h + vertical_spacing

        n_cmp = len(kanji_data.get("compounds", []))
        if n_cmp:
            box_padding = self._s(15)
            right_h += vertical_spacing + box_padding * 2 + n_cmp * line_h

        if kanji_data.get("sentence"):
            right_h += vertical_spacing + label_h + line_h  # label + sentence
            if kanji_data.get("translation"):
                right_h += self._s(36) + vertical_spacing

        return max(left_h, right_h)

    def create_kanji_image(self, kanji_data, output_path, jlpt_level=None):
        """
        Create a kanji wallpaper image with the specified layout.

        Args:
            kanji_data (dict): Parsed kanji data
            output_path (str): Path to save the image
            jlpt_level (str): JLPT level string e.g. "N5" for badge display
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

        def _to_hiragana(s):
            return "".join(
                chr(ord(c) - 0x60) if 0x30A1 <= ord(c) <= 0x30F6 else c for c in s
            )

        for r in all_raw_readings:
            parts = re.split(r"[.・]", r)
            stem = parts[0].strip()
            if not stem:
                continue
            # Add stem (reading without okurigana)
            target_readings.append(_to_hiragana(stem))
            # Also add full form (dot removed) so e.g. "な.す" → "なす" matches compound readings
            if len(parts) > 1:
                full_form = "".join(p.strip() for p in parts)
                if full_form:
                    target_readings.append(_to_hiragana(full_form))
        # Sort by length descending to match longest possible reading first
        target_readings = sorted(list(set(target_readings)), key=len, reverse=True)

        # --- Vertical centering ---
        x_margin = self._s(80)
        vertical_spacing = self._s(20)
        content_height = self._estimate_content_height(kanji_data)
        y_margin = max(self._s(40), (self.image_height - content_height) // 2)

        # Left alignment for all text elements
        left_x = x_margin

        # Draw the main Kanji character (large, left side) - vertically centered with content
        kanji_y = y_margin
        draw.text((left_x, kanji_y), kanji, font=self.font_large, fill=KANJI_COLOR)
        kanji_bbox = draw.textbbox((left_x, kanji_y), kanji, font=self.font_large)
        kanji_bottom = kanji_bbox[3]

        # Calculate position for right column (next to kanji with some spacing)
        right_x = left_x + self._s(350)
        right_y = y_margin

        # --- Left column: radicals and confusables below the main kanji ---
        left_y = kanji_bottom + vertical_spacing * 2

        if kanji_data.get("radicals"):
            draw.text((left_x, left_y), "部首 (Radicals)", font=self.font_label, fill=KUN_LABEL_COLOR)
            lbl_bbox = draw.textbbox((0, 0), "部首 (Radicals)", font=self.font_label)
            left_y += (lbl_bbox[3] - lbl_bbox[1]) + self._s(4)
            rad_x = left_x
            max_left_x = right_x - self._s(10)
            for rad in kanji_data["radicals"]:
                b = draw.textbbox((0, 0), rad, font=self.font_small)
                char_w = b[2] - b[0]
                if rad_x + char_w > max_left_x and rad_x != left_x:
                    left_y += self._s(55)
                    rad_x = left_x
                draw.text((rad_x, left_y), rad, font=self.font_small, fill=HIGHLIGHT_COLOR)
                rad_x += char_w + self._s(8)
            left_y += self._s(55) + vertical_spacing

        if kanji_data.get("confusables"):
            draw.text((left_x, left_y), "混同 (Confuse)", font=self.font_label, fill=(220, 80, 80))
            lbl_bbox = draw.textbbox((0, 0), "混同 (Confuse)", font=self.font_label)
            left_y += (lbl_bbox[3] - lbl_bbox[1]) + self._s(4)
            conf_x = left_x
            for conf in kanji_data["confusables"]:
                draw.text((conf_x, left_y), conf, font=self.font_small, fill=COMPOUND_READING_COLOR)
                b = draw.textbbox((0, 0), conf, font=self.font_small)
                conf_x += b[2] - b[0] + self._s(16)

        # Draw JIS code (skip if not available)
        if kanji_data.get("jis_code") and kanji_data["jis_code"].strip():
            jis_text = kanji_data["jis_code"]
            bbox = draw.textbbox((0, 0), jis_text, font=self.font_jis)
            jis_width = bbox[2] - bbox[0]
            jis_x = self.image_width - x_margin - jis_width
            draw.text((jis_x, right_y), jis_text, font=self.font_jis, fill=TEXT_COLOR)

        # Draw meaning - prominent, white
        max_meaning_width = self.image_width - right_x - x_margin
        truncated_meaning = self._truncate_text(
            kanji_data["meaning"], self.font_meaning, max_meaning_width, draw
        )
        draw.text(
            (right_x, right_y),
            truncated_meaning,
            font=self.font_meaning,
            fill=TEXT_COLOR,
        )
        right_y += self._s(62) + vertical_spacing

        pill_padding_x = self._s(6)
        pill_padding_y = self._s(4)
        pill_gap = self._s(16)
        max_reading_x = self.image_width - x_margin
        reading_line_step = self._s(55)

        def _draw_text_background(x, y, text_width, text_bbox, padding_x, padding_y):
            """Draw a padded background behind text drawn at (x, y)."""
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

                    # Before dot: orange (the kanji reading); after dot: cornflower blue (okurigana)
                    draw.text(
                        (current_x, y),
                        parts[0],
                        font=self.font_reading,
                        fill=COMPOUND_READING_COLOR,
                    )
                    draw.text(
                        (current_x + width_before, y),
                        parts[1],
                        font=self.font_reading,
                        fill=ACCENT_COLOR,
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
                        fill=COMPOUND_READING_COLOR,
                    )
                    current_x += pill_total_width + pill_gap

            return y + reading_line_step + vertical_spacing

        def _draw_section_label(label, y, color):
            """Draw a small ON/KUN section label and return updated y."""
            draw.text((right_x, y), label, font=self.font_label, fill=color)
            bbox = draw.textbbox((0, 0), label, font=self.font_label)
            return y + (bbox[3] - bbox[1]) + self._s(4)

        def _draw_pitch_lines(mora_positions, is_high, y):
            """Draw pitch-accent contour (overline + downstep) above compound reading."""
            if not mora_positions or not any(is_high):
                return
            # Use textbbox to find actual glyph top relative to draw origin
            ref_bb = draw.textbbox((0, 0), "あ", font=self.font_small)
            line_y = y + ref_bb[1] - self._s(5)   # 5 px above character top
            drop_h = self._s(9)
            lw = max(1, self._s(2))
            n = len(mora_positions)
            i = 0
            while i < n:
                if is_high[i]:
                    # extend the HIGH run
                    j = i + 1
                    while j < n and is_high[j]:
                        j += 1
                    x0 = mora_positions[i][0]
                    x1 = mora_positions[j - 1][0] + mora_positions[j - 1][1]
                    draw.line(
                        [(x0, line_y), (x1, line_y)],
                        fill=PITCH_ACCENT_COLOR,
                        width=lw,
                    )
                    if j < n:  # downstep into next (LOW) mora
                        draw.line(
                            [(x1, line_y), (x1, line_y + drop_h)],
                            fill=PITCH_ACCENT_COLOR,
                            width=lw,
                        )
                    i = j
                else:
                    i += 1

        # Draw on'yomi (katakana) with label
        if kanji_data.get("katakana_readings"):
            right_y = _draw_section_label("音読み (On'yomi)", right_y, ON_LABEL_COLOR)
            right_y = _draw_readings(kanji_data["katakana_readings"], right_y)

        # Draw kun'yomi (hiragana) with label
        if kanji_data.get("hiragana_readings"):
            right_y = _draw_section_label("訓読み (Kun'yomi)", right_y, KUN_LABEL_COLOR)
            right_y = _draw_readings(kanji_data["hiragana_readings"], right_y)

        # --- Compounds Box ---
        box_padding = self._s(15)
        line_spacing = self._s(55)
        box_x0 = right_x - box_padding
        box_y0 = right_y + vertical_spacing

        available_width = self.image_width - right_x - x_margin - self._s(20)
        max_box_width = available_width - (box_padding * 2)

        # Process compounds with truncation
        processed_compounds = []
        for compound in kanji_data["compounds"]:
            kanji_bbox = draw.textbbox((0, 0), compound["kanji"], font=self.font_small)
            kanji_width = kanji_bbox[2] - kanji_bbox[0]
            reading_bbox = draw.textbbox(
                (0, 0), compound["reading"], font=self.font_small
            )
            reading_width = reading_bbox[2] - reading_bbox[0]

            accent_text = "·" + compound["pitch_accent"] if compound.get("pitch_accent") else ""
            accent_width = 0
            if accent_text:
                ab = draw.textbbox((0, 0), accent_text, font=self.font_small)
                accent_width = ab[2] - ab[0]

            extra_width = (
                kanji_width
                + self._s(8)
                + self._s(20)
                + reading_width
                + accent_width
                + self._s(24)
            )
            available_for_meaning = max_box_width - extra_width

            truncated_meaning = self._truncate_text(
                compound["meaning"], self.font_small, available_for_meaning, draw
            )

            processed_compounds.append(
                {
                    "kanji": compound["kanji"],
                    "reading": compound["reading"],
                    "pitch_accent": compound.get("pitch_accent"),
                    "meaning": truncated_meaning,
                }
            )

        # Calculate box height
        if processed_compounds:
            max_available_height = self.image_height - box_y0 - self._s(30)
            ideal_content_height = len(processed_compounds) * line_spacing
            actual_content_height = min(
                ideal_content_height, max_available_height - (box_padding * 2)
            )
            box_height = actual_content_height + (box_padding * 2)
            box_y1 = box_y0 + box_height
        else:
            box_y1 = box_y0 + (box_padding * 2) + 30

        box_x1 = self.image_width - x_margin

        draw.rectangle(
            (box_x0, box_y0, box_x1, box_y1),
            fill=COMPOUND_BOX_COLOR,
            outline=TEXT_COLOR,
            width=2,
        )

        # Draw compound text with colored components
        if processed_compounds:
            compound_y = box_y0 + box_padding
            for compound in processed_compounds:
                current_x = right_x

                # 1. Kanji part: target kanji in orange, others in cornflower blue
                target_kanji = kanji_data["kanji"]
                for char in compound["kanji"]:
                    char_color = (
                        COMPOUND_READING_COLOR
                        if char == target_kanji
                        else ACCENT_COLOR
                    )
                    draw.text(
                        (current_x, compound_y),
                        char,
                        font=self.font_small,
                        fill=char_color,
                    )
                    char_bbox = draw.textbbox((0, 0), char, font=self.font_small)
                    current_x += char_bbox[2] - char_bbox[0]
                current_x += self._s(8)

                # 2. Reading part
                reading_text = compound["reading"]

                draw.text(
                    (current_x, compound_y),
                    "(",
                    font=self.font_small,
                    fill=COMPOUND_TEXT_COLOR,
                )
                bbox = draw.textbbox((0, 0), "(", font=self.font_small)
                current_x += bbox[2] - bbox[0]

                # Pre-compute mora positions for pitch-accent line drawing.
                # Done here (before text is painted) so we know each mora's x offset.
                _morae = split_into_morae(reading_text)
                _mora_pos = []
                _mx = current_x
                for _m in _morae:
                    _mb = draw.textbbox((0, 0), _m, font=self.font_small)
                    _mw = _mb[2] - _mb[0]
                    _mora_pos.append((_mx, _mw))
                    _mx += _mw

                # Highlight target readings in blue, others in white
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
                            idx < e and idx + len(tr) > s for s, e in reading_matches
                        ):
                            reading_matches.append((idx, idx + len(tr)))
                        start_search = idx + 1
                reading_matches.sort()

                last_idx = 0
                for start, end in reading_matches:
                    if start > last_idx:
                        seg = reading_text[last_idx:start]
                        draw.text(
                            (current_x, compound_y),
                            seg,
                            font=self.font_small,
                            fill=ACCENT_COLOR,  # other reading: cornflower blue
                        )
                        bbox = draw.textbbox((0, 0), seg, font=self.font_small)
                        current_x += bbox[2] - bbox[0]

                    seg = reading_text[start:end]
                    draw.text(
                        (current_x, compound_y),
                        seg,
                        font=self.font_small,
                        fill=COMPOUND_READING_COLOR,  # target reading: orange
                    )
                    bbox = draw.textbbox((0, 0), seg, font=self.font_small)
                    current_x += bbox[2] - bbox[0]
                    last_idx = end

                if last_idx < len(reading_text):
                    seg = reading_text[last_idx:]
                    draw.text(
                        (current_x, compound_y),
                        seg,
                        font=self.font_small,
                        fill=ACCENT_COLOR,  # other reading: cornflower blue
                    )
                    bbox = draw.textbbox((0, 0), seg, font=self.font_small)
                    current_x += bbox[2] - bbox[0]

                # Draw pitch-accent overline + downstep above the reading
                if self.show_pitch_accent and compound.get("pitch_accent") and _mora_pos:
                    try:
                        _acc = int(compound["pitch_accent"].split(",")[0].strip())
                        _draw_pitch_lines(
                            _mora_pos,
                            pitch_pattern(len(_morae), _acc),
                            compound_y,
                        )
                    except (ValueError, IndexError):
                        pass

                # Pitch accent marker (yellow-gold), e.g. "·2"
                if compound.get("pitch_accent"):
                    accent_text = "·" + compound["pitch_accent"]
                    draw.text(
                        (current_x, compound_y),
                        accent_text,
                        font=self.font_small,
                        fill=PITCH_ACCENT_COLOR,
                    )
                    bbox = draw.textbbox((0, 0), accent_text, font=self.font_small)
                    current_x += bbox[2] - bbox[0]

                draw.text(
                    (current_x, compound_y),
                    ")",
                    font=self.font_small,
                    fill=COMPOUND_TEXT_COLOR,
                )
                bbox = draw.textbbox((0, 0), ")", font=self.font_small)
                current_x += bbox[2] - bbox[0]
                current_x += self._s(24)

                # 3. Meaning in white
                draw.text(
                    (current_x, compound_y),
                    compound["meaning"],
                    font=self.font_small,
                    fill=COMPOUND_TEXT_COLOR,
                )

                compound_y += line_spacing
                if compound_y > box_y1 - box_padding:
                    break

        # --- Bottom of right column: example sentence ---
        if kanji_data.get("sentence"):
            right_y = box_y1 + vertical_spacing * 2
            right_y = _draw_section_label("例文 (Example)", right_y, KUN_LABEL_COLOR)
            sentence_text = kanji_data["sentence"]
            draw.text((right_x, right_y), sentence_text, font=self.font_small, fill=TEXT_COLOR)
            right_y += self._s(50)
            if kanji_data.get("translation"):
                trans = self._truncate_text(
                    kanji_data["translation"], self.font_label,
                    self.image_width - right_x - x_margin, draw
                )
                draw.text((right_x, right_y), trans, font=self.font_label, fill=ACCENT_COLOR)

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
    parser.add_argument(
        "--pitch-accent",
        action="store_true",
        default=False,
        help="Draw pitch-accent overlines above compound readings (disabled by default).",
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

    generator = KanjiImageGenerator(
        image_width=args.width,
        image_height=args.height,
        show_pitch_accent=args.pitch_accent,
    )

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

        # Determine output directory and JLPT level from filename
        # pattern: kanji_xxx.csv -> JLPT-XXX
        input_basename = os.path.splitext(os.path.basename(input_file))[0]

        if "_" in input_basename:
            after_first_underscore = input_basename.split("_", 1)[1]
            suffix = after_first_underscore.upper().replace("_", "-")
        else:
            suffix = input_basename.upper()

        # Extract JLPT level for badge (e.g. "N5" from "N5" suffix)
        jlpt_level = suffix if re.match(r"^N\d$", suffix) else None

        output_dir = "JLPT-{}".format(suffix)
        os.makedirs(output_dir, exist_ok=True)

        successful = 0
        failed = 0

        for i, kanji_data in enumerate(kanji_list):
            file_number = i + 1
            filename = "JLPT_{}_{:05d}.png".format(suffix, file_number)
            output_path = os.path.join(output_dir, filename)

            if generator.create_kanji_image(kanji_data, output_path, jlpt_level=jlpt_level):
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
