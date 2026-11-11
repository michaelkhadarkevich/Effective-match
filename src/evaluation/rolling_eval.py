"""Rolling (backtest) evaluation: forecast a student's next semester from their past.

Fold k (k = 1, 2, ..., K):
    cutoff_s  = last_semester_s - k            (per student s)
    history   = all rows with semester <= cutoff_s        -> training data
    target    = all rows with semester == cutoff_s + 1    -> what must be forecast

So fold 1 hides each student's last semester and forecasts it, fold 2 hides the last two semesters
and forecasts the second-to-last one, and so on. Every model only ever sees data from before the
forecast semester (for every student), so there is no leakage from the future.

Two forecasts are evaluated per fold:
  1. WHICH courses the student takes next semester  -> precision / recall / F1 against the true set
  2. WHAT grade they get in each course actually taken -> MAE / RMSE

Baselines here are deliberately simple; trained models (MF/IRT, sequence models) plug into the same
`forecast_courses` / `forecast_grades` interface later.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

PASS_GRADE = 56


# ---------------------------------------------------------------- splitting
def rolling_split(df: pd.DataFrame, k: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (history, target) for fold k. Students with too few semesters are skipped."""
    last = df.groupby("student_id")["semester"].transform("max")
    cutoff = last - k
    keep = cutoff >= 1  # need at least one semester of history
    history = df[keep & (df.semester <= cutoff)]
    target = df[keep & (df.semester == cutoff + 1)]
    return history, target


# ---------------------------------------------------------------- course forecast
def load_catalog(path: Path) -> pd.DataFrame:
    cat = pd.read_csv(path)
    cat["prereqs"] = cat["prereqs"].fillna("").apply(lambda s: [p for p in s.split(";") if p])
    return cat.set_index("course_id")


def forecast_courses(history: pd.DataFrame, cat: pd.DataFrame) -> dict[str, set[str]]:
    """Rule + popularity baseline for next-semester course sets.

    1. retake every course failed (and not since passed)
    2. take every eligible core course whose catalog semester == next semester
    3. add the most popular eligible electives (popularity = #students who took it in history),
       as many as the student's median number of electives per semester so far (default 2)
    """
    electives = cat.index[cat.elective == 1]
    popularity = history[history.course_id.isin(electives)].groupby("course_id").student_id.nunique()
    out: dict[str, set[str]] = {}
    for sid, h in history.groupby("student_id"):
        nxt = h.semester.max() + 1
        best = h.groupby("course_id").grade.max()
        passed = set(best.index[best >= PASS_GRADE])
        failed = set(best.index[best < PASS_GRADE])

        def eligible(cid: str) -> bool:
            return cid not in passed and all(p in passed for p in cat.at[cid, "prereqs"])

        pred = set(failed)
        pred |= {c for c in cat.index[(cat.elective == 0) & (cat.semester == nxt)] if eligible(c)}

        el_hist = h[h.course_id.isin(electives)].groupby("semester").size()
        n_el = int(el_hist.median()) if len(el_hist) else 2
        cands = [c for c in electives if cat.at[c, "semester"] <= nxt and eligible(c)]
        cands.sort(key=lambda c: popularity.get(c, 0), reverse=True)
        pred |= set(cands[:n_el])
        out[sid] = pred
    return out


def course_metrics(pred: dict[str, set[str]], target: pd.DataFrame) -> dict[str, float]:
    p_list, r_list, f_list = [], [], []
    for sid, t in target.groupby("student_id"):
        true, guess = set(t.course_id), pred.get(sid, set())
        tp = len(true & guess)
        p = tp / len(guess) if guess else 0.0
        r = tp / len(true) if true else 0.0
        p_list.append(p)
        r_list.append(r)
        f_list.append(2 * p * r / (p + r) if p + r else 0.0)
    return {"course_precision": np.mean(p_list), "course_recall": np.mean(r_list),
            "course_f1": np.mean(f_list)}


# ---------------------------------------------------------------- grade forecast
def forecast_grades(history: pd.DataFrame, target: pd.DataFrame) -> dict[str, pd.Series]:
    gmean = history.grade.mean()
    cmean = history.groupby("course_id").grade.mean()
    smean = history.groupby("student_id").grade.mean()
    c = target.course_id.map(cmean).fillna(gmean)
    s = target.student_id.map(smean).fillna(gmean)
    return {
        "global_mean": pd.Series(gmean, index=target.index),
        "course_mean": c,
        "student_plus_offset": (s + (c - gmean)).clip(0, 100),
    }


# ---------------------------------------------------------------- driver
def run(df: pd.DataFrame, cat: pd.DataFrame, max_k: int) -> pd.DataFrame:
    rows = []
    for k in range(1, max_k + 1):
        history, target = rolling_split(df, k)
        if target.empty:
            break
        cm = course_metrics(forecast_courses(history, cat), target)
        for name, pred in forecast_grades(history, target).items():
            err = pred - target.grade
            rows.append({"fold_k": k, "forecast_semester": f"last-{k - 1}" if k > 1 else "last",
                         "n_students": target.student_id.nunique(), "grade_model": name,
                         "MAE": err.abs().mean(), "RMSE": np.sqrt((err**2).mean()), **cm})
    return pd.DataFrame(rows)


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=root / "data/synthetic/transcripts.csv")
    ap.add_argument("--catalog", type=Path, default=root / "data/catalog/courses.csv")
    ap.add_argument("--max-k", type=int, default=4, help="number of semesters to roll back")
    ap.add_argument("--out", type=Path, default=None, help="optional CSV for the results table")
    args = ap.parse_args()

    res = run(pd.read_csv(args.data), load_catalog(args.catalog), args.max_k)
    pd.set_option("display.width", 200)
    print(res.to_string(index=False, float_format="%.3f"))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        res.to_csv(args.out, index=False)


if __name__ == "__main__":
    main()
