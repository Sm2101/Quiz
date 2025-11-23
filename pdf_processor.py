import pdfplumber
import pytesseract
from PIL import Image
import re
import io

# Set Tesseract path
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

QUESTION_PATTERN = re.compile(r'^\s*(Q?\s*\d+[\.\)])', re.IGNORECASE)

def merge_bbox(bboxes):
    """Merge multiple bounding boxes into one bounding box (x0,y0,x1,y1)."""
    x0 = min(b[0] for b in bboxes)
    y0 = min(b[1] for b in bboxes)
    x1 = max(b[2] for b in bboxes)
    y1 = max(b[3] for b in bboxes)
    return (x0, y0, x1, y1)

def bbox_intersects(b1, b2):
    """Check if two bounding boxes overlap."""
    x0, y0, x1, y1 = b1
    a0, b0, a1, b1_ = b2
    return not (x1 < a0 or x0 > a1 or y1 < b0 or y0 > b1_)

def crop_image_from_page(page, bbox):
    """Crop a region of the PDF page into a PIL image."""
    try:
        clipped = page.within_bbox(bbox)
        img = clipped.to_image(resolution=200).original
        return img
    except:
        return None

def extract_questions_with_images(pdf_path):
    """
    Extract:
    - Full question text (multi-line)
    - Options (A–D)
    - Numerical type (no options)
    - Cropped images belonging to each question
    """

    results = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            words = page.extract_words(x_tolerance=3, y_tolerance=3)
            images = page.images  # all image objects in the page

            question_blocks = []
            current_block = {"lines": [], "bboxes": []}

            # Build question blocks from detected text lines
            for w in words:
                text = w["text"]
                bbox = (w["x0"], w["top"], w["x1"], w["bottom"])

                # If this line starts a new question → close previous block
                if QUESTION_PATTERN.match(text):
                    if current_block["lines"]:
                        question_blocks.append(current_block)
                    current_block = {"lines": [], "bboxes": []}

                current_block["lines"].append(text)
                current_block["bboxes"].append(bbox)

            # Add last block
            if current_block["lines"]:
                question_blocks.append(current_block)

            # Match images to each question block
            for qb in question_blocks:
                q_bbox = merge_bbox(qb["bboxes"])
                q_text = " ".join(qb["lines"])

                # Crop only images that overlap with question
                figures = []
                for img in images:
                    img_bbox = (img["x0"], img["y0"], img["x1"], img["y1"])

                    if bbox_intersects(q_bbox, img_bbox):
                        cropped = crop_image_from_page(page, img_bbox)
                        if cropped:
                            figures.append(cropped)

                # MCQ option detection
                options = []
                opt_matches = re.findall(
                    r'\(([A-D])\)\s*([^\(]+?)(?=\([A-D]\)|$)',
                    q_text,
                    re.IGNORECASE
                )

                if opt_matches:
                    options = [o[1].strip() for o in opt_matches]

                q_type = "MCQ" if options else "NUMERIC"

                results.append({
                    "question": q_text.strip(),
                    "options": options,
                    "type": q_type,
                    "figures": figures
                })

    return results
