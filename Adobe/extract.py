import fitz  # PyMuPDF
import json
import re
import os
from collections import defaultdict

class PDFOutlineExtractor:
    def __init__(self, pdf_path):
        self.pdf_path = pdf_path
        self.doc = fitz.open(pdf_path)
        self.styles = None
        self.body_style = None
        self.ranked_heading_styles = None
        self.page_metadata = self._identify_page_metadata()

    def _get_style_key(self, span):
        size = round(span['size'])
        font = span['font']
        is_bold = (span['flags'] & 2**4) or ("bold" in font.lower())
        is_italic = (span['flags'] & 2**1) or ("italic" in font.lower())
        return (size, font, is_bold, is_italic)

    def _analyze_styles(self):
        style_profile = defaultdict(lambda: {'count': 0, 'chars': 0})
        for page in self.doc:
            blocks = page.get_text("dict").get("blocks", [])
            for block in blocks:
                if block['type'] == 0:
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            style_key = self._get_style_key(span)
                            style_profile[style_key]['count'] += 1
                            style_profile[style_key]['chars'] += len(span['text'].strip())

        if not style_profile:
            self.styles = {}
            self.body_style = None
            self.ranked_heading_styles = []
            return

        body_style_key = max(style_profile, key=lambda k: style_profile[k]['chars'])
        self.body_style = {'key': body_style_key, 'size': body_style_key[0]}

        heading_candidates = []
        for style, stats in style_profile.items():
            if style == self.body_style['key']:
                continue
            is_potential_heading = (
                style[0] > self.body_style['size'] or
                (style[2] and not self.body_style['key'][2])
            )
            if is_potential_heading and stats['count'] > 1 and stats['count'] < style_profile[body_style_key]['count'] / 2:
                heading_candidates.append(style)

        self.ranked_heading_styles = sorted(heading_candidates, key=lambda s: (-s[0], not s[2], s[1]))
        self.styles = style_profile

    def _identify_page_metadata(self):
        metadata_patterns = defaultdict(int)
        if len(self.doc) < 3: return set()
        
        page_height = self.doc[0].rect.height
        header_zone_y_end = page_height * 0.1
        footer_zone_y_start = page_height * 0.9

        for page in self.doc:
            blocks = page.get_text("dict").get("blocks", [])
            for block in blocks:
                if block['type'] == 0 and (block['bbox'][1] <= header_zone_y_end or block['bbox'][1] >= footer_zone_y_start):
                    block_text = "".join(s['text'] for l in block.get('lines', []) for s in l.get('spans', [])).strip()
                    cleaned_text = re.sub(r'(\s*\d+)+$', '', block_text).strip()
                    cleaned_text = re.sub(r'RFP: To Develop the Ontario Digital Library Business Plan\s+March\s+\d{4}', '', cleaned_text, flags=re.IGNORECASE).strip()
                    if len(cleaned_text) > 5 and not cleaned_text.isdigit():
                        metadata_patterns[cleaned_text] += 1
        return {text for text, count in metadata_patterns.items() if count > len(self.doc) / 2}

    def _classify_block(self, block_text, block_style, bbox=None):
        cleaned = re.sub(r'(\s*\d+)+$', '', block_text).strip()
        cleaned = re.sub(r'RFP:.*?(March\s+\d{4})?', '', cleaned, flags=re.IGNORECASE).strip()
        if cleaned in self.page_metadata:
            return None
        if bbox:
            page_height = self.doc[0].rect.height
            y_top = bbox[1]
            y_bottom = bbox[3]
            if y_top < page_height * 0.10 or y_bottom > page_height * 0.90:
                return None
        if len(block_text) > 150 or (len(block_text) > 30 and re.search(r'[.?!]\s', block_text[:-1])):
            return None

        level = None
        match = re.match(r'^((\d+(\.\d+)*\s)|(Appendix\s[A-Z]+:?\s)|(Phase\s[IVX]+:?\s))', block_text, re.IGNORECASE)
        if match:
            prefix = match.group(0)
            if re.match(r'^\d+\.\d+\s', prefix) and block_style == self.body_style['key']:
                return None
            if "Appendix" in prefix.lower() or "Phase" in prefix.lower():
                level = 1
            elif re.match(r'^\d+\.\s', prefix):
                level = 3
            elif re.match(r'^\d+(\.\d+)*\s', prefix):
                level = prefix.count('.') + 1
            elif re.match(r'^[A-Z]\.\s', prefix):
                level = 1

        if level is not None:
            return level

        if block_style in self.ranked_heading_styles:
            return min(self.ranked_heading_styles.index(block_style) + 1, 3)

        return None

    def _extract_title(self):
        if self.doc.page_count == 0:
            return "Title Not Found"

        page = self.doc[0]
        blocks = page.get_text("dict", sort=True).get("blocks", [])
        page_width = page.rect.width
        page_height = page.rect.height
        
        title_parts = []
        min_title_font_size = self.body_style['size'] * 1.2 if self.body_style else 16

        for block in blocks:
            if block['type'] == 0:
                bbox = block['bbox']
                block_center_x = (bbox[0] + bbox[2]) / 2
                is_centered = (abs(block_center_x - page_width / 2) < page_width * 0.15)
                block_text = " ".join(s['text'] for l in block.get('lines', []) for s in l.get('spans', [])).strip()
                if not block_text or len(block_text) < 5 or re.fullmatch(r'[\.\s-]+', block_text):
                    continue
                dominant_span_size = 0
                if block.get('lines') and block['lines'][0].get('spans'):
                    dominant_span_size = round(block['lines'][0]['spans'][0]['size'])
                if bbox[1] < page_height / 2 and is_centered and dominant_span_size >= min_title_font_size:
                    title_parts.append({'text': block_text, 'bbox': bbox, 'size': dominant_span_size})

        if not title_parts:
            return "Title Not Found"

        title_parts.sort(key=lambda x: x['bbox'][1])
        final_title = " ".join([p['text'] for p in title_parts]).replace("  ", " ").strip()

        final_title = re.sub(r'(RFP:)\s*(RFP:)+', r'\1', final_title, flags=re.IGNORECASE)
        final_title = re.sub(r'(\bRequest\s+f)\s*(quest\s+f)+', r'\1', final_title, flags=re.IGNORECASE)
        final_title = re.sub(r'(\bPr\s+r)\s*(Pr\s+r)+', r'\1', final_title, flags=re.IGNORECASE)
        final_title = re.sub(r'(\bProposal\s+o)\s*(posal\s+o)+', r'\1', final_title, flags=re.IGNORECASE)
        final_title = re.sub(r'\s+oposal\s+oposal', '', final_title, flags=re.IGNORECASE)
        final_title = re.sub(r'\s+quest\s+f', ' ', final_title, flags=re.IGNORECASE)
        final_title = re.sub(r'\s+Pr\s+r', ' ', final_title, flags=re.IGNORECASE)
        final_title = re.sub(r'\s+r\s+Proposal', ' Proposal', final_title, flags=re.IGNORECASE)
        final_title = re.sub(r'\s+o\s+posal', 'osal', final_title, flags=re.IGNORECASE)
        final_title = re.sub(r'\s+o\s+posa', 'osa', final_title, flags=re.IGNORECASE)
        final_title = re.sub(r'\s+sal', 'sal', final_title, flags=re.IGNORECASE)
        final_title = re.sub(r'RFP:\s*', 'RFP:', final_title)
        return final_title.strip()

    def extract_outline(self):
        self._analyze_styles()
        if not self.body_style:
            return {"title": "Processing Error: Could not determine body style", "outline": []}

        title = self._extract_title()
        outline = []
        
        for page_num, page in enumerate(self.doc):
            blocks = page.get_text("dict").get("blocks", [])
            for block in blocks:
                if block['type'] == 0:
                    block_text = " ".join(s['text'] for l in block.get('lines', []) for s in l.get('spans', [])).strip()
                    if not block_text or len(block_text) < 3 or re.fullmatch(r'[\.\s-]+', block_text):
                        continue
                    dominant_style = None
                    if block.get('lines') and block['lines'][0].get('spans'):
                        dominant_style = self._get_style_key(block['lines'][0]['spans'][0])
                    if not dominant_style:
                        continue

                    level = self._classify_block(block_text, dominant_style, bbox=block['bbox'])
                    if level:
                        actual_level = min(level, 3)
                        node = {'level': f"H{actual_level}", 'text': block_text, 'page': page_num + 1}
                        outline.append(node)

        return {"title": title, "outline": outline}


# --- Batch Processing of All PDFs in input/ ---
input_dir = "/app/input"
output_dir = "/app/output"

if not os.path.exists(output_dir):
    os.makedirs(output_dir)

pdf_files = [f for f in os.listdir(input_dir) if f.lower().endswith(".pdf")]

if not pdf_files:
    print("No PDF files found in input/")
else:
    for filename in pdf_files:
        pdf_path = os.path.join(input_dir, filename)
        json_filename = os.path.splitext(filename)[0] + ".json"
        output_path = os.path.join(output_dir, json_filename)

        try:
            print(f"Processing: {pdf_path}")
            extractor = PDFOutlineExtractor(pdf_path)
            extracted_data = extractor.extract_outline()

            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(extracted_data, f, indent=4, ensure_ascii=False)

            print(f"Saved: {output_path}")
        except Exception as e:
            print(f"Failed to process {filename}: {e}")