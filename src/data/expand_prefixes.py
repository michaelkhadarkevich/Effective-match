"""Prefix expansion: turn each transcript into many (history -> next semester) training samples.

A student with semesters 1..T yields T-1 samples by repeatedly removing the last semester:

    sample t=T-1 : history = semesters 1..T-1   target = semester T
    sample t=T-2 : history = semesters 1..T-2   target = semester T-1
    ...
    sample t=1   : history = semester  1        target = semester 2

Each target contains the courses the student took that semester AND the grades they got,
so the same samples train both the course forecaster and the grade forecaster.

This multiplies the amount of training data (critical with few real transcripts), but the samples
from one student are strongly correlated. Therefore train/val/test MUST be split by student
(`split_by_student`), never by sample — otherwise prefixes of a test student leak into training.

Output: one row per sample with JSON columns
    sample_id, student_id, track, cutoff_semester, n_history_semesters,
    history  = [{"semester", "course_id", "grade"}, ...]
    target   = [{"course_id", "grade"}, ...]          (the semester cutoff_semester + 1)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def expand_prefixes(df: pd.DataFrame, min_history: int = 1) -> pd.DataFrame:
    rows = []
    for sid, g in df.sort_values(["student_id", "semester"]).groupby("student_id"):
        sems = sorted(g.semester.unique())
        track = g.track.iloc[0] if "track" in g else None
        for i in range(min_history, len(sems)):
            cutoff, nxt = sems[i - 1], sems[i]
            hist = g[g.semester <= cutoff]
            tgt = g[g.semester == nxt]
            rows.append({
                "sample_id": f"{sid}_t{cutoff}",
                "student_id": sid,
                "track": track,
                "cutoff_semester": int(cutoff),
                "n_history_semesters": i,
                "history": json.dumps(hist[["semester", "course_id", "grade"]].to_dict("records")),
                "target": json.dumps(tgt[["course_id", "grade"]].to_dict("records")),
            })
    return pd.DataFrame(rows)


def split_by_student(samples: pd.DataFrame, val: float = 0.15, test: float = 0.15,
                     seed: int = 42) -> pd.Series:
    """Assign 'train' / 'val' / 'test' per STUDENT so no student appears in two splits."""
    students = np.random.default_rng(seed).permutation(sorted(samples.student_id.unique()))
    n_test, n_val = int(len(students) * test), int(len(students) * val)
    split = {s: "test" for s in students[:n_test]}
    split |= {s: "val" for s in students[n_test:n_test + n_val]}
    split |= {s: "train" for s in students[n_test + n_val:]}
    return samples.student_id.map(split)


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=root / "data/synthetic/transcripts.csv")
    ap.add_argument("--out", type=Path, default=root / "data/synthetic/samples.csv")
    ap.add_argument("--min-history", type=int, default=1, help="min #semesters of history per sample")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    df = pd.read_csv(args.data)
    samples = expand_prefixes(df, args.min_history)
    samples["split"] = split_by_student(samples, seed=args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    samples.to_csv(args.out, index=False)

    n_st = df.student_id.nunique()
    print(f"{n_st} transcripts -> {len(samples)} samples ({len(samples) / n_st:.1f} per student)")
    print(samples.groupby("split").agg(students=("student_id", "nunique"),
                                       samples=("sample_id", "count")).to_string())


if __name__ == "__main__":
    main()
