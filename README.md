# Course Recommendation for Bar-Ilan Engineering using Real and Synthetic Transcripts

Grade-aware elective recommendation for students of the Bar-Ilan University Faculty of Engineering.
Given a student's partial transcript (courses, semesters, grades), track, and interests, the system
predicts the student's expected grade in each eligible course and recommends a ranked list of electives
that respects prerequisites and degree requirements.

## Research question

> With only a few dozen real transcripts, does pretraining on **calibrated synthetic transcripts** improve
> grade prediction and course recommendation for real students — and how large is the sim-to-real gap?

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
- **Course catalog** — courses, credits and prerequisites from the Bar-Ilan Engineering yearbook (שנתון).
- **Synthetic transcripts** — latent-skill generator calibrated to real grade statistics
  ([`src/synthetic/generator.py`](src/synthetic/generator.py)). Used for **training only**; the test set is 100% real.

## Evaluation

- **Temporal split**: hide each real student's last semester and predict it from earlier ones.
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
python src/synthetic/generator.py --n-students 2000 --out data/synthetic/transcripts.csv
python src/models/baselines.py --data data/synthetic/transcripts.csv
```

## Milestones

| Week | Milestone |
|---|---|
| 5 | Proposal presentation |
| 8 | Midterm: baselines, first results, error analysis |
| 13 | Final presentation |
| 14–15 | Repository polish and submission |
