"""Effective-match — academic balance viewer (double-click app, no install needed).

Open it by double-clicking "Maazan App.bat" in the project folder, or drag a מאזן לימודים PDF onto that
file. The main tab lists every course: name, grade (if any), credits (נ"ז) and lecturer.

Lecturers are NOT in the מאזן PDF. Double-click a course to type its lecturer; names are saved in
data/catalog/lecturers.csv (by course code) and reused for every PDF you open afterwards.
Everything runs locally.
"""
from __future__ import annotations

import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "data"))
import pandas as pd  # noqa: E402
from parse_maazan import obligations, parse  # noqa: E402

LECTURERS_CSV = ROOT / "data" / "catalog" / "lecturers.csv"
FONT = ("Arial", 13)
BIG = ("Arial", 16, "bold")
SKIP_TYPES = {"ש.מחלקה"}  # "department hours" placeholder rows


# ------------------------------------------------------------------ data helpers
def load_lecturers() -> dict[str, str]:
    if LECTURERS_CSV.exists():
        df = pd.read_csv(LECTURERS_CSV, dtype=str, encoding="utf-8-sig").fillna("")
        return dict(zip(df.course_id, df.lecturer))
    return {}


def save_lecturers(lect: dict[str, str]) -> None:
    LECTURERS_CSV.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(sorted(lect.items()), columns=["course_id", "lecturer"]).to_csv(
        LECTURERS_CSV, index=False, encoding="utf-8-sig")


def course_list(courses: pd.DataFrame, lecturers: dict[str, str]) -> pd.DataFrame:
    """One row per course: lecture + exercise + lab rows are merged (credits summed)."""
    c = courses[(courses.status != "requirement") & ~courses.type.isin(SKIP_TYPES)].copy()
    c["is_lecture"] = c.type.eq("הרצאה")
    rows = []
    for cid, g in c.groupby("course_id", sort=False):
        named = g.sort_values("is_lecture", ascending=False)
        graded = g.dropna(subset=["grade"])
        raw = g.grade_raw.dropna()
        grade = (str(int(graded.grade.max())) if len(graded)
                 else raw.iloc[0] if len(raw) else "")
        rows.append({
            "course_id": cid,
            "name": named.name.iloc[0],
            "grade": grade,
            "credits": g.credits.fillna(0).sum(),
            "lecturer": lecturers.get(cid, ""),
            "year": g.year_hebrew.dropna().iloc[0] if g.year_hebrew.notna().any() else "",
            "_year_num": g.year.min(),
        })
    df = pd.DataFrame(rows)
    df["_order"] = range(len(df))  # keep the PDF order within a year
    return df.sort_values(["_year_num", "_order"]).drop(columns=["_year_num", "_order"]).reset_index(drop=True)


