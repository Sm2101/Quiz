import os
import re
import pdfplumber
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import messagebox

PDF_PATH = PDF_PATH = r"E:\pdf_quiz_windows\1.pdf"     # your uploaded PDF
TEMP_DIR = "question_images"
os.makedirs(TEMP_DIR, exist_ok=True)

QUESTION_PATTERN = re.compile(r'^\s*(\d+)[\.\)]')  # "1." or "1)"

BOLD_HINTS = ["Bold", "BD", "Black", "Heavy", "bold", "BOLD", "Bd", "SemiBold"]


def is_bold(fontname):
    if not fontname:
        return False
    return any(h in fontname for h in BOLD_HINTS)


def group_lines(page):
    chars = page.chars
    if not chars:
        return []

    lines_map = {}
    for ch in chars:
        key = int(round(ch["top"]))
        lines_map.setdefault(key, []).append(ch)

    lines = []
    for k in sorted(lines_map.keys()):
        row = sorted(lines_map[k], key=lambda c: c["x0"])
        text = "".join(c["text"] for c in row)
        x0 = min(c["x0"] for c in row)
        x1 = max(c["x1"] for c in row)
        top = min(c["top"] for c in row)
        bottom = max(c["bottom"] for c in row)
        lines.append({"text": text, "chars": row, "bbox": (x0, top, x1, bottom)})
    return lines


def merge_boxes(bboxes):
    return (
        min(b[0] for b in bboxes),
        min(b[1] for b in bboxes),
        max(b[2] for b in bboxes),
        max(b[3] for b in bboxes),
    )


def intersects(a, b):
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def extract_questions(pdf_path):
    questions = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_index, page in enumerate(pdf.pages, start=1):
            lines = group_lines(page)
            if not lines:
                continue

            starts = []
            for i, ln in enumerate(lines):
                m = QUESTION_PATTERN.match(ln["text"])
                if m:
                    number = int(m.group(1))
                    bold_number = False
                    for ch in ln["chars"][:5]:
                        if ch["text"].isdigit():
                            if is_bold(ch.get("fontname", "")):
                                bold_number = True
                    starts.append((i, number, bold_number))

            if not starts:
                continue

            if any(b for _, _, b in starts):
                indices = [idx for idx, _, b in starts if b]
            else:
                indices = [idx for idx, _, _ in starts]

            for s_i, start_line in enumerate(indices):
                end_line = indices[s_i + 1] if s_i + 1 < len(indices) else len(lines)
                block_lines = lines[start_line:end_line]
                block_text = "\n".join(l["text"] for l in block_lines)
                block_bbox = merge_boxes([l["bbox"] for l in block_lines])

                qnum = None
                m = QUESTION_PATTERN.match(block_lines[0]["text"])
                if m:
                    qnum = int(m.group(1))

                imgs = []
                for idx_img, img in enumerate(page.images):
                    ib = (img["x0"], img["top"], img["x1"], img["bottom"])
                    if intersects(block_bbox, ib):
                        try:
                            cropped = page.within_bbox(ib).to_image(resolution=200).original
                            fname = f"q{qnum}_img{idx_img}.png"
                            fpath = os.path.join(TEMP_DIR, fname)
                            cropped.save(fpath)
                            imgs.append(fpath)
                        except:
                            pass

                questions.append({
                    "number": qnum,
                    "text": block_text,
                    "images": imgs
                })

    return questions


#########################################
# GUI APP — show question + A/B/C/D
#########################################

class QuizApp:
    def __init__(self, root, questions):
        self.root = root
        self.questions = questions
        self.index = 0
        self.answers = {}

        root.title("Question Answering (A/B/C/D)")
        root.geometry("1000x780")

        self.qbox = tk.Text(root, height=15, wrap="word", font=("Segoe UI", 12))
        self.qbox.pack(fill="both", padx=10, pady=10)

        self.img_label = tk.Label(root)
        self.img_label.pack()

        btn_frame = tk.Frame(root)
        btn_frame.pack(pady=10)

        for letter in ["A", "B", "C", "D"]:
            tk.Button(btn_frame, text=letter, width=10,
                      command=lambda l=letter: self.record(l)).pack(side="left", padx=10)

        nav = tk.Frame(root)
        nav.pack(pady=10)

        tk.Button(nav, text="Prev", width=12, command=self.prev_q).pack(side="left", padx=10)
        tk.Button(nav, text="Next", width=12, command=self.next_q).pack(side="left", padx=10)
        tk.Button(nav, text="Finish & Save", width=16, command=self.finish).pack(side="left", padx=10)

        self.status = tk.Label(root, text="")
        self.status.pack()

        self.show_question()

    def show_question(self):
        q = self.questions[self.index]
        self.qbox.delete("1.0", "end")
        self.qbox.insert("end", f"{q['number']}. {q['text']}")

        self.img_label.config(image="", text="")
        if q["images"]:
            img_path = q["images"][0]
            try:
                im = Image.open(img_path)
                im.thumbnail((900, 420))
                self.tk_img = ImageTk.PhotoImage(im)
                self.img_label.config(image=self.tk_img)
            except:
                self.img_label.config(text="(Unable to load image)")

        self.status.config(text=f"Question {self.index+1}/{len(self.questions)}")

    def record(self, letter):
        qnum = self.questions[self.index]["number"]
        self.answers[qnum] = letter
        if self.index < len(self.questions)-1:
            self.index += 1
            self.show_question()
        else:
            self.finish()

    def next_q(self):
        if self.index < len(self.questions)-1:
            self.index += 1
            self.show_question()

    def prev_q(self):
        if self.index > 0:
            self.index -= 1
            self.show_question()

    def finish(self):
        if not self.answers:
            messagebox.showwarning("Empty", "You didn't answer anything!")
            return

        with open("answers.txt", "w") as f:
            for k in sorted(self.answers.keys()):
                f.write(f"{k}-{self.answers[k]}\n")

        messagebox.showinfo("Saved", "answers.txt created!")
        self.root.destroy()


def main():
    qs = extract_questions(PDF_PATH)
    if not qs:
        print("No questions found.")
        return
    root = tk.Tk()
    QuizApp(root, qs)
    root.mainloop()


if __name__ == "__main__":
    main()
