"""Parse a Bar-Ilan "מאזן לימודים" (academic balance) PDF into structured tables.

The Bar-Ilan PDF stores Hebrew in a TrueType font whose character codes are broken (copy-paste
gives garbage like "´¥²¨"). The glyph IDs are correct, though, so we decode every character through
the embedded font: glyph id -> glyph name -> Unicode. Text is stored in visual (left-to-right) order,
so Hebrew spans are reversed back to logical order. Table cells are assigned by the table's vertical
border lines.

Outputs (written to --out-dir, default data/real/<pdf name>/ which is git-ignored):
  courses.csv    one row per table line: section, year, code, type, name, credits, grade
  sections.csv   one row per requirement group: code, name, min / max / earned credits
  transcript.csv one row per course with a numeric grade, in the project's transcript schema
  meta.json      track, specializations, degree — NO name or ID number

Personal identifiers (name, ID number) are never written.

Usage:
  python src/data/parse_maazan.py path/to/maazan.pdf [--out-dir DIR] [--student-id S001]
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import pymupdf
from fontTools.ttLib import TTFont

HEBREW = re.compile(r"[א-ת]")
LTR_RUN = re.compile(r"[0-9A-Za-z][0-9A-Za-z.\-/:,_]*[0-9A-Za-z]|[0-9A-Za-z]")
MIRROR = str.maketrans("()[]{}", ")(][}{")
DEFAULT_BORDERS = [38, 72, 108, 398, 442, 509, 563]
COLUMNS = ["grade", "credits", "name", "type", "code", "year"]  # left -> right on the page
SECTION_RE = re.compile(r"^(\d{1,8})\s*-\s*(.+)$")
SUMMARY_RE = re.compile(r"מינ'\s*נ\"ז\s*:?\s*([\d.]+).*?מקס'\s*נ\"ז\s*:?\s*([\d.]+).*?שנצברו\s*:?\s*([\d.]+)")
HEADER_FIELDS = {"ת.לימודים": "degree", "מסלול": "track", "ש.ליעוץ": "advisory_year",
                 "רמת אנגלית": "english_level", "רמת עברית": "hebrew_level", "סטטוס": "status"}
GEMATRIA = dict(zip("אבגדהוזחטיכלמנסעפצקרשת",
                    [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 200, 300, 400]))


# ------------------------------------------------------------------ text decoding
def glyph_maps(doc: pymupdf.Document) -> dict[str, dict[int, str]]:
    """font name -> {glyph id: unicode char}, built from each embedded TrueType font."""
    maps: dict[str, dict[int, str]] = {}
    for page in doc:
        for xref, _ext, typ, base, *_ in page.get_fonts():
            name = base.split("+")[-1]
            if name in maps or typ not in ("TrueType", "Type0"):
                continue
            font = TTFont(io.BytesIO(doc.extract_font(xref)[3]))
            by_glyph: dict[str, str] = {}
            for cp, gname in font.getBestCmap().items():
                ch = chr(cp)
                # prefer real Hebrew/ASCII code points over private-use duplicates (e.g. U+F8FF for נ)
                if gname not in by_glyph or (0xE000 <= ord(by_glyph[gname]) <= 0xF8FF):
                    by_glyph[gname] = ch
            maps[name] = {gid: by_glyph.get(g) for gid, g in enumerate(font.getGlyphOrder())}
    return maps


def to_logical(visual: str) -> str:
    """Visual-order span -> logical order (reverse Hebrew, keep numbers/Latin runs readable)."""
    if not HEBREW.search(visual):
        return visual
    s = visual[::-1].translate(MIRROR)
    return LTR_RUN.sub(lambda m: m.group(0)[::-1], s)


@dataclass
class Span:
    x0: float
    x1: float
    y: float
    text: str


def page_spans(page: pymupdf.Page, gmaps: dict[str, dict[int, str]]) -> list[Span]:
    spans = []
    for t in page.get_texttrace():
        m = gmaps.get(t["font"], {})
        chars = []
        for c in t["chars"]:
            code, gid = c[0], c[1]
            ch = chr(code) if code not in (0xFFFD, 0) and code < 0x80 else m.get(gid)
            chars.append(ch if ch and not (0xE000 <= ord(ch) <= 0xF8FF) else "")
        text = to_logical("".join(chars))
        if text.strip():
            b = t["bbox"]
            spans.append(Span(b[0], b[2], round(b[3], 0), text))
    return spans


def column_borders(page: pymupdf.Page) -> list[float]:
    xs = sorted({round(it["rect"].x0) for it in page.get_drawings()
                 if abs(it["rect"].x1 - it["rect"].x0) < 1 and it["rect"].height > 5})
    return xs if len(xs) == len(DEFAULT_BORDERS) else DEFAULT_BORDERS


def group_rows(spans: list[Span], tol: float = 2.0) -> list[list[Span]]:
    rows: list[list[Span]] = []
    for s in sorted(spans, key=lambda s: (s.y, -s.x1)):
        if rows and abs(rows[-1][0].y - s.y) <= tol:
            rows[-1].append(s)
        else:
            rows.append([s])
    return rows


def rtl_join(spans: list[Span]) -> str:
    return re.sub(r"\s+", " ", "".join(s.text for s in sorted(spans, key=lambda s: -s.x1))).strip()


# ------------------------------------------------------------------ parsing
@dataclass
class Parsed:
    meta: dict = field(default_factory=dict)
    sections: list[dict] = field(default_factory=list)
    courses: list[dict] = field(default_factory=list)


def year_to_gregorian(hy: str) -> int | None:
    """'תשפ"ד' -> 2023 (academic year 2023/24)."""
    letters = [c for c in hy if c in GEMATRIA]
    if not letters:
        return None
    return 5000 + sum(GEMATRIA[c] for c in letters) - 3761


def parse(pdf: Path) -> Parsed:
    doc = pymupdf.open(pdf)
    gmaps = glyph_maps(doc)
    out = Parsed()
    section: dict | None = None
    in_table = False
    last_row: tuple[int, float] | None = None  # (page, y) of the last course row
    spec_row_y = 0.0

    for page in doc:
        borders = column_borders(page)
        for row in group_rows(page_spans(page, gmaps)):
            line = rtl_join(row)

            # header fields ("label: value") before the first table; name / ID are skipped on purpose
            if not out.sections and not in_table:
                for s in row:
                    lab = s.text.strip().rstrip(":").strip()
                    if lab in HEADER_FIELDS:
                        # value = spans to the left of the label, up to the next label
                        left = [v for v in row if v.x1 <= s.x0 + 1]
                        labels = [v for v in left if v.text.strip().rstrip(":").strip()
                                  in (*HEADER_FIELDS, "שם", "זיהוי")]
                        stop = max((v.x1 for v in labels), default=0)
                        out.meta[HEADER_FIELDS[lab]] = rtl_join([v for v in left if v.x0 >= stop])
                if "התמחויות" in line:
                    spec_row_y = row[0].y
                    out.meta["specializations"] = line.split(":", 1)[-1].strip()
                elif "specializations" in out.meta and 0 < row[0].y - spec_row_y < 12:
                    out.meta["specializations"] += " " + line  # wrapped second line

            m_sum = SUMMARY_RE.search(line)
            if m_sum and section is not None:
                section.update(min_credits=float(m_sum[1]), max_credits=float(m_sum[2]),
                               earned_credits=float(m_sum[3]))
                continue

            m_sec = SECTION_RE.match(line)
            if m_sec and not any(s.x1 <= borders[2] for s in row):  # nothing in grade/credit columns
                section = {"section_code": m_sec[1], "section_name": m_sec[2].strip()}
                out.sections.append(section)
                continue
            if line.startswith("קבוצות קורס ללא שיוך"):
                section = {"section_code": "unassigned", "section_name": line}
                out.sections.append(section)
                continue

            cells = {c: [] for c in COLUMNS}
            for s in row:
                xc = (s.x0 + s.x1) / 2
                for i, c in enumerate(COLUMNS):
                    if borders[i] <= xc < borders[i + 1]:
                        cells[c].append(s)
            cells = {c: rtl_join(v) for c, v in cells.items()}

            if cells["name"] == "שם" and cells["code"] == "קוד":
                in_table = True
                continue
            if not in_table or section is None or not any(cells.values()):
                continue

            code_ok = re.fullmatch(r"\d{4,6}(-\d{2})?", cells["code"])
            if not code_ok:
                # continuation line of a wrapped cell (e.g. "קולוקויום / רשות"): same page, just below
                if (out.courses and not cells["code"] and not cells["credits"]
                        and last_row is not None and last_row[0] == page.number
                        and 0 < row[0].y - last_row[1] < 12):
                    prev = out.courses[-1]
                    for c in ("name", "type"):
                        if cells[c]:
                            prev[c] = f"{prev[c]} {cells[c]}".strip()
                continue

            last_row = (page.number, row[0].y)
            base, _, grp = cells["code"].partition("-")
            grade_raw = cells["grade"]
            out.courses.append({
                "section_code": section["section_code"],
                "section_name": section["section_name"],
                "year_hebrew": cells["year"],
                "year": year_to_gregorian(cells["year"]),
                "code": cells["code"],
                "course_id": base,
                "group": grp or None,
                "type": cells["type"],
                "name": cells["name"],
                "credits": float(cells["credits"]) if re.fullmatch(r"[\d.]+", cells["credits"]) else None,
                "grade_raw": grade_raw,
                "grade": int(grade_raw) if grade_raw.isdigit() else None,
                "status": ("failed" if grade_raw.startswith("נ") else "pass" if grade_raw == "עובר"
                           else "exempt" if grade_raw == "פטור" else "graded" if grade_raw.isdigit()
                           else "requirement" if not cells["year"] else "no_grade"),
            })
    # drop faculty-level headers ("83 - הפקולטה להנדסה"): no credit summary and no courses of their own
    used = {c["section_code"] for c in out.courses}
    out.sections = [s for s in out.sections if "min_credits" in s or s["section_code"] in used]
    return out


def to_transcript(courses: pd.DataFrame, student_id: str, track: str | None) -> pd.DataFrame:
    """One row per (course, year) with a numeric grade, in the project's transcript schema.

    The balance lists academic YEARS, not semesters, so `semester` here is the 1-based academic-year
    index (first year in the document = 1).
    """
    g = courses.dropna(subset=["grade", "year"])
    g = g.sort_values("grade", ascending=False).drop_duplicates(["course_id", "year"])
    years = sorted(g.year.unique())
    return pd.DataFrame({
        "student_id": student_id,
        "track": track,
        "semester": g.year.map({y: i + 1 for i, y in enumerate(years)}).astype(int),
        "course_id": g.course_id,
        "course_name": g.name,
        "credits": g.credits,
        "grade": g.grade.astype(int),
    }).sort_values(["semester", "course_id"]).reset_index(drop=True)


def obligations(courses: pd.DataFrame, sections: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Remaining credits per requirement group + courses registered this year without a grade yet."""
    sec = sections.copy()
    sec["remaining_credits"] = (sec.min_credits - sec.earned_credits).clip(lower=0)
    current = courses.year.max()
    in_progress = courses[(courses.year == current) & courses.grade.isna()
                          & ~courses.type.isin(["ש.מחלקה"])]
    return sec, in_progress


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--student-id", default="S001", help="anonymous id to put in transcript.csv")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # Hebrew output on Windows consoles

    out_dir = args.out_dir or root / "data/real" / args.student_id
    out_dir.mkdir(parents=True, exist_ok=True)

    parsed = parse(args.pdf)
    courses = pd.DataFrame(parsed.courses)
    sections = pd.DataFrame(parsed.sections)
    transcript = to_transcript(courses, args.student_id, parsed.meta.get("track"))
    sections, in_progress = obligations(courses, sections)

    courses.to_csv(out_dir / "courses.csv", index=False, encoding="utf-8-sig")
    sections.to_csv(out_dir / "sections.csv", index=False, encoding="utf-8-sig")
    transcript.to_csv(out_dir / "transcript.csv", index=False, encoding="utf-8-sig")
    (out_dir / "meta.json").write_text(json.dumps(parsed.meta, ensure_ascii=False, indent=2), "utf-8")

    print(f"{len(courses)} course rows, {len(sections)} sections, "
          f"{len(transcript)} graded courses -> {out_dir}\n")
    print("Remaining credits per requirement group:")
    for _, s in sections[sections.remaining_credits > 0].iterrows():
        print(f"  {s.section_code:>10}  {s.remaining_credits:5.1f} of {s.min_credits:5.1f}  {s.section_name}")
    print(f"\nRegistered this year ({in_progress.year_hebrew.iloc[0] if len(in_progress) else '-'}), "
          f"no grade yet:")
    for _, c in in_progress[in_progress.type != "תרגיל"].iterrows():
        print(f"  {c.code:>10}  {c.credits:4.1f}  {c['name']}")


if __name__ == "__main__":
    main()
