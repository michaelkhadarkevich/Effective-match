# Effective-match — Course Recommendation for Bar-Ilan Engineering

**Team:** Michael Khadarkevich, Matan Coen · **Instructor:** Dr. Alexander Apartsin · Bar-Ilan University, Faculty of Engineering

Grade-aware elective recommendation for students of the Bar-Ilan University Faculty of Engineering.
Given a student's partial transcript (courses, semesters, grades), track, and interests, the system
predicts the student's expected grade in each eligible course and recommends a ranked list of electives
that respects prerequisites and degree requirements.

## Task formulation

| | |
|---|---|
| **Input** | Partial transcript `(course, semester, grade)*`, track (EE / CE / Biomedical / ...), optional free-text interests |
| **Output** | Ranked list of eligible electives with predicted grade, P(grade ≥ 85), and a short explanation |
| **Constraints** | Prerequisites, degree requirements, privacy of real grades |

## Planned pipeline

```
transcript ─► preprocessing ─► prerequisite / eligibility filter ─► grade predictor ─► ranker ─► explanation
                                                                    ▲
                                    synthetic pretraining ──────────┘
```

## Approaches compared

1. **Baselines** — course mean; student mean + course offset
2. **Matrix factorization / IRT** — latent student ability × course difficulty
3. **Sequence model (trained)** — GRU / Transformer over semester-ordered transcript (knowledge-tracing style),
   trained on: real only · synthetic only · synthetic pretrain → real fine-tune
4. **LLM zero-shot** — comparison point only

## Data

- **Real transcripts** — collected from consenting students, anonymized. **Never committed to this repository**
  (see [`data/README.md`](data/README.md)).
- **Academic balance parser** ([`src/data/parse_maazan.py`](src/data/parse_maazan.py)) — reads a Bar-Ilan
  "מאזן לימודים" PDF and extracts every course (year, code, type, name, credits, grade), each requirement
  group with min / earned / remaining credits, and the courses registered this year. Also writes the
  transcript in the project schema. Name and ID number are never extracted; output goes to the git-ignored `data/real/`.
- **Course catalog** — courses, credits and prerequisites from the Bar-Ilan Engineering yearbook (שנתון).
- **Synthetic transcripts** — latent-skill generator calibrated to real grade statistics
  ([`src/synthetic/generator.py`](src/synthetic/generator.py)). Used for **training only**; the test set is 100% real.
- **Prefix expansion** ([`src/data/expand_prefixes.py`](src/data/expand_prefixes.py)) — more training data from
  each transcript: remove the last semester → sample "semesters 1..T-1 → forecast semester T (courses + grades)",
  then remove the second-to-last → "1..T-2 → T-1", and so on. A student with T semesters gives T-1 samples
  (≈7 per 8-semester student). Samples from the same student are correlated, so splits are **by student**, never by sample.

## Evaluation

- **Rolling backtest** ([`src/evaluation/rolling_eval.py`](src/evaluation/rolling_eval.py)):
  fold 1 hides each student's last semester and forecasts it from everything before; fold 2 hides the
  last two semesters and forecasts the second-to-last; and so on. Each fold forecasts
  **which courses** the student takes next (precision / recall / F1) and **what grades** they get (MAE / RMSE).
  Models only see data from before the forecast semester, so there is no leakage from the future.
- **Grade metrics**: MAE, RMSE, calibration of P(grade ≥ 85).
- **Ranking metrics**: NDCG@k, Precision@k vs. courses the student actually did well in.
- **Main experiment**: error vs. number of real training transcripts, with / without synthetic pretraining.
- **Known bias**: grades are observed only for courses students chose (selection bias).

## Repository structure

```
data/
  catalog/        course catalog + prerequisite graph (public)
  synthetic/      generated transcripts (reproducible from code)
  real/           real transcripts — git-ignored, never pushed
docs/             proposal outline, notes, related work
notebooks/        EDA and experiments
presentations/    proposal / midterm / final slides (PPTX + PDF)
src/
  synthetic/      synthetic transcript generator
  models/         baselines and trained models
  evaluation/     metrics and evaluation protocol
```

## Quick start

```bash
pip install -r requirements.txt
python src/data/parse_maazan.py path/to/maazan.pdf --student-id S001   # -> data/real/S001/ (private)
python src/synthetic/generator.py --n-students 2000 --out data/synthetic/transcripts.csv
python src/data/expand_prefixes.py --data data/synthetic/transcripts.csv --out data/synthetic/samples.csv
python src/models/baselines.py --data data/synthetic/transcripts.csv
python src/evaluation/rolling_eval.py --data data/synthetic/transcripts.csv --max-k 4
```

## Milestones

| Week | Milestone |
|---|---|
| 5 | Proposal presentation |
| 8 | Midterm: baselines, first results, error analysis |
| 13 | Final presentation |
| 14–15 | Repository polish and submission |

## Academic balance app (no command line)

Double-click **`Maazan App.bat`** (or drag a מאזן לימודים PDF onto it) → the app opens with a course list
(**name · grade · credits · lecturer**), remaining credits per requirement and courses registered this year.
Lecturers are not in the PDF: double-click a course to type its lecturer — saved in `data/catalog/lecturers.csv`
and reused for every PDF; and **Save results**
writes CSV files that open in Excel. Runs locally; nothing is uploaded.

## Transcript collection page (web)

[`web/collect.html`](web/collect.html) is a page friends open from a link: they drop their מאזן לימודים PDF, it is
parsed **in their browser** ([`web/maazan-parse.js`](web/maazan-parse.js), a port of the Python parser, verified to
give identical output), they pick the 3 preferences (workload, exam/project, M.Sc./industry), consent, and submit.
Saved: name, track, courses, grades, credits, requirement progress, preferences. Never saved: ID number, the PDF.
Only the owner can read submissions and download them as CSV. Rebuild after editing the template or parser:
`collect.template.html` + `maazan-parse.js` → `collect.html`.
