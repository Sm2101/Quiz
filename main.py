# main.py
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import os
import PyPDF2

# try to import your pdf_processor.extract_pages_with_images to get page images
try:
    from pdf_processor import extract_pages_with_images
    have_pdf_processor = True
except Exception:
    have_pdf_processor = False

from parser import parse_questions_from_text

# global state
questions = []
page_images = {}  # page_num -> image path or PIL.Image
current_idx = 0

def extract_text_with_pypdf2(pdf_path):
    text_pages = []
    with open(pdf_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        for p in reader.pages:
            try:
                text_pages.append(p.extract_text() or "")
            except Exception:
                text_pages.append("")
    full_text = "\n\n".join(text_pages)
    return full_text, text_pages

def load_pdf():
    global questions, current_idx, page_images
    path = filedialog.askopenfilename(filetypes=[("PDF files","*.pdf")])
    if not path:
        return
    status_label.config(text="Extracting text...")
    root.update_idletasks()

    full_text, page_texts = extract_text_with_pypdf2(path)
    # parse questions
    parsed = parse_questions_from_text(full_text)
    if not parsed:
        messagebox.showerror("No questions", "No questions were parsed from this PDF.")
        status_label.config(text="Ready")
        return

    # try to get page images for preview (if pdf_processor available)
    page_images = {}
    if have_pdf_processor:
        try:
            pages = extract_pages_with_images(path, ocr_on_image_pages=False)  # if your function supports this arg; else just call without
            # pages is expected list of dicts with page_num and page_image
            for p in pages:
                if isinstance(p, dict) and p.get("page_image"):
                    page_images[p.get("page_num")] = p.get("page_image")
        except TypeError:
            # fallback if signature different: call with single arg
            try:
                pages2 = extract_pages_with_images(path)
                for p in pages2:
                    if isinstance(p, dict) and p.get("page_image"):
                        page_images[p.get("page_num")] = p.get("page_image")
            except Exception:
                page_images = {}
        except Exception:
            page_images = {}

    # we don't have precise question->page mapping from parser, so we will attach no image
    # But we can attempt to match question numbers to page_texts: if a page contains the question number, map it.
    for q in parsed:
        qnum = q.get("number")
        q["page_num"] = None
        if qnum is not None:
            for i, ptext in enumerate(page_texts, start=1):
                if re_search_question_number_in_page(ptext, qnum):
                    q["page_num"] = i
                    break

    questions = parsed
    current_idx = 0
    status_label.config(text=f"Parsed {len(questions)} questions")
    show_question()

import re
def re_search_question_number_in_page(page_text, qnum):
    # crude check: look for "qnum." or "qnum )" in page text
    if not page_text:
        return False
    patterns = [rf'\n\s*{qnum}\.\s', rf'^{qnum}\.\s', rf'\n\s*{qnum}\s*\)', rf'\n\s*Q\s*{qnum}\.']
    for pat in patterns:
        if re.search(pat, page_text, flags=re.MULTILINE):
            return True
    # fallback simple contains (may be noisy)
    # look for " qnum." anywhere
    if f"{qnum}." in page_text:
        return True
    return False

def show_question():
    global current_idx
    if not questions:
        return
    q = questions[current_idx]
    # populate text and options
    qtext_box.delete("1.0", tk.END)
    qtext_box.insert(tk.END, q.get("text",""))

    opts = q.get("options", ["","","",""])
    for i in range(4):
        opt_entries[i].delete(0, tk.END)
        if i < len(opts):
            opt_entries[i].insert(0, opts[i])

    # show attached image if available via page_num mapping
    image_label.config(image="")
    image_label.image = None
    pnum = q.get("page_num")
    if pnum and pnum in page_images and os.path.exists(page_images[pnum]):
        try:
            pil = Image.open(page_images[pnum])
            pil.thumbnail((380,380))
            tkimg = ImageTk.PhotoImage(pil)
            image_label.config(image=tkimg)
            image_label.image = tkimg
        except Exception as e:
            print("Image load error:", e)

    # update nav
    idx_label.config(text=f"{current_idx+1} / {len(questions)}")
    prev_btn.config(state=tk.NORMAL if current_idx>0 else tk.DISABLED)
    next_btn.config(state=tk.NORMAL if current_idx < len(questions)-1 else tk.DISABLED)

def save_question():
    global current_idx
    if not questions:
        return
    q = questions[current_idx]
    q["text"] = qtext_box.get("1.0", tk.END).strip()
    q["options"] = [e.get().strip() for e in opt_entries]
    messagebox.showinfo("Saved", "Question saved locally.")

def next_q():
    global current_idx
    save_question()
    if current_idx < len(questions)-1:
        current_idx += 1
        show_question()

def prev_q():
    global current_idx
    save_question()
    if current_idx > 0:
        current_idx -= 1
        show_question()

def export_to_json():
    import json
    if not questions:
        messagebox.showinfo("No data","No questions to export.")
        return
    path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON","*.json")])
    if not path:
        return
    with open(path,"w",encoding="utf-8") as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)
    messagebox.showinfo("Exported", f"Exported {len(questions)} questions to {path}")

# UI setup
root = tk.Tk()
root.title("PDF → Quiz Builder (fixed parser)")
root.geometry("1000x720")

top_frame = tk.Frame(root)
top_frame.pack(fill="x", pady=6)
load_btn = tk.Button(top_frame, text="Load PDF", command=load_pdf)
load_btn.pack(side="left", padx=6)
export_btn = tk.Button(top_frame, text="Export JSON", command=export_to_json)
export_btn.pack(side="left", padx=6)
status_label = tk.Label(top_frame, text="Ready")
status_label.pack(side="right", padx=8)

qtext_box = tk.Text(root, height=8, wrap="word")
qtext_box.pack(fill="x", padx=8, pady=8)

opts_frame = tk.Frame(root)
opts_frame.pack(fill="x", padx=8)
opt_entries = []
for i in range(4):
    e = tk.Entry(opts_frame, width=110)
    e.pack(pady=3)
    opt_entries.append(e)

image_label = tk.Label(root)
image_label.pack(padx=8, pady=6)

nav_frame = tk.Frame(root)
nav_frame.pack(fill="x", pady=8)
prev_btn = tk.Button(nav_frame, text="← Prev", width=12, command=prev_q)
prev_btn.pack(side="left", padx=6)
save_btn = tk.Button(nav_frame, text="Save", width=12, command=save_question)
save_btn.pack(side="left", padx=6)
next_btn = tk.Button(nav_frame, text="Next →", width=12, command=next_q)
next_btn.pack(side="left", padx=6)
idx_label = tk.Label(nav_frame, text="0 / 0")
idx_label.pack(side="right", padx=12)

root.mainloop()
