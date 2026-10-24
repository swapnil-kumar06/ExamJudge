# Calibration criteria for the evaluator

The judge is calibrated by (a) explicit score bands in `judge_system.md`, (b) two few-shot
examples at the top and bottom of the scale (`few_shot.json`), and (c) the checks below,
which should be re-run whenever the prompt, model or rubric changes.

| Check | How | Target |
|---|---|---|
| Repeatability | grade the same answer N times at T=0.0 | std-dev of total <= 0.25 marks |
| Criterion-order invariance | reverse / shuffle criteria order in the prompt | max change in total <= 0.5 marks |
| Verbosity invariance | append fluent but irrelevant filler to an answer | score must not rise (delta <= 0) |
| Position consistency | pairwise comparison with A/B swapped | >= 90% same winner |
| Human agreement | MAE / Pearson / Spearman vs. human marks on benchmark set | MAE <= 1.0 of 10, Spearman >= 0.8 |
| Anchor drift | grade the few-shot "good" and "poor" answers | within 0.5 marks of the anchor total |

Rules of thumb for graders using the platform
* Edit rubric `description` text to be concrete and checkable ("names slow start AND states that cwnd doubles each RTT"), not vague ("good explanation").
* Keep each criterion independent - do not make "Completeness" depend on "Accuracy".
* Keep temperature at 0.0. Provider-side non-determinism can still cause +/-0.5 mark jitter; quantify it with the Repeatability check.
* Re-calibrate (adjust descriptions/few-shot) if the judge is systematically more lenient or harsh than humans: check the mean signed error in the benchmark.
