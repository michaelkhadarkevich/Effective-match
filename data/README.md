# Data

## `real/` — real transcripts (PRIVATE, git-ignored)

- Collected only from students who signed a consent form.
- Remove names, ID numbers, and any other identifying fields before saving; use a random `student_id`.
- Grades are sensitive personal data (Israeli Privacy Protection Law) — keep them local, never push or share.
- Expected schema (same as synthetic):

| column | type | description |
|---|---|---|
| `student_id` | str | random anonymous id |
| `track` | str | e.g. EE, CE, BME |
| `semester` | int | 1, 2, 3, ... |
| `course_id` | str | catalog id |
| `grade` | int | 0–100 |

## `catalog/` — course catalog (public)

`courses.csv` must be filled from the official Bar-Ilan Engineering yearbook (שנתון).
The current file is a **placeholder** with generic course names, not real course numbers.

## `synthetic/` — generated transcripts

Reproducible from `src/synthetic/generator.py` (fixed seed). Used for training only — never for testing.
