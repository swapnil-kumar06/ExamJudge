"""Markdown report builders shared by the CLI and the dashboard."""
from __future__ import annotations
import datetime


def nan(x):
    try:
        value = float(x)
    except (TypeError, ValueError):
        return "n/a"
    return "n/a" if value != value else f"{value:.2f}"


def bias_markdown(a, cfg, b):
    r, o, p, ln = a["repeatability"], a["order"], a["position"], a["length"]
    L = ["# Bias, Consistency and Metric Analysis", "",
         f"Judge: **{b['judge']}** - temperature 0.0 - few-shot {cfg.few_shot}",
         f"Dataset source: **{b.get('data_source', 'unknown source')}**", ""]
    if not b.get("human_data_is_real", False):
        L += ["> Human reference marks are illustrative or unverified. The report must not be presented as a real human-agreement study.", ""]
    else:
        L += ["> The application user confirmed that the reference marks were independently assigned. This declaration has not been independently audited.", ""]
    if cfg.offline:
        L += ["> Offline baseline run. A deterministic keyword judge is trivially repeatable and order-invariant, so the "
              "consistency tables below are **expected to be perfect and prove nothing about an LLM**. They exist to "
              "validate the test harness; re-run with an API key for the real analysis.", ""]
    L += ["## 1. Repeatability (same input, same settings)", "",
          f"{r['runs']} runs on {r.get('student_id', 'selected answer')} -> totals {r['totals']}; std = {r['std']:.2f}, range = {r['range']:.2f} marks. Target: std <= 0.25.", "",
          "## 2. Criterion-order invariance (prompt-position bias over rubric items)", "",
          "| Order | Total |", "|---|---|"] + [f"| {k} | {v:g} |" for k, v in o["totals"].items()] + \
         ["", f"Max change across orders: **{o['max_delta']:.1f}** marks. Target: <= 0.5.", "",
          "## 3. Verbosity bias (irrelevant filler appended)", "",
          "| Answer | Original | Padded | Delta | Words added |", "|---|---|---|---|---|"] + \
         [f"| {k} | {v['original_total']:g} | {v['padded_total']:g} | {v['delta']:+.1f} | {v['words_added']} |" for k, v in a["verbosity"].items()] + \
         ["", "A fair judge shows delta <= 0 (irrelevant text must never raise the mark).", "",
          "## 4. Position consistency (pairwise A/B swap)", "",
          f"All {p['pairs']} answer pairs were judged in both orders. **Consistency: {p['consistency_rate']*100:.0f}%** "
          f"(target >= 90%). Reference-ranking agreement: "
          f"{('n/a (illustrative human grades)' if p.get('human_agreement_rate') is None else f"{p['human_agreement_rate']*100:.0f}%")}.", "",
          "| Pair | Winner (order 1) | Winner (order 2) | Consistent | Reference winner |", "|---|---|---|---|---|"] + \
         [f"| {x['pair']} | {x['order_1_winner']} | {x['order_2_winner']} | {'yes' if x['consistent'] else 'NO'} | {x['human_winner']} |" for x in p["rows"]] + \
         ["", "## 5. Length bias", "",
          "| | Pearson (words vs score) | Spearman |", "|---|---|---|",
          f"| Automated | {nan(ln['auto_vs_length_pearson'])} | {nan(ln['auto_vs_length_spearman'])} |",
          f"| {'Independent human reference' if b.get('human_data_is_real', False) else 'Illustrative reference (not human-graded)'} | {nan(ln['human_vs_length_pearson'])} | {nan(ln['human_vs_length_spearman'])} |", "",
          "A much higher automated correlation than the independently graded reference can indicate length bias. "
          "When the reference marks are illustrative or unverified, this comparison is demonstration-only. With n = 5 it is unstable either way."]
    return "\n".join(L) + "\n"


