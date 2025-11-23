# run_extract_and_answer.py
import os
import re
import pdfplumber
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import messagebox, filedialog

PDF_PATH = "/mnt/data/1.pdf"   # path to your uploaded PDF
TMP_IMG_DIR = os.path.join(os.getcwd(), "q_images")
os.makedirs(TMP_IMG_DIR, exist_ok=True)

QUESTION_NUM_RE = re.compile(r'^\s*(\d+)\s*[\.\)]')  # matches lines starting with "1." or "1)" etc.

# sensible list of substrings that indicate a bold font name in many PDFs
BOLD_HINTS = ["Bold", "BD", "Black", "Heavy", "bold", "BOLD", "Bd", "SemiBold"]


def is_font_bold(fontname: str) -> bool:
    if not fontname:
        return False
    for hint in BOLD_HINTS:
        if hint in fontname:
            return True
    return False


def group_chars_to_lines(page):
    """
    Returns list of lines: each line is dict { 'text':..., 'chars': [char dicts], 'bbox': (x0,top,x1,bottom) }
    char dicts are pdfplumber char dicts with keys: text, x0, x1, top, bottom, fontname, size
    """
    chars = page.chars  # list of character dicts
    if not chars:
        return []

    # Group by rounded top coordinate to form lines
    lines_map = {}
    for ch in chars:
        top_key = int(round(ch["top"]))  # grouping
        lines_map.setdefault(top_key, []).append(ch)

    # Sort lines by vertical position (top ascending)
    sorted_keys = sorted(lines_map.keys())
    lines = []
    for k in sorted_keys:
        row_chars = sorted(lines_map[k], key=lambda c: c["x0"])  # left to right
        text = "".join(c.get("text", "") for c in row_chars)
        # compute bbox
        x0 = min(c["x0"] for c in row_chars)
        x1 = max(c["x1"] for c in row_chars)
        top = min(c["top"] for c in row_chars)
        bottom = max(c["bottom"] for c in row_chars)
        lines.append({
            "text": text,
            "chars": row_chars,
            "bbox": (x0, top, x1, bottom)
        })
    return lines


def merge_bboxes(bboxes):
    x0 = min(b[0] for b in bboxes)
    top = min(b[1] for b in bboxes)
    x1 = max(b[2] for b in bboxes)
    bottom = max(b[3] for b in bboxes)
    return (x0, top, x1, bottom)


def bbox_intersects(a, b):
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    # overlap if projections overlap
    return not (ax1 < bx0 or ax0 > bx1 or ay1 < by0 or ay0 > by1)


