import pdfplumber
import re
import os
from PIL import Image

OPTION_PATTERN = re.compile(r"\(\s*[A-D]\s*\)")   # Detects (A) (B) (C) (D)

def intersects(a, b):
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])

def merge(bboxes):
    return (
        min(b[0] for b in bboxes),
        min(b[1] for b in bboxes),
        max(b[2] for b in bboxes),
        max(b[3] for b in bboxes),
    )

def extract_question_blocks(pdf_path, temp_dir="images"):
    os.makedirs(temp_dir, exist_ok=True)

    questions = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_index, page in enumerate(pdf.pages, start=1):
            text_lines = page.extract_text().split("\n")
            char_lines = page.chars

            # Detect question numbers like "1."
            q_positions = []
            for i, line in enumerate(text_lines):
                m = re.match(r"^\s*(\d+)\.", line)
                if m:
                    q_positions.append((i, int(m.group(1))))

            for i in range(len(q_positions)):
                start_i, qnum = q_positions[i]
                end_i = q_positions[i+1][0] if i+1 < len(q_positions) else len(text_lines)

                block_text = "\n".join(text_lines[start_i:end_i])

                # detect location of block in page
                block_chars = [c for c in char_lines if start_i <= int(c["top"] / 12) < end_i]
                if not block_chars:
                    continue
                bbox = merge([(c["x0"], c["top"], c["x1"], c["bottom"]) for c in block_chars])

                imgs = []
                for idx, im in enumerate(page.images):
                    ib = (im["x0"], im["top"], im["x1"], im["bottom"])
                    if intersects(bbox, ib):
                        try:
                            cropped = page.within_bbox(ib).to_image(resolution=200).original
                            fp = f"{temp_dir}/q{qnum}_p{page_index}_{idx}.png"
                            cropped.save(fp)
                            imgs.append(fp)
                        except:
                            pass

                questions.append({
                    "number": qnum,
                    "text": block_text,
                    "images": imgs
                })

    return questions
