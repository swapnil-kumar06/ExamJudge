# Project 05 — Deliverables checklist

## 1. Complete grading engine and file-upload dashboard

- `app.py` — Streamlit interface for PDF/TXT upload, pasted answers, rubric setup, score sheets and JSON/CSV exports.
- `engine/` — rubric normalization, LLM/offline grading, similarity metrics, benchmark statistics, PDF text extraction, and consistency/bias checks.
- The app supports a server-configured Gemini judge and an offline keyword-baseline mode. Offline scores are for demonstrations only, not reliable semantic grading.

## 2. Evaluator prompts and calibration

- `prompts/judge_system.md` — rubric, score bounds, evidence and feedback requirements.
- `prompts/few_shot.json` — calibration scoring examples.
- `prompts/calibration.md` — scoring bands and calibration guidance.
- `prompts/pairwise_system.md` — paired answer position-consistency prompt.

## 3. Benchmark evaluation report against five human-graded answers

- `reports/benchmark_report.md` and `reports/benchmark_scores.csv` are report placeholders until genuine data are supplied; the repository deliberately contains no fabricated human-comparison scores.
- In **Grade answers**, enter the target question, answer key and rubric. In **Benchmark vs human**, download the CSV template generated from that rubric, enter five de-identified scripts and independent human criterion marks, upload it, and confirm the marks are genuine. The resulting report compares those reference marks with automated scores and records the source/provenance status.
- A user confirmation is not an external audit; keep original grading records.

## 4. Project report with bias, position consistency, and metric analysis

- `reports/project_report.md` — project design, metric definitions, bias test methods, limitations, and reproduction instructions. Numeric results are populated after a real benchmark run.
- `reports/bias_consistency_analysis.md` — method template for repeatability, criterion-order, verbosity-padding, A/B position-swap, and length-correlation checks. Numeric values are generated from the uploaded five-answer dataset.
- To generate reports from a completed five-answer CSV from the project root (CLI uses the bundled sample question/model answer/rubric; the dashboard can use the active exam):

```powershell
python scripts/run_reports.py --provider offline --benchmark-csv data/benchmark/my_real_benchmark.csv --confirm-human-grades
```

For Gemini reports, configure `GEMINI_API_KEY` in the environment and replace `--provider offline` with `--provider gemini`. Live Gemini requests may consume API quota. The command overwrites the files under `reports/` with the new run's outputs.

## Validation

The repository includes pytest coverage for score normalization, prompt construction, metrics, offline grading, input validation, benchmark CSV validation, and bias-metric semantics. Run `python -m pytest -q` from the project root. Passing tests validates code paths, not grading accuracy; real-world accuracy requires independently graded reference data.
