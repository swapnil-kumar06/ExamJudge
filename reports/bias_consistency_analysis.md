# Bias, Consistency and Metric Analysis — Pending Real Run

**Status: no numeric claims are published here because no genuine human-graded five-answer dataset has been supplied.**

The dashboard implements these tests on the same five answers and active exam setup used by the benchmark:

1. **Repeatability:** grade the same answer repeatedly with identical settings; report the total-score standard deviation and range.
2. **Criterion-order sensitivity:** rerun with original, reversed, and shuffled rubric criteria; report the maximum total-score difference.
3. **Verbosity bias:** append a fixed block of irrelevant filler and measure the change in grade. A positive delta is a warning sign.
4. **Position consistency:** compare each pair of answers in both A/B orders. Position consistency is the proportion of pairs with the same winning answer after swapping positions.
5. **Human pairwise agreement:** compare pairwise winners with human-reference total marks; this is reported only for a user-confirmed human-grade dataset.
6. **Length correlation:** report Pearson/Spearman association between answer word count and automated marks. This is descriptive and unstable at n=5.

## Interpretation safeguards

- The offline keyword baseline is deterministic; perfect repeatability or position consistency validates only the test harness, not LLM reliability.
- Temperature 0.0 reduces sampling variability but does not guarantee identical hosted-model results.
- Position consistency and agreement with human rankings are different measures and are calculated separately.
- Do not make general fairness claims from five answers. A stronger study should use more scripts and at least two independent human graders, then report inter-rater agreement.

Run **Bias & consistency** after uploading and confirming a genuine five-answer benchmark to produce the numeric results for this dataset.