def project_markdown(b, a, cfg):
    st = b["stats"]
    return f"""# Project Report - Automated Descriptive Exam Assessment Engine (LLM-as-a-Judge)

_Generated {datetime.date.today().isoformat()} - judge used for the numbers: **{b['judge']}**; dataset source: **{b.get('data_source', 'unknown source')}**._

> **Human-mark provenance:** {('user-confirmed independently assigned marks; original grading records should be retained' if b.get('human_data_is_real', False) else 'illustrative or unverified reference marks; numeric agreement statistics are demonstration outputs, not evidence of human-study accuracy')}.

## 1. Problem and objectives
Manual grading of long-form answers is slow and subject to evaluator bias. The goal is a transparent, auditable platform that
grades a student answer against an official question, model answer and multi-criteria rubric, returns an itemised score sheet,
conceptual deficiencies and improvement feedback as structured JSON, and quantifies its own reliability.

## 2. System design
```
PDF/TXT upload -> text extraction (pypdf) -> BLEU / ROUGE / cosine baseline (HF evaluate)
                                         \\-> judge prompt (rubric + model answer + few-shot) -> LLM, T=0.0
                                                -> JSON validation (clamp, round to 0.5, recompute total)
                                                -> score sheet, deficiencies, feedback (+ JSON/CSV export)
```
* **LLM-as-a-Judge:** the system prompt (`prompts/judge_system.md`) states the exact criteria and marks, forbids rewarding length,
  treats the student text as untrusted data (prompt-injection defence) and asks for a concise evidence-based rationale before each criterion score.
* **Sampling control:** temperature is hard-wired to 0.0 in `engine/judge.py` to reduce sampling variability; hosted-model responses are not guaranteed to be identical across calls.
* **Calibration:** explicit score bands plus two few-shot examples (good / poor) on a different question so no benchmark item leaks (`prompts/few_shot.json`, `prompts/calibration.md`).
* **Baseline metrics:** BLEU, ROUGE-1/2/L via the Python `evaluate` library (pure-Python fallback if the hub is unreachable) and cosine similarity.
  They are shown next to the grade and optionally given to the judge; by default they are *not* given, to avoid anchoring.
* **Validation layer:** the application never trusts the model's arithmetic: criteria are matched to the rubric by name, scores are clamped to [0, max], rounded to half marks and totals recomputed.
* **Offline baseline:** a keyword-coverage grader lets the app run (and be tested) with no API key. It is a lower bound, not a substitute for the LLM.

## 3. Metric evaluation (summary)
{render_summary(b)}
Full tables: `reports/benchmark_report.md`.

## 4. Bias and consistency analysis (summary)
* Repeatability: std {a['repeatability']['std']:.2f} marks over {a['repeatability']['runs']} runs.
* Criterion-order invariance: max change {a['order']['max_delta']:.1f} marks.
* Verbosity: padding deltas {', '.join(f"{k}: {v['delta']:+.1f}" for k, v in a['verbosity'].items())}.
* Position consistency (A/B swap): {a['position']['consistency_rate']*100:.0f}% of {a['position']['pairs']} pairs.
* Length-score correlation: automated {nan(a['length']['auto_vs_length_pearson'])} vs {('independent reference' if b.get('human_data_is_real', False) else 'illustrative reference')} {nan(a['length']['human_vs_length_pearson'])}.
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
* The bundled five benchmark answers and reference marks are **illustrative sample data**. If a custom dataset is used, the report records the uploaded source and user confirmation; that declaration is not an external audit. With n = 5 any correlation is statistically weak; use the harness on a larger set of real scripts with two human graders and report inter-rater agreement first.
* Scanned or handwritten PDFs need OCR before upload; the app reports this instead of guessing.
* LLM judges can still make factual mistakes in niche domains; this is a decision-support tool and every score sheet is auditable (reasoning + evidence quotes) so a human examiner can override.
* Gemini quotas can rate-limit requests; model availability can change. The app owner controls the model through the `GEMINI_MODEL` secret.

## 7. Reproduce
`GEMINI_API_KEY=... python scripts/run_reports.py --provider gemini` regenerates reports using Gemini. The included default reports use the offline baseline and illustrative sample data.
"""


def render_summary(b):
    st = b["stats"]
    reference_label = "independent reference" if b.get("human_data_is_real", False) else "illustrative reference (not human-study evidence)"
    return (f"**Reference data:** {reference_label}.\n\n"
            f"| MAE | RMSE | Pearson | Spearman | Within 1 mark | Mean signed error |\n|---|---|---|---|---|---|\n"
            f"| {st['MAE']:.2f} | {st['RMSE']:.2f} | {nan(st['pearson'])} | {nan(st['spearman'])} | {st['within_1.0']*100:.0f}% | {st['mean_signed_error']:+.2f} |\n"
            f"BLEU/ROUGE-L vs reference Spearman: BLEU {nan(b['metric_corr']['BLEU']['spearman'])}, ROUGE-L {nan(b['metric_corr']['ROUGE-L']['spearman'])}.\n")


