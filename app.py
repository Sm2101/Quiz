import tkinter as tk
from tkinter import filedialog, messagebox
from extractor import extract_question_blocks
from PIL import Image, ImageTk
import csv
import openpyxl
import os

class QuizApp:
    def __init__(self, root):
        self.root = root
        root.title("MCQ Extraction Quiz")
        root.geometry("1100x850")

        self.questions = []
        self.answers = {}
        self.index = 0

        self.theme_dark = False

        tk.Button(root, text="Load PDF", command=self.load_pdf).pack(pady=10)

        # Theme toggle
        tk.Button(root, text="Toggle Theme", command=self.toggle_theme).pack()

        # Question area scrollable
        frame = tk.Frame(root)
        frame.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(frame)
        scrollbar = tk.Scrollbar(frame, command=self.canvas.yview)
        scrollbar.pack(side="right", fill="y")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)

        self.inner = tk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        self.qtext = tk.Label(self.inner, text="", font=("Segoe UI", 14), wraplength=900, justify="left")
        self.qtext.pack(pady=10)

        self.img_frame = tk.Frame(self.inner)
        self.img_frame.pack()

        # Buttons
        btn_frame = tk.Frame(root)
        btn_frame.pack(pady=20)

        for opt in ["A", "B", "C", "D"]:
            self.root.bind(opt.lower(), lambda e, x=opt: self.record_answer(x))
            tk.Button(btn_frame, text=opt, width=10, command=lambda x=opt: self.record_answer(x)).pack(side="left", padx=10)

        nav = tk.Frame(root)
        nav.pack(pady=10)

        tk.Button(nav, text="Prev", width=12, command=self.prev_q).pack(side="left", padx=10)
        tk.Button(nav, text="Next", width=12, command=self.next_q).pack(side="left", padx=10)
        tk.Button(nav, text="Finish", width=16, command=self.finish).pack(side="left", padx=10)

        self.status = tk.Label(root, text="")
        self.status.pack()

    def toggle_theme(self):
        self.theme_dark = not self.theme_dark
        bg = "#1e1e1e" if self.theme_dark else "#ffffff"
        fg = "#ffffff" if self.theme_dark else "#000000"
        self.root.configure(bg=bg)
        self.qtext.configure(bg=bg, fg=fg)
        self.canvas.configure(bg=bg)
        self.status.configure(bg=bg, fg=fg)

    def load_pdf(self):
        file = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        if not file:
            return

        self.questions = extract_question_blocks(file)
        if not self.questions:
            messagebox.showerror("Error", "Could not extract questions.")
            return

        self.index = 0
        self.show_question()

    def show_question(self):
        q = self.questions[self.index]

        self.qtext.config(text=f"Q{q['number']}.\n\n{q['text']}")

        for w in self.img_frame.winfo_children():
            w.destroy()

        # grid layout 2×2
        images = []
        for img_path in q["images"]:
            try:
                im = Image.open(img_path)
                im.thumbnail((400, 300))
                tkim = ImageTk.PhotoImage(im)
                images.append(tkim)
            except:
                pass

        self._imgs = images  # keep reference

        for i, im in enumerate(images):
            r = i // 2
            c = i % 2
            tk.Label(self.img_frame, image=im).grid(row=r, column=c, padx=10, pady=10)

        self.status.config(text=f"{self.index+1}/{len(self.questions)}")

    def record_answer(self, letter):
        self.answers[self.questions[self.index]["number"]] = letter
        self.auto_save()
        self.next_q()

    def next_q(self):
        if self.index < len(self.questions)-1:
            self.index += 1
            self.show_question()

    def prev_q(self):
        if self.index > 0:
            self.index -= 1
            self.show_question()

    def auto_save(self):
        with open("answers.txt", "w") as f:
            for q, ans in sorted(self.answers.items()):
                f.write(f"{q}-{ans}\n")

    def finish(self):
        if not self.answers:
            return

        # Save txt
        with open("answers.txt", "w") as f:
            for q, ans in sorted(self.answers.items()):
                f.write(f"{q}-{ans}\n")

        # Save CSV
        with open("answers.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Question", "Answer"])
            for q, ans in sorted(self.answers.items()):
                w.writerow([q, ans])

        # Save Excel
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Question", "Answer"])
        for q, ans in sorted(self.answers.items()):
            ws.append([q, ans])
        wb.save("answers.xlsx")

        messagebox.showinfo("Done", "Saved answers in txt, csv, xlsx")

if __name__ == "__main__":
    root = tk.Tk()
    QuizApp(root)
    root.mainloop()
