"""Baseline grade predictors evaluated with a temporal split.

Split: for each student, the LAST semester is the test set; all earlier semesters are training.

Baselines:
  1. course_mean          — mean grade of the course over training rows
  2. student_plus_offset  — student's mean training grade + (course mean - global mean)
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def temporal_split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    last = df.groupby("student_id")["semester"].transform("max")
    return df[df.semester < last], df[df.semester == last]


def evaluate(train: pd.DataFrame, test: pd.DataFrame) -> pd.DataFrame:
    gmean = train.grade.mean()
    cmean = train.groupby("course_id").grade.mean()
    smean = train.groupby("student_id").grade.mean()

    c = test.course_id.map(cmean).fillna(gmean)
    s = test.student_id.map(smean).fillna(gmean)
    preds = {
        "global_mean": pd.Series(gmean, index=test.index),
        "course_mean": c,
        "student_plus_offset": (s + (c - gmean)).clip(0, 100),
    }
    out = []
    for name, p in preds.items():
        err = p - test.grade
        out.append({"model": name, "MAE": err.abs().mean(), "RMSE": np.sqrt((err**2).mean())})
    return pd.DataFrame(out)


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=root / "data/synthetic/transcripts.csv")
    args = ap.parse_args()

    df = pd.read_csv(args.data)
    train, test = temporal_split(df)
    print(f"train rows {len(train)}, test rows {len(test)}")
    print(evaluate(train, test).to_string(index=False, float_format="%.2f"))


if __name__ == "__main__":
    main()
