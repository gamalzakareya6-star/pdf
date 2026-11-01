"""Tkinter GUI for PDF Toolkit."""
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import __version__, core


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"PDF Toolkit {__version__}")
        self.geometry("720x520")
        self.minsize(640, 460)

        self.status = tk.StringVar(value="Ready")
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        nb.add(self._merge_tab(nb), text="Merge")
        nb.add(self._extract_tab(nb), text="Extract pages")
        nb.add(self._split_tab(nb), text="Split")
        nb.add(self._rotate_tab(nb), text="Rotate")
        nb.add(self._text_tab(nb), text="Extract text")

        ttk.Label(self, textvariable=self.status, anchor="w", relief="sunken").pack(
            fill="x", side="bottom"
        )

    # ---------- helpers ----------
    def _run(self, fn, done_msg):
        """Run a job in a thread so the window never freezes."""
        self.status.set("Working...")

        def worker():
            try:
                result = fn()
                self.after(0, lambda: self._ok(done_msg, result))
            except Exception as e:  # noqa: BLE001 - show any error to the user
                self.after(0, lambda: self._fail(e))

        threading.Thread(target=worker, daemon=True).start()

    def _ok(self, msg, result=None):
        self.status.set(msg)
        messagebox.showinfo("Done", f"{msg}\n\n{result or ''}".strip())

    def _fail(self, err):
        self.status.set("Error")
        messagebox.showerror("Error", str(err))

    @staticmethod
    def _pick_pdf():
        return filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])

    @staticmethod
    def _save_pdf():
        return filedialog.asksaveasfilename(
            defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")]
        )

    # ---------- merge ----------
    def _merge_tab(self, parent):
        f = ttk.Frame(parent, padding=10)
        lb = tk.Listbox(f, selectmode="extended")
        lb.pack(fill="both", expand=True)
        btns = ttk.Frame(f)
        btns.pack(fill="x", pady=6)

        def add():
            for p in filedialog.askopenfilenames(filetypes=[("PDF files", "*.pdf")]):
                lb.insert("end", p)

        def remove():
            for i in reversed(lb.curselection()):
                lb.delete(i)

        def move(d):
            sel = lb.curselection()
            if len(sel) != 1:
                return
            i = sel[0]
            j = i + d
            if 0 <= j < lb.size():
                t = lb.get(i)
                lb.delete(i)
                lb.insert(j, t)
                lb.selection_set(j)

        def merge():
            files = list(lb.get(0, "end"))
            if len(files) < 2:
                return messagebox.showwarning("Merge", "Add at least 2 PDF files.")
            out = self._save_pdf()
            if out:
                self._run(lambda: core.merge_pdfs(files, out), "Merged successfully")

        for text, cmd in [("Add", add), ("Remove", remove),
                          ("Up", lambda: move(-1)), ("Down", lambda: move(1)),
                          ("Merge", merge)]:
            ttk.Button(btns, text=text, command=cmd).pack(side="left", padx=3)
        return f

    # ---------- extract ----------
    def _extract_tab(self, parent):
        f = ttk.Frame(parent, padding=10)
        src, spec = tk.StringVar(), tk.StringVar()
        ttk.Label(f, text="PDF file:").grid(row=0, column=0, sticky="w")
        ttk.Entry(f, textvariable=src, width=60).grid(row=0, column=1, padx=4)
        ttk.Button(f, text="Browse", command=lambda: src.set(self._pick_pdf() or src.get())
                   ).grid(row=0, column=2)
        ttk.Label(f, text="Pages (e.g. 1-3,5,8-):").grid(row=1, column=0, sticky="w", pady=10)
        ttk.Entry(f, textvariable=spec, width=30).grid(row=1, column=1, sticky="w", padx=4)

        def go():
            if not src.get() or not spec.get():
                return messagebox.showwarning("Extract", "Choose a file and page range.")
            out = self._save_pdf()
            if out:
                self._run(lambda: core.extract_pages(src.get(), spec.get(), out),
                          "Pages extracted")

        ttk.Button(f, text="Extract", command=go).grid(row=2, column=1, sticky="w")
        return f

    # ---------- split ----------
    def _split_tab(self, parent):
        f = ttk.Frame(parent, padding=10)
        src = tk.StringVar()
        ttk.Label(f, text="PDF file:").grid(row=0, column=0, sticky="w")
        ttk.Entry(f, textvariable=src, width=60).grid(row=0, column=1, padx=4)
        ttk.Button(f, text="Browse", command=lambda: src.set(self._pick_pdf() or src.get())
                   ).grid(row=0, column=2)

        def go():
            if not src.get():
                return messagebox.showwarning("Split", "Choose a PDF file.")
            folder = filedialog.askdirectory(title="Output folder")
            if folder:
                self._run(
                    lambda: f"{len(core.split_pdf(src.get(), folder))} files in {folder}",
                    "Split complete",
                )

        ttk.Button(f, text="Split into single pages", command=go).grid(
            row=1, column=1, sticky="w", pady=10)
        return f

    # ---------- rotate ----------
    def _rotate_tab(self, parent):
        f = ttk.Frame(parent, padding=10)
        src, deg = tk.StringVar(), tk.IntVar(value=90)
        ttk.Label(f, text="PDF file:").grid(row=0, column=0, sticky="w")
        ttk.Entry(f, textvariable=src, width=60).grid(row=0, column=1, padx=4)
        ttk.Button(f, text="Browse", command=lambda: src.set(self._pick_pdf() or src.get())
                   ).grid(row=0, column=2)
        box = ttk.Frame(f)
        box.grid(row=1, column=1, sticky="w", pady=10)
        for d in (90, 180, 270):
            ttk.Radiobutton(box, text=f"{d}°", value=d, variable=deg).pack(side="left", padx=4)

        def go():
            if not src.get():
                return messagebox.showwarning("Rotate", "Choose a PDF file.")
            out = self._save_pdf()
            if out:
                self._run(lambda: core.rotate_pdf(src.get(), deg.get(), out), "Rotated")

        ttk.Button(f, text="Rotate", command=go).grid(row=2, column=1, sticky="w")
        return f

    # ---------- text ----------
    def _text_tab(self, parent):
        f = ttk.Frame(parent, padding=10)
        src = tk.StringVar()
        ttk.Label(f, text="PDF file:").grid(row=0, column=0, sticky="w")
        ttk.Entry(f, textvariable=src, width=60).grid(row=0, column=1, padx=4)
        ttk.Button(f, text="Browse", command=lambda: src.set(self._pick_pdf() or src.get())
                   ).grid(row=0, column=2)

        def go():
            if not src.get():
                return messagebox.showwarning("Text", "Choose a PDF file.")
            out = filedialog.asksaveasfilename(
                defaultextension=".txt", initialfile=Path(src.get()).stem + ".txt",
                filetypes=[("Text", "*.txt")])
            if out:
                def job():
                    Path(out).write_text(core.extract_text(src.get()), encoding="utf-8")
                    return out
                self._run(job, "Text saved")

        ttk.Button(f, text="Extract text to .txt", command=go).grid(
            row=1, column=1, sticky="w", pady=10)
        return f


def main():
    App().mainloop()
