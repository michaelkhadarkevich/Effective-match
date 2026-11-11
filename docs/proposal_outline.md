# Proposal Presentation — Outline

Follows the course guide *Project Proposal Presentation* (six required parts + checklist).

## 1. Motivating use case
- Who: Bar-Ilan Engineering students choosing electives each semester.
- Today: word of mouth, WhatsApp groups, the yearbook, academic advisors.
- Why hard: prerequisites, workload balance, fit between course demands and the student's strengths.
- **TODO evidence**: short classmate survey (how electives are chosen, regret rate), failure/drop statistics,
  existing recommenders at other universities and their limitations.

## 2. Task
Input: partial transcript + track + interests → Output: ranked eligible electives with predicted grade
and explanation. Constraints: prerequisites, degree requirements, privacy.
Worked example slide: one anonymized student → top-3 recommendations.

## 3. Novelty
- Prior work: grade prediction (matrix factorization, IRT), knowledge tracing, course recommenders.
- Gap: real transcript data is tiny and sensitive.
- Contribution: calibrated synthetic transcript generator + measured synthetic→real transfer study.
- **TODO**: find 2–3 papers on grade prediction / course recommendation.

## 4. Models and methods
Pipeline: preprocessing → eligibility filter → grade predictor → ranker → explanation.
Baselines (course mean, student + offset) · MF / IRT · GRU/Transformer sequence model (trained) ·
LLM zero-shot (comparison only). Justify each vs. alternatives.

## 5. Data
- Real: N consenting students (target 40–100), anonymized, local only.
- Catalog: yearbook courses + prerequisites → graph.
- Synthetic: latent-skill generator (`src/synthetic/generator.py`); controlled attributes, diversity,
  realism checks (distribution match, correlations, 8-objective EDA checklist). Test set = real only.
- Risks: small N, selection bias, privacy, sim-to-real gap, leakage.

## 6. Evaluation
- Temporal split: predict each real student's last semester.
- MAE / RMSE / calibration; NDCG@k, Precision@k.
- Main plot: error vs. #real transcripts, with vs. without synthetic pretraining.
- Success criterion (fixed in advance): e.g. ≥15% MAE reduction vs. course-mean baseline on real test set.

## Checklist
- [ ] Use case specific and evidence-based
- [ ] Input / output / task / users / constraints defined
- [ ] Contribution grounded in prior work
- [ ] Full pipeline, not one model call
- [ ] Trained model included
- [ ] Data source, size, labels, splits
- [ ] Synthetic data need / control / validation explained
- [ ] Baseline + success criterion
- [ ] Metrics justified
- [ ] Example inputs/outputs shown, risks named
