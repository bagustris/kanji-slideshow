#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JLPT N2 Kanji Image Generator
Processes kanji data from CSV file and creates wallpaper images in the same format as JLPT-N3 folder.

Input format expected (CSV file with header):
```
kanji,meaning,readings,compounds
腕,"arm, ability, talent",ワン; うで,"右腕 (うわん) = right arm; 手腕 (しゅわん) = ability; ..."
```
"""

from PIL import Image, ImageDraw, ImageFont
import csv
import re
import os
import sys

# Image configuration for PC wallpaper (1920x1080)
IMAGE_WIDTH = 1920
IMAGE_HEIGHT = 1080
BACKGROUND_COLOR = (0, 0, 0, 255)  # Black background with alpha
TEXT_COLOR = (255, 255, 255)  # White text
COMPOUND_BOX_COLOR = (20, 20, 20, 255)  # Slightly lighter black for subtle contrast
COMPOUND_TEXT_COLOR = (255, 255, 255)  # White text for compounds
COMPOUND_READING_COLOR = (255, 165, 0)  # Orange color for hiragana readings in compounds
ACCENT_COLOR = (100, 149, 237)  # Cornflower blue for section headers
KANJI_COLOR = (255, 255, 255)  # White for main kanji
STROKE_ORDER_COLOR = (128, 128, 128)  # Gray for stroke order info

class KanjiImageGenerator:
    def __init__(self):
        self.font_large = None
        self.font_medium = None
        self.font_small = None
        self._load_fonts()
    
    def _load_fonts(self):
        """Load suitable fonts for Japanese characters."""
        font_paths = [
            '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',  # Ubuntu/Debian
            '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',  # Alternative path
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',  # Fallback
            '/System/Library/Fonts/Hiragino Sans GB.ttc',  # macOS
            '/Windows/Fonts/msgothic.ttc',  # Windows
        ]
        
        # Try to load fonts in different sizes - reduced for wallpaper use
        for font_path in font_paths:
            if os.path.exists(font_path):
                try:
                    self.font_large = ImageFont.truetype(font_path, 220)  # Smaller main kanji
                    self.font_medium = ImageFont.truetype(font_path, 32)  # Smaller meaning/readings
                    self.font_small = ImageFont.truetype(font_path, 24)   # Smaller compounds
                    self.font_jis = ImageFont.truetype(font_path, 16)     # Smaller JIS text
                    print(f"Successfully loaded font: {font_path}")
                    return
                except Exception as e:
                    print(f"Failed to load font {font_path}: {e}")
                    continue
        
        # Fallback to default font
        print("Warning: Using default font. Japanese characters may not display correctly.")
        try:
            self.font_large = ImageFont.load_default()
            self.font_medium = ImageFont.load_default()
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
        kanji = row['kanji'].strip()
        meaning = row['meaning'].strip()
        readings_str = row['readings'].strip()
        compounds_str = row['compounds'].strip()
        
        # Parse readings - separate hiragana and katakana
        hiragana_readings = []
        katakana_readings = []
        
        if readings_str:
            # Split by semicolon and comma
            reading_parts = []
            for part in readings_str.split(';'):
                reading_parts.extend([p.strip() for p in part.split(',') if p.strip()])
            
            for reading in reading_parts:
                reading = reading.strip()
                if reading:
                    # Check if it's hiragana or katakana
                    if re.match(r'^[\u3040-\u309F\s・.,ー]+$', reading):  # Hiragana
                        hiragana_readings.append(reading)
                    elif re.match(r'^[\u30A0-\u30FF\s・,ー]+$', reading):  # Katakana
                        katakana_readings.append(reading)
                    else:
                        # Mixed or other - try to separate
                        hiragana_part = re.findall(r'[\u3040-\u309F・.,ー]+', reading)
                        katakana_part = re.findall(r'[\u30A0-\u30FF・,ー]+', reading)
                        if hiragana_part:
                            hiragana_readings.extend(hiragana_part)
                        if katakana_part:
                            katakana_readings.extend(katakana_part)
        
        # Parse compounds - format: "右腕 (うわん) = right arm; 手腕 (しゅわん) = ability; ..."
        compounds = []
        if compounds_str:
            # Split by semicolon first
            compound_parts = [part.strip() for part in compounds_str.split(';') if part.strip()]
            
            for compound_part in compound_parts:
                # Match pattern: "kanji (reading) = meaning"
                match = re.match(r'([^\s(]+)\s*\(([^)]+)\)\s*=\s*(.+)', compound_part.strip())
                if match:
                    compounds.append({
                        'kanji': match.group(1).strip(),
                        'reading': match.group(2).strip(), 
                        'meaning': match.group(3).strip()
                    })
        
        return {
            'kanji': kanji,
            'meaning': meaning,
            'hiragana_readings': hiragana_readings,
            'katakana_readings': katakana_readings,
            'compounds': compounds
        }

    def create_kanji_image(self, kanji_data, output_path):
        """
        Create a kanji wallpaper image with the specified layout.
        
        Args:
            kanji_data (dict): Parsed kanji data
            output_path (str): Path to save the image
        """
        if not kanji_data or not kanji_data.get('kanji'):
            print(f"Warning: Invalid kanji data for {output_path}")
            return False
            
        # Create image
        image = Image.new('RGBA', (IMAGE_WIDTH, IMAGE_HEIGHT), BACKGROUND_COLOR)
        draw = ImageDraw.Draw(image)
        
        kanji = kanji_data['kanji']
        
        # --- Text Positioning ---
        x_margin = 80
        # Center content vertically on the 1920x1080 canvas
        # Estimate total content height and center it
        estimated_content_height = 400  # Approximate height of all content
        y_center_offset = (IMAGE_HEIGHT - estimated_content_height) // 2
        y_margin = max(50, y_center_offset)  # Ensure minimum margin
        vertical_spacing = 20  # Additional vertical space between elements
        
        # Left alignment for all text elements
        left_x = x_margin
        
        # Draw the main Kanji character (large, left side) - centered vertically
        kanji_y = y_margin + 30
        draw.text((left_x, kanji_y), kanji, font=self.font_large, fill=KANJI_COLOR)

        # Calculate position for right column (next to kanji with some spacing)
        right_x = left_x + 350  # Position right column next to kanji with more space
        right_y = y_margin
        
        # Draw JIS code at top-right corner - aligned with top (skip if not available)
        if kanji_data.get('jis_code') and kanji_data['jis_code'].strip():
            jis_text = kanji_data['jis_code']
            bbox = draw.textbbox((0, 0), jis_text, font=self.font_jis)
            jis_width = bbox[2] - bbox[0]
            jis_x = IMAGE_WIDTH - x_margin - jis_width
            draw.text((jis_x, right_y), jis_text, font=self.font_jis, fill=TEXT_COLOR)

        # Draw meaning - left-aligned in right column (no label)
        draw.text((right_x, right_y), kanji_data['meaning'], font=self.font_medium, fill=TEXT_COLOR)
        right_y += 45 + vertical_spacing

        # Draw katakana readings first (onyomi) - left-aligned with alternating colors
        if kanji_data.get('katakana_readings'):
            current_x = right_x
            for i, reading in enumerate(kanji_data['katakana_readings']):
                # Alternate between white and orange colors
                color = TEXT_COLOR if i % 2 == 0 else COMPOUND_READING_COLOR
                draw.text((current_x, right_y), reading, font=self.font_medium, fill=color)
                # Calculate width of this reading to position next one
                bbox = draw.textbbox((0, 0), reading, font=self.font_medium)
                current_x += bbox[2] - bbox[0] + 15  # Add spacing between readings
            right_y += 40 + vertical_spacing

        # Draw hiragana readings second (kunyomi) - left-aligned with alternating colors
        if kanji_data.get('hiragana_readings'):
            current_x = right_x
            for i, reading in enumerate(kanji_data['hiragana_readings']):
                # Alternate between white and orange colors
                color = TEXT_COLOR if i % 2 == 0 else COMPOUND_READING_COLOR
                draw.text((current_x, right_y), reading, font=self.font_medium, fill=color)
                # Calculate width of this reading to position next one
                bbox = draw.textbbox((0, 0), reading, font=self.font_medium)
                current_x += bbox[2] - bbox[0] + 15  # Add spacing between readings
            right_y += 40 + vertical_spacing

        # --- Compounds Box ---
        # Remove compounds label, start box directly
        box_padding = 15
        line_spacing = 30  # Fixed spacing between compound lines
        box_x0 = right_x - box_padding  # Left-aligned with other text
        box_y0 = right_y + vertical_spacing

        # Calculate available box width more conservatively to prevent overflow
        available_width = IMAGE_WIDTH - right_x - x_margin - 20  # Extra margin for safety
        max_box_width = available_width - (box_padding * 2)
        
        # Process compounds and handle text wrapping with colored components
        wrapped_compound_lines = []
        for compound in kanji_data['compounds']:
            # Store compound parts separately for colored rendering
            compound_parts = {
                'kanji': compound['kanji'],
                'reading': compound['reading'], 
                'meaning': compound['meaning']
            }
            
            # Calculate widths of each component
            kanji_bbox = draw.textbbox((0, 0), compound['kanji'], font=self.font_small)
            kanji_width = kanji_bbox[2] - kanji_bbox[0]
            
            reading_bbox = draw.textbbox((0, 0), compound['reading'], font=self.font_small)
            reading_width = reading_bbox[2] - reading_bbox[0]
            
            # Check if kanji + reading + some meaning fits on one line
            kanji_reading_width = kanji_width + 8 + reading_width + 12  # Including spacing
            available_for_meaning = max_box_width - kanji_reading_width
            
            # Try to fit as much meaning as possible on the first line
            meaning_words = compound['meaning'].split()
            first_line_meaning = ""
            remaining_meaning = ""
            
            for i, word in enumerate(meaning_words):
                test_meaning = first_line_meaning + (" " if first_line_meaning else "") + word
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
                first_line_meaning = compound['meaning']
                remaining_meaning = ""
            
            # Add the first line with kanji, reading, and partial meaning
            if first_line_meaning:
                wrapped_compound_lines.append({
                    'kanji': compound['kanji'],
                    'reading': compound['reading'],
                    'meaning': first_line_meaning
                })
            else:
                # Even first word doesn't fit, just put kanji and reading
                wrapped_compound_lines.append({
                    'kanji': compound['kanji'],
                    'reading': compound['reading'],
                    'meaning': ""
                })
                remaining_meaning = compound['meaning']
            
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
                            wrapped_compound_lines.append({
                                'kanji': '',
                                'reading': '',
                                'meaning': current_line
                            })
                        current_line = word
                
                # Add the last line
                if current_line:
                    wrapped_compound_lines.append({
                        'kanji': '',
                        'reading': '',
                        'meaning': current_line
                    })

        # Calculate box height based on actual wrapped lines + ensure bottom is visible
        if wrapped_compound_lines:
            # Reserve space at bottom of image to ensure box is fully visible
            max_available_height = IMAGE_HEIGHT - box_y0 - 30  # 30px from bottom edge
            ideal_content_height = len(wrapped_compound_lines) * line_spacing
            actual_content_height = min(ideal_content_height, max_available_height - (box_padding * 2))
            
            box_height = actual_content_height + (box_padding * 2)
            box_y1 = box_y0 + box_height
        else:
            box_y1 = box_y0 + (box_padding * 2) + 30  # Minimum height for empty box

        # Define the box dimensions
        box_x1 = IMAGE_WIDTH - x_margin

        # Draw the filled rectangle with visible borders
        draw.rectangle([box_x0, box_y0, box_x1, box_y1], fill=COMPOUND_BOX_COLOR, outline=TEXT_COLOR, width=2)

        # Now draw the wrapped compound text with colored components
        if wrapped_compound_lines:
            compound_y = box_y0 + box_padding
            for line_parts in wrapped_compound_lines:
                current_x = right_x
                
                # Handle different line types
                if line_parts['kanji'] and line_parts['reading'] and line_parts['meaning']:
                    # Full compound line with all parts - no brackets or equals sign
                    # Draw kanji part (white)
                    draw.text((current_x, compound_y), line_parts['kanji'], font=self.font_small, fill=COMPOUND_TEXT_COLOR)
                    kanji_bbox = draw.textbbox((0, 0), line_parts['kanji'], font=self.font_small)
                    current_x += kanji_bbox[2] - kanji_bbox[0] + 8  # Add spacing
                    
                    # Draw reading part (orange) - no brackets
                    draw.text((current_x, compound_y), line_parts['reading'], font=self.font_small, fill=COMPOUND_READING_COLOR)
                    reading_bbox = draw.textbbox((0, 0), line_parts['reading'], font=self.font_small)
                    current_x += reading_bbox[2] - reading_bbox[0] + 12  # Add more spacing before meaning
                    
                    # Draw meaning part (white) - no equals sign
                    draw.text((current_x, compound_y), line_parts['meaning'], font=self.font_small, fill=COMPOUND_TEXT_COLOR)
                    
                elif line_parts['meaning']:
                    # Continuation line with just meaning (or overflow text)
                    draw.text((current_x, compound_y), line_parts['meaning'], font=self.font_small, fill=COMPOUND_TEXT_COLOR)
                
                compound_y += line_spacing
                
                # Safety check: don't draw text outside the box
                if compound_y > box_y1 - box_padding:
                    break

        # Save the image
        try:
            image.save(output_path, 'PNG')
            print(f"✓ Created: {output_path}")
            return True
        except Exception as e:
            print(f"✗ Error saving {output_path}: {e}")
            return False

def parse_kanji_csv_file(file_path):
    """
    Parse the CSV file containing kanji data.
    
    Args:
        file_path (str): Path to the CSV file
        
    Returns:
        list: List of parsed kanji data dictionaries
    """
    if not os.path.exists(file_path):
        print(f"Error: File {file_path} not found.")
        return []
    
    parsed_kanji = []
    generator = KanjiImageGenerator()
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            for row_num, row in enumerate(reader, start=2):  # Start at 2 since header is row 1
                try:
                    kanji_data = generator.parse_csv_entry(row)
                    if kanji_data and kanji_data.get('kanji'):
                        parsed_kanji.append(kanji_data)
                    else:
                        print(f"Warning: Invalid kanji data at row {row_num}")
                except Exception as e:
                    print(f"Error parsing row {row_num}: {e}")
                    continue
                    
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        return []
    
    return parsed_kanji

def main():
    """Main function to generate N2 kanji images from CSV file."""
    
    if len(sys.argv) != 2:
        print("Usage: python3 generate_n2_kanji_images.py <kanji_csv_file>")
        print("\nExpected CSV format:")
        print("kanji,meaning,readings,compounds")
        print('腕,"arm, ability, talent",ワン; うで,"右腕 (うわん) = right arm; 手腕 (しゅわん) = ability; ..."')
        print("\nThe script will create images in the JLPT-N2 folder.")
        return
    
    input_file = sys.argv[1]
    
    print("Parsing kanji CSV data...")
    kanji_list = parse_kanji_csv_file(input_file)
    
    if not kanji_list:
        print("No valid kanji data found in the CSV file.")
        return
    
    print(f"Found {len(kanji_list)} kanji entries.")
    
    # Create output directory
    # Determine output directory based on input
    # pattern: kanji_xxx.csv -> JLPT-XXX
    input_basename = os.path.splitext(os.path.basename(input_file))[0]
    
    # Find first underscore and extract everything after it
    if '_' in input_basename:
        after_first_underscore = input_basename.split('_', 1)[1]
        # Convert to uppercase and replace remaining underscores with hyphens
        suffix = after_first_underscore.upper().replace('_', '-')
        output_dir = f"JLPT-{suffix}"
    else:
        # Fallback if no underscore found
        output_dir = f"JLPT-{input_basename.upper()}"
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate images
    generator = KanjiImageGenerator()
    successful = 0
    failed = 0
    
    for i, kanji_data in enumerate(kanji_list):
        # Generate filename with zero-padding (5 digits like in N3)
        file_number = i + 1
        filename = f"JLPT_N2_{file_number:05d}.png"
        output_path = os.path.join(output_dir, filename)
        
        if generator.create_kanji_image(kanji_data, output_path):
            successful += 1
        else:
            failed += 1
            print(f"Failed to create image for kanji: {kanji_data.get('kanji', 'unknown')}")
    
    print(f"\n=== Generation Complete ===")
    print(f"✓ Successfully created: {successful} images")
    print(f"✗ Failed: {failed} images")
    print(f"📁 Output directory: {output_dir}")

if __name__ == "__main__":
    main()
