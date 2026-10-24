# Benchmark Evaluation Report

**Judge:** offline keyword baseline  
**Temperature:** 0.0  **Few-shot:** True  **Baseline metrics shown to judge:** False  
**Items:** 5 student answers, graded out of 10 marks.  
**BLEU/ROUGE backend:** pure-python fallback

> **Important:** this run used the *offline keyword baseline*, not an LLM. It is a lower-bound reference (it counts rubric concepts but cannot detect wrong statements). Re-run with an API key to benchmark the LLM judge: `python scripts/run_reports.py --provider gemini`.

> The five answers and human marks in `data/benchmark/` are **illustrative sample data** authored for this repository. Replace them with real double-graded scripts before drawing research conclusions.

## 1. Score comparison

| Student | Words | Human | Auto | Error (auto-human) | BLEU | ROUGE-L |
|---|---|---|---|---|---|---|
| student_1 | 174 | 9 | 10 | +1.0 | 0.337 | 0.641 |
| student_2 | 119 | 7.5 | 8 | +0.5 | 0.078 | 0.349 |
| student_3 | 83 | 3.5 | 2.5 | -1.0 | 0.018 | 0.164 |
| student_4 | 172 | 3 | 8.5 | +5.5 | 0.097 | 0.297 |
| student_5 | 38 | 0.5 | 0 | -0.5 | 0.002 | 0.126 |

## 2. Agreement statistics

| Metric | Value |
|---|---|
| MAE (marks) | 1.70 (17.0% of max) |
| RMSE (marks) | 2.56 |
| Mean signed error (+ = lenient) | +1.10 |
| Pearson r | 0.80 |
| Spearman rho | 0.70 |
| Within 0.5 mark | 40% |
| Within 1.0 mark | 80% |

## 3. Per-criterion mean absolute error

| Criterion | MAE (marks) |
|---|---|
| Technical Accuracy | 1.10 |
| Completeness | 0.60 |
| Nomenclature | 0.40 |

## 4. Can BLEU / ROUGE-L grade on their own?

| Metric | Pearson vs human | Spearman vs human |
|---|---|---|
| BLEU | 0.79 | 0.70 |
| ROUGE-L | 0.88 | 0.90 |

With only 5 items these correlations are unstable. A more telling check is pairwise ordering: ROUGE-L orders 1 of 10 answer pairs differently from the human graders (e.g. student_3 vs student_4). Lexical overlap rewards wording that matches the model answer, so correct paraphrases score low and long answers that reuse the right words but state wrong facts can score high. BLEU/ROUGE are therefore used here as baseline features, not as the grade.
