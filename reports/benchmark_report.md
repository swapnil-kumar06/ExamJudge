# Benchmark Evaluation Report — Pending Real Human-Graded Dataset

**Status: NOT YET RUN AGAINST GENUINE HUMAN-GRADED ANSWERS.**

The project intentionally does not include fabricated benchmark results. The bundled TCP congestion-control answers and example marks are illustrative test fixtures only. They are not evidence of agreement with human examiners.

## How to generate the formal report

1. In the dashboard's **Grade answers** tab, enter the exam question, model answer, and marking rubric.
2. Download the blank five-answer CSV template from **Benchmark vs human**.
3. Replace the rows with five de-identified answer scripts and independently assigned human marks for each rubric criterion.
4. Upload the completed CSV and confirm the marks were independently assigned by a human evaluator.
5. Run the benchmark and download the generated report. The report will include each reference total, automated total, signed error, MAE, RMSE, Pearson/Spearman correlations (where defined), within-tolerance rates, per-criterion MAE, and BLEU/ROUGE correlations.

## Metrics reported by the application

- **MAE:** average absolute difference between automated and human total marks.
- **RMSE:** penalizes larger grading errors more heavily.
- **Mean signed error:** positive values mean the automated grader is more lenient.
- **Pearson and Spearman:** linear and rank association; may be `n/a` with too few distinct score values.
- **Within tolerance:** percentage of answers whose automated total is within 0.5 or 1.0 marks of the human total.
- **BLEU/ROUGE:** lexical-overlap baselines only; not measures of factual correctness.

A user confirmation is an attestation, not an independent audit. Five answers are enough for a small course demonstration but not to establish general reliability. Keep the original human marking records and have a human examiner review automated results.