def find_question_blocks(pdf_path):
    """
    Walks pages and returns a list of question dicts:
      { 'qnum': int or None, 'text': str, 'page': page_number (1-based), 'bbox': (x0,top,x1,bottom), 'images': [png_paths] }
    Prefers lines whose leading number characters appear to be in bold font.
    """
    questions = []
    with pdfplumber.open(pdf_path) as pdf:
        for p_idx, page in enumerate(pdf.pages, start=1):
            lines = group_chars_to_lines(page)
            if not lines:
                continue

            # detect candidate question-start lines and whether the number glyphs are bold
            starts = []
            for i, ln in enumerate(lines):
                # find leading number token in line text
                m = QUESTION_NUM_RE.match(ln["text"])
                if m:
                    # attempt to detect font of leading number chars:
                    # scan first few chars in ln['chars'] to find digits and inspect fontname
                    first_chars = ln["chars"][:6]  # few chars at start
                    digit_fontnames = []
                    for ch in first_chars:
                        if ch.get("text","").strip() and re.match(r'\d', ch.get("text","")):
                            fn = ch.get("fontname") or ch.get("font", "")
                            digit_fontnames.append(fn)
                    bold_detected = any(is_font_bold(fn) for fn in digit_fontnames) if digit_fontnames else False
                    starts.append((i, int(m.group(1)), bold_detected))

            # If there are no bold starts but starts exist, we will accept all numeric starts (fallback).
            # If some are bold, prefer only bold-starts to mark question boundaries.
            use_indices = []
            if any(b for (_, _, b) in starts):
                # use only indices where bold_detected True
                use_indices = [idx for (idx, num, b) in starts if b]
            else:
                use_indices = [idx for (idx, num, b) in starts]

            if not use_indices:
                # fallback: if no starts on this page, skip
                continue

            # Build blocks from these indices
            for si_index, start_ln_idx in enumerate(use_indices):
                start_line_idx = start_ln_idx
                # end at next used index or end of page
                if si_index + 1 < len(use_indices):
                    end_line_idx = use_indices[si_index + 1]
                else:
                    end_line_idx = len(lines)
                # combine text lines from start_line_idx upto end_line_idx (exclusive)
                block_lines = lines[start_line_idx:end_line_idx]
                block_text = "\n".join(l["text"] for l in block_lines).strip()
                block_bbox = merge_bboxes([l["bbox"] for l in block_lines])
                # find images (page.images) intersecting block_bbox
                imgs = []
                for img_idx, img in enumerate(page.images or []):
                    # pdfplumber image dict coords are x0, top, x1, bottom
                    img_bbox = (img.get("x0"), img.get("top"), img.get("x1"), img.get("bottom"))
                    if bbox_intersects(block_bbox, img_bbox):
                        # crop the image region and save as PNG file
                        try:
                            cropped = page.within_bbox(img_bbox).to_image(resolution=200).original
                            # Save to tmp folder
                            img_name = f"p{p_idx}_q{si_index}_img{img_idx}.png"
                            img_path = os.path.join(TMP_IMG_DIR, img_name)
                            cropped.save(img_path, format="PNG")
                            imgs.append(img_path)
                        except Exception:
                            # fallback attempt: render full page and crop using PIL by transforming bbox to px coordinates
                            imgs.append(None)
                # determine qnum from first line
                first_line_text = block_lines[0]["text"]
                m = QUESTION_NUM_RE.match(first_line_text)
                qnum = int(m.group(1)) if m else None

                questions.append({
                    "qnum": qnum,
                    "text": block_text,
                    "page": p_idx,
                    "bbox": block_bbox,
                    "images": imgs
                })

    return questions


# ---------------- GUI to show question + images and record A/B/C/D ----------------

