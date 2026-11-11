"""Synthetic transcript generator (latent-skill model).

Each synthetic student has a latent skill vector over the skill dimensions in the course catalog
(math, programming, physics, circuits, signals) built from a shared "general ability" factor plus
skill-specific deviations. Each course has a skill loading vector and a difficulty.

    grade = BASE + SCALE * (skills . loading - DIFFICULTY_SCALE * difficulty) + workload + noise

Realistic effects modelled:
  * correlated skills (general ability factor)
  * elective self-selection by skill + interest (creates the selection bias present in real data)
  * semester workload penalty
  * failing (< 56) and retaking the course next semester
  * grade heaping at the pass threshold and at 100

All constants below are PLACEHOLDERS and must be calibrated against real-transcript statistics
(per-course mean / std, fail rate, inter-course correlations) — see docs/proposal_outline.md.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

SKILLS = ["math", "programming", "physics", "circuits", "signals"]
TRACKS = ["EE", "CE", "BME"]

BASE = 78.0
SCALE = 14.0
DIFFICULTY_SCALE = 1.0
NOISE_STD = 7.0
PASS_GRADE = 56
GENERAL_FACTOR_WEIGHT = 0.7
ELECTIVES_PER_SEMESTER = 2
N_SEMESTERS = 8


def load_catalog(path: Path) -> pd.DataFrame:
    cat = pd.read_csv(path)
    cat["prereqs"] = cat["prereqs"].fillna("").apply(lambda s: [p for p in s.split(";") if p])
    return cat


def sample_student(rng: np.random.Generator) -> dict:
    g = rng.normal()
    specific = rng.normal(size=len(SKILLS))
    w = GENERAL_FACTOR_WEIGHT
    skills = w * g + np.sqrt(1 - w**2) * specific
    interest = rng.dirichlet(np.ones(len(SKILLS)) * 0.8)
    return {"skills": skills, "interest": interest, "track": rng.choice(TRACKS)}


def grade_for(student: dict, course: pd.Series, n_courses: int, rng: np.random.Generator) -> int:
    loading = course[SKILLS].to_numpy(dtype=float)
    loading = loading / (loading.sum() or 1.0)
    signal = student["skills"] @ loading - DIFFICULTY_SCALE * (course["difficulty"] - 0.5) * 2
    workload = -0.8 * max(0, n_courses - 5)
    g = BASE + SCALE * signal + workload + rng.normal(0, NOISE_STD)
    g = int(np.clip(round(g), 0, 100))
    if 50 <= g < PASS_GRADE and rng.random() < 0.4:  # heaping at pass threshold
        g = PASS_GRADE
    if g >= 97 and rng.random() < 0.5:  # heaping at 100
        g = 100
    return g


def simulate_student(sid: str, cat: pd.DataFrame, rng: np.random.Generator) -> list[dict]:
    st = sample_student(rng)
    passed: set[str] = set()
    retake: list[str] = []
    rows = []
    core = cat[cat["elective"] == 0]
    electives = cat[cat["elective"] == 1]

    for sem in range(1, N_SEMESTERS + 1):
        eligible = lambda c: c["course_id"] not in passed and all(p in passed for p in c["prereqs"])
        planned = [c for _, c in core[core["semester"] == sem].iterrows() if eligible(c)]
        planned += [cat.set_index("course_id").loc[cid].rename(cid) for cid in retake]
        retake = []

        # elective self-selection: utility = interest . loading + skill . loading + noise
        el = [c for _, c in electives[electives["semester"] <= sem].iterrows() if eligible(c)]
        if el:
            def utility(c):
                lv = c[SKILLS].to_numpy(dtype=float)
                return st["interest"] @ lv + 0.3 * st["skills"] @ lv + rng.normal(0, 0.2)
            el = sorted(el, key=utility, reverse=True)[:ELECTIVES_PER_SEMESTER]
            planned += el

        for c in planned:
            cid = c["course_id"] if "course_id" in c else c.name
            g = grade_for(st, c, len(planned), rng)
            rows.append({"student_id": sid, "track": st["track"], "semester": sem,
                         "course_id": cid, "grade": g})
            if g >= PASS_GRADE:
                passed.add(cid)
            else:
                retake.append(cid)
    return rows


def generate(n_students: int, catalog: Path, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    cat = load_catalog(catalog)
    rows = []
    for i in range(n_students):
        rows += simulate_student(f"S{i:05d}", cat, rng)
    return pd.DataFrame(rows)


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n-students", type=int, default=2000)
    ap.add_argument("--catalog", type=Path, default=root / "data/catalog/courses.csv")
    ap.add_argument("--out", type=Path, default=root / "data/synthetic/transcripts.csv")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    df = generate(args.n_students, args.catalog, args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f"wrote {len(df)} rows for {df.student_id.nunique()} students -> {args.out}")
    print(f"mean grade {df.grade.mean():.1f}, std {df.grade.std():.1f}, "
          f"fail rate {(df.grade < PASS_GRADE).mean():.1%}")


if __name__ == "__main__":
    main()
