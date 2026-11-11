"""Effective-match — academic balance viewer (double-click app, no install needed).

Open it by double-clicking "Maazan App.bat" in the project folder, or drag a מאזן לימודים PDF onto that
file. Choose a PDF -> see remaining credits, courses registered this year, all courses and requirement
groups -> "Save results" writes the CSV files (they open in Excel). Everything runs locally.
"""
from __future__ import annotations

import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "data"))
import pandas as pd  # noqa: E402
from parse_maazan import obligations, parse, to_transcript  # noqa: E402

FONT = ("Arial", 13)
BIG = ("Arial", 16, "bold")


class App(tk.Tk):
    def __init__(self, pdf: Path | None = None):
        try:  # sharp text on scaled (high-DPI) Windows displays
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
        super().__init__()
        self.title("Effective-match — מאזן לימודים")
        self.geometry("1000x650")
        try:
            self.state("zoomed")  # open maximized so it fits any screen
        except tk.TclError:
            pass
        self.result: dict | None = None
        self.pdf: Path | None = None
        style = ttk.Style(self)
        style.configure("Treeview", font=FONT, rowheight=30)
        style.configure("Treeview.Heading", font=("Arial", 13, "bold"))
        style.configure("TNotebook.Tab", font=FONT, padding=(12, 6))

        top = tk.Frame(self, pady=10)
        top.pack(fill="x")
        tk.Button(top, text="📄  בחר קובץ PDF  /  Open PDF", font=BIG, padx=20, pady=8,
                  command=self.choose).pack(side="right", padx=12)
        self.save_btn = tk.Button(top, text="💾  שמור תוצאות  /  Save results", font=FONT, padx=12,
                                  pady=6, state="disabled", command=self.save)
        self.save_btn.pack(side="left", padx=12)
        self.status = tk.Label(top, text="בחר קובץ מאזן לימודים (PDF) מאתר בר-אילן", font=FONT, fg="#555")
        self.status.pack(side="right", padx=12)

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.summary = tk.Text(self.tabs, font=("Arial", 14), wrap="word", padx=16, pady=12)
        self.summary.tag_configure("rtl", justify="right")
        self.summary.tag_configure("h", font=BIG, justify="right")
        self.tabs.add(self.summary, text="  סיכום / Summary  ")
        self.req_tree = self._table("  דרישות / Requirements  ")
        self.course_tree = self._table("  קורסים / Courses  ")
        self.trans_tree = self._table("  ציונים / Grades  ")

        if pdf:
            self.after(100, lambda: self.load(pdf))

    # ------------------------------------------------------------- UI helpers
    def _table(self, title: str) -> ttk.Treeview:
        frame = tk.Frame(self.tabs)
        tree = ttk.Treeview(frame, show="headings")
        ys = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=ys.set)
        ys.pack(side="left", fill="y")
        tree.pack(fill="both", expand=True)
        self.tabs.add(frame, text=title)
        return tree

    @staticmethod
    def _fill(tree: ttk.Treeview, df: pd.DataFrame, widths: dict[str, int]) -> None:
        tree.delete(*tree.get_children())
        cols = list(reversed(df.columns))  # right-to-left: first column on the right
        tree["columns"] = cols
        for c in cols:
            tree.heading(c, text=c)
            tree.column(c, width=widths.get(c, 90), anchor="e")
        for _, r in df.iterrows():
            tree.insert("", "end", values=["" if pd.isna(r[c]) else r[c] for c in cols])

    # ------------------------------------------------------------- actions
    def choose(self) -> None:
        f = filedialog.askopenfilename(title="בחר מאזן לימודים", filetypes=[("PDF", "*.pdf")],
                                       initialdir=Path.home() / "Downloads")
        if f:
            self.load(Path(f))

    def load(self, pdf: Path) -> None:
        self.status.config(text="קורא את הקובץ...")
        self.update_idletasks()
        try:
            parsed = parse(pdf)
            courses = pd.DataFrame(parsed.courses)
            if courses.empty:
                raise ValueError("No course table found — is this a Bar-Ilan מאזן לימודים PDF?")
            sections, in_prog = obligations(courses, pd.DataFrame(parsed.sections))
            transcript = to_transcript(courses, "S001", parsed.meta.get("track"))
        except Exception as e:  # show any parsing problem to the user instead of crashing
            self.status.config(text="שגיאה")
            messagebox.showerror("Error", f"Could not read this PDF:\n{e}")
            return

        self.pdf = pdf
        self.result = {"meta": parsed.meta, "courses": courses, "sections": sections,
                       "in_progress": in_prog, "transcript": transcript}
        self._show_summary()
        self._fill(self.req_tree, sections.rename(columns={
            "section_code": "קוד", "section_name": "דרישה", "min_credits": "מינימום נ\"ז",
            "max_credits": "מקסימום נ\"ז", "earned_credits": "נצברו", "remaining_credits": "חסר"}),
            {"דרישה": 380})
        self._fill(self.course_tree, courses[["year_hebrew", "code", "type", "name", "credits",
                                              "grade_raw", "section_name"]].rename(columns={
            "year_hebrew": "שנה", "code": "קוד", "type": "סוג", "name": "שם", "credits": "נ\"ז",
            "grade_raw": "ציון", "section_name": "קבוצה"}), {"שם": 320, "קבוצה": 300})
        self._fill(self.trans_tree, transcript[["semester", "course_id", "course_name", "credits",
                                                "grade"]].rename(columns={
            "semester": "שנת לימוד", "course_id": "קוד", "course_name": "שם", "credits": "נ\"ז",
            "grade": "ציון"}), {"שם": 380})
        self.save_btn.config(state="normal")
        self.status.config(text=f"✔ {pdf.name}")

    def _show_summary(self) -> None:
        r, t = self.result, self.summary
        t.config(state="normal")
        t.delete("1.0", "end")
        m = r["meta"]
        t.insert("end", "מסלול\n", "h")
        t.insert("end", f"{m.get('track', '')}\n{m.get('specializations', '')}\n\n", "rtl")

        g = r["transcript"]
        if len(g):
            avg = (g.grade * g.credits).sum() / g.credits.sum() if g.credits.sum() else g.grade.mean()
            t.insert("end", "ציונים\n", "h")
            t.insert("end", f"קורסים עם ציון: {len(g)}\n", "rtl")
            t.insert("end", f"ממוצע משוקלל (הערכה): {avg:.1f}\n\n", "rtl")

        t.insert("end", "חסר להשלמה לפי דרישות\n", "h")
        rem = r["sections"][r["sections"].remaining_credits > 0]
        if rem.empty:
            t.insert("end", "אין דרישות חסרות ✔\n", "rtl")
        for _, s in rem.iterrows():
            t.insert("end", f"{s.section_name}:  חסר {s.remaining_credits:g} מתוך {s.min_credits:g} נ\"ז\n", "rtl")

        ip = r["in_progress"]
        ip = ip[ip.type != "תרגיל"]
        year = ip.year_hebrew.iloc[0] if len(ip) else ""
        t.insert("end", f"\nרשום השנה ({year}) — עדיין ללא ציון\n", "h")
        for _, c in ip.iterrows():
            t.insert("end", f"{c['name']}  ({c.credits:g} נ\"ז)\n", "rtl")
        t.config(state="disabled")

    def save(self) -> None:
        if not self.result:
            return
        default = ROOT / "data" / "real"
        default.mkdir(parents=True, exist_ok=True)
        folder = filedialog.askdirectory(title="Where to save?", initialdir=default)
        if not folder:
            return
        out = Path(folder) / self.pdf.stem
        out.mkdir(parents=True, exist_ok=True)
        r = self.result
        for name in ("courses", "sections", "transcript", "in_progress"):
            r[name].to_csv(out / f"{name}.csv", index=False, encoding="utf-8-sig")
        messagebox.showinfo("Saved", f"Saved to:\n{out}")
        os.startfile(out)  # open the folder in Explorer


if __name__ == "__main__":
    App(Path(sys.argv[1]) if len(sys.argv) > 1 else None).mainloop()
