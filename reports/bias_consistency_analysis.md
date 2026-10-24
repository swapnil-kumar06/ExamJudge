# Bias, Consistency and Metric Analysis

Judge: **offline keyword baseline** - temperature 0.0 - few-shot True

> Offline baseline run. A deterministic keyword judge is trivially repeatable and order-invariant, so the consistency tables below are **expected to be perfect and prove nothing about an LLM**. They exist to validate the test harness; re-run with an API key for the real analysis.

## 1. Repeatability (same input, same settings)

3 runs on student_2 -> totals [8.0, 8.0, 8.0]; std = 0.00, range = 0.00 marks. Target: std <= 0.25.

## 2. Criterion-order invariance (prompt-position bias over rubric items)

| Order | Total |
|---|---|
| original | 8 |
| reversed | 8 |
| shuffled | 8 |

Max change across orders: **0.0** marks. Target: <= 0.5.

## 3. Verbosity bias (irrelevant filler appended)

| Answer | Original | Padded | Delta | Words added |
|---|---|---|---|---|
| student_3 | 2.5 | 2.5 | +0.0 | 180 |
| student_4 | 8.5 | 8.5 | +0.0 | 180 |

A fair judge shows delta <= 0 (irrelevant text must never raise the mark).

## 4. Position consistency (pairwise A/B swap)

All 10 answer pairs were judged in both orders. **Consistency: 100%** (target >= 90%). Agreement of the consistent verdicts with human ranking: 80%.

| Pair | Winner (order 1) | Winner (order 2) | Consistent | Human winner |
|---|---|---|---|---|
| student_1 vs student_2 | student_1 | student_1 | yes | student_1 |
| student_1 vs student_3 | student_1 | student_1 | yes | student_1 |
| student_1 vs student_4 | student_1 | student_1 | yes | student_1 |
| student_1 vs student_5 | student_1 | student_1 | yes | student_1 |
| student_2 vs student_3 | student_2 | student_2 | yes | student_2 |
| student_2 vs student_4 | student_4 | student_4 | yes | student_2 |
| student_2 vs student_5 | student_2 | student_2 | yes | student_2 |
| student_3 vs student_4 | student_4 | student_4 | yes | student_3 |
| student_3 vs student_5 | student_3 | student_3 | yes | student_3 |
| student_4 vs student_5 | student_4 | student_4 | yes | student_4 |

## 5. Length bias

| | Pearson (words vs score) | Spearman |
|---|---|---|
| Automated | 0.96 | 1.00 |
| Human | 0.65 | 0.70 |

If the automated correlation is clearly higher than the human one, the judge is rewarding length. With n = 5 this is indicative only.
