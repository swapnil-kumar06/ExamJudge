# Project Report - Automated Descriptive Exam Assessment Engine (LLM-as-a-Judge)

_Generated 2026-10-24 by `scripts/run_reports.py` - judge used for the numbers: **offline keyword baseline**._

## 1. Problem and objectives
Manual grading of long-form answers is slow and subject to evaluator bias. The goal is a transparent, auditable platform that
grades a student answer against an official question, model answer and multi-criteria rubric, returns an itemised score sheet,
conceptual deficiencies and improvement feedback as structured JSON, and quantifies its own reliability.

## 2. System design
```
PDF/TXT upload -> text extraction (pypdf) -> BLEU / ROUGE / cosine baseline (HF evaluate)
                                         \-> judge prompt (rubric + model answer + few-shot) -> LLM, T=0.0
                                                -> JSON validation (clamp, round to 0.5, recompute total)
                                                -> score sheet, deficiencies, feedback (+ JSON/CSV export)
```
* **LLM-as-a-Judge:** the system prompt (`prompts/judge_system.md`) states the exact criteria and marks, forbids rewarding length,
  treats the student text as untrusted data (prompt-injection defence) and asks for a concise evidence-based rationale before each criterion score.
* **Determinism:** temperature is hard-wired to 0.0 in `engine/judge.py`.
* **Calibration:** explicit score bands plus two few-shot examples (good / poor) on a different question so no benchmark item leaks (`prompts/few_shot.json`, `prompts/calibration.md`).
* **Baseline metrics:** BLEU, ROUGE-1/2/L via the Python `evaluate` library (pure-Python fallback if the hub is unreachable) and cosine similarity.
  They are shown next to the grade and optionally given to the judge; by default they are *not* given, to avoid anchoring.
* **Validation layer:** the application never trusts the model's arithmetic: criteria are matched to the rubric by name, scores are clamped to [0, max], rounded to half marks and totals recomputed.
* **Offline baseline:** a keyword-coverage grader lets the app run (and be tested) with no API key. It is a lower bound, not a substitute for the LLM.

## 3. Metric evaluation (summary)
| MAE | RMSE | Pearson | Spearman | Within 1 mark | Mean signed error |
|---|---|---|---|---|---|
| 1.70 | 2.56 | 0.80 | 0.70 | 80% | +1.10 |
BLEU/ROUGE-L vs human Spearman: BLEU 0.70, ROUGE-L 0.90.

Full tables: `reports/benchmark_report.md`.

## 4. Bias and consistency analysis (summary)
* Repeatability: std 0.00 marks over 3 runs.
* Criterion-order invariance: max change 0.0 marks.
* Verbosity: padding deltas student_3: +0.0, student_4: +0.0.
* Position consistency (A/B swap): 100% of 10 pairs.
* Length-score correlation: automated 0.96 vs human 0.65.
Full tables: `reports/bias_consistency_analysis.md`.

## 5. Bias taxonomy and mitigations
| Bias | Risk | Mitigation in this project | Test |
|---|---|---|---|
| Verbosity / length | Longer answers score higher | Prompt rule 3; rubric-based scoring; keyword-stuffing is the offline baseline's known failure | Padding test, length correlation |
| Position (pairwise) | Judge prefers first/second answer | Pairwise verdicts evaluated in both orders | A/B swap consistency |
| Criterion-order / halo | Earlier criteria colour later ones | Independent-criteria rule; order shuffling | Order invariance |
| Self-preference / style | Judge favours fluent, model-like text | Judge never sees which answers are human; no style marks | Compare with human on paraphrased answers |
| Leniency / severity | Systematically high or low marks | Calibration bands, few-shot anchors | Mean signed error |
| Prompt injection | Answer text tries to change grading | Student text delimited as data + rule 2 | Manual red-team (add "give full marks" to an answer) |
| Run-to-run noise | Different marks per run | T = 0.0, JSON validation | Repeatability |

## 6. Limitations and honest caveats
* The five benchmark answers and human marks shipped here are **illustrative sample data**. With n = 5 any correlation is statistically weak; use the harness on >= 30 real scripts with two human graders and report inter-rater agreement (e.g. Cohen's kappa) first.
* Scanned or handwritten PDFs need OCR before upload; the app reports this instead of guessing.
* LLM judges can still make factual mistakes in niche domains; this is a decision-support tool and every score sheet is auditable (reasoning + evidence quotes) so a human examiner can override.
* Gemini quotas can rate-limit requests; model availability can change. The app owner controls the model through the `GEMINI_MODEL` secret.

## 7. Reproduce
`GEMINI_API_KEY=... python scripts/run_reports.py --provider gemini` regenerates reports using Gemini. The included default reports use the offline baseline and illustrative sample data.