# ------------------------------------------------------------------ app
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
        self.lecturers = load_lecturers()

        style = ttk.Style(self)
        style.configure("Treeview", font=FONT, rowheight=32)
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
        self.course_tree = self._table("  קורסים / Courses  ",
                                       hint="לחיצה כפולה על קורס כדי להוסיף / לשנות מרצה")
        self.course_tree.bind("<Double-1>", self.edit_lecturer)
        self.summary = tk.Text(self.tabs, font=("Arial", 14), wrap="word", padx=16, pady=12)
        self.summary.tag_configure("rtl", justify="right")
        self.summary.tag_configure("h", font=BIG, justify="right")
        self.tabs.add(self.summary, text="  סיכום / Summary  ")
        self.req_tree = self._table("  דרישות / Requirements  ")

        if pdf:
            self.after(100, lambda: self.load(pdf))

    # ------------------------------------------------------------- UI helpers
    def _table(self, title: str, hint: str | None = None) -> ttk.Treeview:
        frame = tk.Frame(self.tabs)
        if hint:
            tk.Label(frame, text=hint, font=("Arial", 11), fg="#666", anchor="e").pack(fill="x", padx=8)
        tree = ttk.Treeview(frame, show="headings")
        ys = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=ys.set)
        ys.pack(side="left", fill="y")
        tree.pack(fill="both", expand=True)
        self.tabs.add(frame, text=title)
        return tree

    @staticmethod
    def _fill(tree: ttk.Treeview, df: pd.DataFrame, widths: dict[str, int],
              ids: list[str] | None = None) -> None:
        tree.delete(*tree.get_children())
        cols = list(reversed(df.columns))  # right-to-left: first column on the right
        tree["columns"] = cols
        for c in cols:
            tree.heading(c, text=c)
            tree.column(c, width=widths.get(c, 110), anchor="e")
        for i, (_, r) in enumerate(df.iterrows()):
            vals = ["" if pd.isna(r[c]) else r[c] for c in cols]
            tree.insert("", "end", iid=ids[i] if ids else None, values=vals)

    def _show_courses(self) -> None:
        cl = course_list(self.result["courses"], self.lecturers)
        self.result["course_list"] = cl
        view = cl.assign(credits=cl.credits.map(lambda x: f"{x:g}"))[
            ["name", "grade", "credits", "lecturer"]].rename(columns={
                "name": "שם הקורס", "grade": "ציון", "credits": "נ\"ז", "lecturer": "מרצה"})
        self._fill(self.course_tree, view, {"שם הקורס": 460, "ציון": 90, "נ\"ז": 80, "מרצה": 300},
                   ids=list(cl.course_id))

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
        except Exception as e:  # show any parsing problem to the user instead of crashing
            self.status.config(text="שגיאה")
            messagebox.showerror("Error", f"Could not read this PDF:\n{e}")
            return

        self.pdf = pdf
        self.result = {"meta": parsed.meta, "courses": courses, "sections": sections,
                       "in_progress": in_prog}
        self._show_courses()
        self._show_summary()
        self._fill(self.req_tree, sections.rename(columns={
            "section_code": "קוד", "section_name": "דרישה", "min_credits": "מינימום נ\"ז",
            "max_credits": "מקסימום נ\"ז", "earned_credits": "נצברו", "remaining_credits": "חסר"}),
            {"דרישה": 420})
        self.tabs.select(0)
        self.save_btn.config(state="normal")
        self.status.config(text=f"✔ {pdf.name}")

    def edit_lecturer(self, event) -> None:
        cid = self.course_tree.identify_row(event.y)
        if not cid or not self.result:
            return
        row = self.result["course_list"].set_index("course_id").loc[cid]
        name = simpledialog.askstring("מרצה", f"מרצה עבור:\n{row['name']} ({cid})",
                                      initialvalue=self.lecturers.get(cid, ""), parent=self)
        if name is None:
            return
        if name.strip():
            self.lecturers[cid] = name.strip()
        else:
            self.lecturers.pop(cid, None)
        save_lecturers(self.lecturers)
        self._show_courses()
        self.course_tree.see(cid)
        self.course_tree.selection_set(cid)

    def _show_summary(self) -> None:
        r, t = self.result, self.summary
        t.config(state="normal")
        t.delete("1.0", "end")
        m = r["meta"]
        t.insert("end", "מסלול\n", "h")
        t.insert("end", f"{m.get('track', '')}\n{m.get('specializations', '')}\n\n", "rtl")

        cl = r["course_list"]
        g = cl[cl.grade.str.isdigit()].assign(grade=lambda d: d.grade.astype(int))
        t.insert("end", "ציונים\n", "h")
        t.insert("end", f"קורסים עם ציון: {len(g)}\n", "rtl")
        if len(g) and g.credits.sum():
            t.insert("end", f"ממוצע משוקלל (הערכה): {(g.grade * g.credits).sum() / g.credits.sum():.1f}\n", "rtl")
        t.insert("end", f"סה\"כ נ\"ז בקורסים עם ציון / עובר: "
                        f"{cl[cl.grade != ''].credits.sum():g}\n\n", "rtl")

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
        r["course_list"][["course_id", "name", "grade", "credits", "lecturer", "year"]].to_csv(
            out / "course_list.csv", index=False, encoding="utf-8-sig")
        for name in ("courses", "sections", "in_progress"):
            r[name].to_csv(out / f"{name}.csv", index=False, encoding="utf-8-sig")
        messagebox.showinfo("Saved", f"Saved to:\n{out}")
        os.startfile(out)  # open the folder in Explorer


if __name__ == "__main__":
    App(Path(sys.argv[1]) if len(sys.argv) > 1 else None).mainloop()