class QuizApp:
    def __init__(self, master, questions):
        self.master = master
        self.questions = questions
        self.idx = 0
        self.answers = {}  # qnum -> letter
        self.current_img_tk = None

        master.title("Question Extractor — Answer A/B/C/D")
        master.geometry("1100x800")

        # Question display (scrollable)
        self.q_frame = tk.Frame(master)
        self.q_frame.pack(fill="both", expand=False, padx=12, pady=8)

        self.q_text = tk.Text(self.q_frame, height=12, wrap="word", font=("Segoe UI", 11))
        self.q_text.pack(fill="both", expand=True)

        # Image display
        self.img_label = tk.Label(master)
        self.img_label.pack(padx=8, pady=6)

        # Buttons A B C D
        btn_frame = tk.Frame(master)
        btn_frame.pack(pady=8)

        self.a_btn = tk.Button(btn_frame, text="A", width=10, command=lambda: self.record('A'))
        self.b_btn = tk.Button(btn_frame, text="B", width=10, command=lambda: self.record('B'))
        self.c_btn = tk.Button(btn_frame, text="C", width=10, command=lambda: self.record('C'))
        self.d_btn = tk.Button(btn_frame, text="D", width=10, command=lambda: self.record('D'))

        self.a_btn.grid(row=0, column=0, padx=6)
        self.b_btn.grid(row=0, column=1, padx=6)
        self.c_btn.grid(row=0, column=2, padx=6)
        self.d_btn.grid(row=0, column=3, padx=6)

        # Nav buttons
        nav_frame = tk.Frame(master)
        nav_frame.pack(pady=6)
        self.prev_btn = tk.Button(nav_frame, text="← Prev", width=12, command=self.prev_q)
        self.next_btn = tk.Button(nav_frame, text="Next →", width=12, command=self.next_q)
        self.finish_btn = tk.Button(nav_frame, text="Finish & Save", width=16, command=self.finish_and_save)

        self.prev_btn.grid(row=0, column=0, padx=8)
        self.next_btn.grid(row=0, column=1, padx=8)
        self.finish_btn.grid(row=0, column=2, padx=8)

        # status
        self.status_label = tk.Label(master, text="")
        self.status_label.pack(pady=6)

        self.show_current()

    def show_current(self):
        if not self.questions:
            self.q_text.delete("1.0", "end")
            self.q_text.insert("end", "No questions found.")
            self.status_label.config(text="0 / 0")
            return

        q = self.questions[self.idx]
        display_text = f"{q['qnum']}. {q['text']}" if q.get('qnum') else q['text']
        # Put full block text exactly as extracted (preserves symbols as plain text)
        self.q_text.delete("1.0", "end")
        self.q_text.insert("end", display_text)

        # Show first attached image if present
        self.current_img_tk = None
        self.img_label.config(image="")
        if q.get("images"):
            # find first valid image path
            img_path = None
            for ip in q["images"]:
                if ip and os.path.exists(ip):
                    img_path = ip
                    break
            if img_path:
                try:
                    im = Image.open(img_path)
                    im.thumbnail((900, 480), Image.LANCZOS)
                    self.current_img_tk = ImageTk.PhotoImage(im)
                    self.img_label.config(image=self.current_img_tk)
                except Exception as e:
                    self.img_label.config(text=f"(Unable to load image: {e})")
            else:
                self.img_label.config(text="(No image file available for this question.)")
        else:
            self.img_label.config(image="")
            self.img_label.config(text="")

        # update status
        self.status_label.config(text=f"Question {self.idx+1} / {len(self.questions)} — Q# {q.get('qnum')}")
        # update nav buttons
        self.prev_btn.config(state='normal' if self.idx>0 else 'disabled')
        self.next_btn.config(state='normal' if self.idx < len(self.questions)-1 else 'disabled')

    def record(self, letter):
        q = self.questions[self.idx]
        qnum = q.get('qnum') or (self.idx+1)
        self.answers[qnum] = letter
        # auto-advance if not last
        if self.idx < len(self.questions)-1:
            self.idx += 1
            self.show_current()
        else:
            # If last, prompt to save
            if messagebox.askyesno("Finished", "You answered the last question. Save answers to file now?"):
                self.finish_and_save()

    def prev_q(self):
        if self.idx > 0:
            self.idx -= 1
            self.show_current()

    def next_q(self):
        if self.idx < len(self.questions)-1:
            self.idx += 1
            self.show_current()

    def finish_and_save(self):
        # ensure all questions have some answer; we will save what is present
        if not self.answers:
            if not messagebox.askyesno("No answers", "You haven't entered any answers. Save empty file?"):
                return
        # ask for save location
        save_path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text files","*.txt")], initialfile="answers.txt")
        if not save_path:
            return
        # Write lines like "1-A"
        # Sort by question number if numeric keys, else by order encountered
        entries = []
        # try to sort numerically
        try:
            sorted_keys = sorted(self.answers.keys(), key=lambda x: int(x))
        except Exception:
            sorted_keys = list(self.answers.keys())
        for k in sorted_keys:
            entries.append(f"{k}-{self.answers[k]}")
        with open(save_path, "w", encoding="utf-8") as f:
            f.write("\n".join(entries))
        messagebox.showinfo("Saved", f"Saved {len(entries)} answers to {save_path}")

# ---------------- main execution ----------------

def main():
    # Step 1: extract question blocks
    try:
        questions = find_question_blocks(PDF_PATH)
    except Exception as e:
        messagebox.showerror("Error", f"Failed to parse PDF: {e}")
        return

    if not questions:
        # fallback: try weaker detection (any numbered line)
        messagebox.showwarning("No bolded numbers found", "No bolded-number question starts were found. Attempting fallback extraction (any numbered line).")
        # fallback: do simple splitting by regex
        with pdfplumber.open(PDF_PATH) as pdf:
            full_text = []
            for p in pdf.pages:
                full_text.append(p.extract_text() or "")
        all_text = "\n\n".join(full_text)
        # split by lines beginning with numbers
        parts = re.split(r'(?m)(?=^\s*\d+\s*\.)', all_text)
        questions = []
        for i, part in enumerate(parts):
            part = part.strip()
            if not part:
                continue
            m = re.match(r'^\s*(\d+)\s*\.\s*', part)
            qnum = int(m.group(1)) if m else i+1
            questions.append({"qnum": qnum, "text": part, "page": None, "bbox": None, "images": []})

    # Build and launch GUI
    root = tk.Tk()
    app = QuizApp(root, questions)
    root.mainloop()


if __name__ == "__main__":
    main()
