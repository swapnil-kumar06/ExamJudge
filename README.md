# 🎓 ExamJudge - Automated Descriptive Exam Assessment Engine (LLM-as-a-Judge)

Upload student answer PDFs, a reference question, a model answer and a multi-criteria rubric. ExamJudge returns an itemised
score sheet, conceptual deficiencies and constructive feedback as structured JSON, using an **LLM judge** (evidence-based grading rationales,
`temperature = 0.0`) plus **BLEU / ROUGE** baselines from the Python `evaluate` library.

## Features
* Streamlit dashboard: PDF/TXT upload (batch), paste text, editable rubric table, one-click sample exam
* LLM-as-a-Judge: exact criteria and marks, concise evidence-based rationale-before-score, evidence quotes, deficiencies, feedback
* Temperature fixed at 0.0; scores clamped / rounded to 0.5 / totals recomputed in code
* BLEU, ROUGE-1/2/L (HF `evaluate`, pure-Python fallback) and cosine similarity shown next to every grade
* Gemini LLM judge through Google's OpenAI-compatible API; no arbitrary endpoint controls in the deployed UI
* **Works with no API key** through an offline keyword baseline (a weak demo-only heuristic; cannot detect wrong statements)
* **Security-first deployment:** Gemini key is server-side only, public UI has no key field, a shared app password is required if a Gemini key is configured, fixed provider endpoint, bounded uploads and per-session usage guard
* Benchmark tab: automated vs human marks (MAE, RMSE, Pearson, Spearman, within-N-marks, per-criterion error)
* Bias & consistency tab: repeatability, criterion-order invariance, verbosity bias, A/B position consistency, length bias
* JSON / CSV / Markdown exports

## Quick start (local)

Windows PowerShell:
```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .streamlit/secrets.toml.example .streamlit/secrets.toml
# Edit .streamlit/secrets.toml with GEMINI_API_KEY and a strong APP_PASSWORD
streamlit run app.py
```

macOS/Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Edit .streamlit/secrets.toml with GEMINI_API_KEY and a strong APP_PASSWORD
streamlit run app.py
```

For an offline-only demo, leave `GEMINI_API_KEY` and `APP_PASSWORD` blank. If a Gemini key is configured, the app requires an app password. Click **✨ Load sample exam** → **🚀 Grade**.

## Project layout
```
app.py                     Streamlit dashboard
engine/  judge.py          grading (LLM + offline baseline), JSON validation, pairwise judge
         prompts.py        prompt builders        llm_client.py  OpenAI-compatible client, T=0.0
         metrics.py        BLEU/ROUGE/cosine      pdf_utils.py   PDF text extraction
         benchmark.py      human-vs-auto study    analysis.py    bias & consistency checks
         stats.py, rubric.py, reporting.py
prompts/ judge_system.md   evaluator prompt (criteria, rationale protocol, calibration bands, JSON schema)
         few_shot.json     few-shot scoring examples      pairwise_system.md   position-consistency prompt
         calibration.md    calibration criteria & targets
data/    sample/           question, model answer, rubric      benchmark/  5 student answers (.txt + .pdf) + human marks
reports/ benchmark_report.md · bias_consistency_analysis.md · project_report.md · benchmark_scores.csv
scripts/run_reports.py     regenerates every report from a real run
tests/test_engine.py       unit tests (pytest)
```

## Deliverables map
| Deliverable | Where |
|---|---|
| Grading engine + upload dashboard | `app.py`, `engine/` |
| Evaluator prompts, few-shot, calibration | `prompts/` |
| Benchmark vs 5 human-graded answers | `reports/benchmark_report.md` (+ Benchmark tab) |
| Project report (bias, position consistency, metrics) | `reports/project_report.md`, `reports/bias_consistency_analysis.md` |

## ⚠️ Read this before submitting the reports
The reports currently in `reports/` were generated with the **offline keyword baseline** (no API key was available while
building) and the five benchmark answers / human marks are **illustrative sample data written for this repo**. To get real LLM numbers:
```bash
export GEMINI_API_KEY=...
python scripts/run_reports.py --provider gemini
```
This overwrites the three reports with LLM results. For a credible study replace `data/benchmark/` with real scripts graded by
humans (ideally two graders) and keep the same JSON format.

## Rubric format
`data/sample/rubric.json`: list of `{name, max_marks, description, keywords?}`. Keep descriptions concrete and checkable.

## Tests
`pip install pytest && pytest -q`

## Limitations
Scanned/handwritten PDFs need OCR first. LLM judges can err in niche domains - treat output as decision support. Free quotas
can be rate-limited, and model availability can change; the owner may change `GEMINI_MODEL` in Streamlit Secrets.

## Security notes
- The dashboard never displays or asks visitors to enter the server API key; it reads `GEMINI_API_KEY` from Streamlit Secrets/environment only.
- A configured Gemini key requires `APP_PASSWORD`. The endpoint and model configuration are not editable by visitors.
- This shared-password gate and per-session usage guard are basic safeguards, not enterprise authentication or a global rate limit. Apply provider-side quota limits and use anonymised student work.
