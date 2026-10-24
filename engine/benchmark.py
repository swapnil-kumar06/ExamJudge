"""Benchmark: automated scores vs human-graded answers."""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

from .judge import JudgeConfig, grade_answer
from .rubric import load_rubric, clean_rubric
from .stats import agreement

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "sample"
BENCH = ROOT / "data" / "benchmark"


def load_sample() -> dict:
    return {"question": (SAMPLE / "question.txt").read_text(encoding="utf-8").strip(),
            "model_answer": (SAMPLE / "model_answer.txt").read_text(encoding="utf-8").strip(),
            "rubric": load_rubric(str(SAMPLE / "rubric.json"))}


def load_benchmark() -> dict:
    meta = json.loads((BENCH / "human_grades.json").read_text(encoding="utf-8"))
    for s in meta["students"]:
        s["text"] = (BENCH / "student_answers" / s["file"]).read_text(encoding="utf-8").strip()
        s["human_total"] = sum(s["human"].values())
    return meta


def run_benchmark(cfg: JudgeConfig, sample=None, bench=None, progress=None):
    sample = sample or load_sample()
    bench = bench or load_benchmark()
    rows, results = [], {}
    for i, s in enumerate(bench["students"]):
        res = grade_answer(s["text"], sample["question"], sample["model_answer"], sample["rubric"], cfg)
        results[s["id"]] = res
        row = {"student": s["id"], "words": res["metrics"]["word_count"],
               "human_total": s["human_total"], "auto_total": res["total"],
               "error": res["total"] - s["human_total"],
               "BLEU": res["metrics"]["bleu"], "ROUGE-L": res["metrics"]["rougeL"]}
        for c in res["criteria"]:
            row[f"human_{c['name']}"] = s["human"].get(c["name"], float("nan"))
            row[f"auto_{c['name']}"] = c["score"]
        rows.append(row)
        if progress:
            progress((i + 1) / len(bench["students"]))
    df = pd.DataFrame(rows)
    stats = agreement(df["auto_total"], df["human_total"], bench["max_total"])
    per_crit = {}
    for rc in sample["rubric"]:
        n = rc["name"]
        per_crit[n] = float((df[f"auto_{n}"] - df[f"human_{n}"]).abs().mean())
    # metrics vs human correlation (are BLEU/ROUGE useful graders on their own?)
    from .stats import pearson, spearman
    metric_corr = {m: {"pearson": pearson(df[m], df["human_total"]), "spearman": spearman(df[m], df["human_total"])}
                   for m in ("BLEU", "ROUGE-L")}
    return {"df": df, "stats": stats, "per_criterion_mae": per_crit,
            "metric_corr": metric_corr, "results": results, "max_total": bench["max_total"],
            "judge": next(iter(results.values()))["judge"]}


def _discordant(df, col):
    import itertools
    bad, tot, ex = 0, 0, []
    for i, j in itertools.combinations(range(len(df)), 2):
        h = df["human_total"].iloc[i] - df["human_total"].iloc[j]
        m = df[col].iloc[i] - df[col].iloc[j]
        if h == 0:
            continue
        tot += 1
        if h * m < 0:
            bad += 1
            ex.append(f"{df['student'].iloc[i]} vs {df['student'].iloc[j]}")
    return bad, tot, ex


def _f(x, nd=2):
    return "n/a" if x != x else f"{x:.{nd}f}"


def render_benchmark_markdown(b: dict, cfg: JudgeConfig) -> str:
    df, st = b["df"], b["stats"]
    L = ["# Benchmark Evaluation Report", "",
         f"**Judge:** {b['judge']}  ",
         f"**Temperature:** 0.0  **Few-shot:** {cfg.few_shot}  **Baseline metrics shown to judge:** {cfg.include_metrics}  ",
         f"**Items:** {st['n']} student answers, graded out of {b['max_total']:g} marks.  ",
         f"**BLEU/ROUGE backend:** {next(iter(b['results'].values()))['metrics']['backend']}", ""]
    if cfg.offline:
        L += ["> **Important:** this run used the *offline keyword baseline*, not an LLM. It is a lower-bound reference "
              "(it counts rubric concepts but cannot detect wrong statements). Re-run with an API key to benchmark the "
              "LLM judge: `python scripts/run_reports.py --provider gemini`.", ""]
    L += ["> The five answers and human marks in `data/benchmark/` are **illustrative sample data** authored for this "
          "repository. Replace them with real double-graded scripts before drawing research conclusions.", "",
          "## 1. Score comparison", "",
          "| Student | Words | Human | Auto | Error (auto-human) | BLEU | ROUGE-L |", "|---|---|---|---|---|---|---|"]
    for _, r in df.iterrows():
        L.append(f"| {r['student']} | {int(r['words'])} | {r['human_total']:g} | {r['auto_total']:g} | "
                 f"{r['error']:+.1f} | {r['BLEU']:.3f} | {r['ROUGE-L']:.3f} |")
    L += ["", "## 2. Agreement statistics", "", "| Metric | Value |", "|---|---|",
          f"| MAE (marks) | {_f(st['MAE'])} ({_f(st['MAE_pct_of_max'],1)}% of max) |",
          f"| RMSE (marks) | {_f(st['RMSE'])} |",
          f"| Mean signed error (+ = lenient) | {st['mean_signed_error']:+.2f} |",
          f"| Pearson r | {_f(st['pearson'])} |",
          f"| Spearman rho | {_f(st['spearman'])} |",
          f"| Within 0.5 mark | {st['within_0.5']*100:.0f}% |",
          f"| Within 1.0 mark | {st['within_1.0']*100:.0f}% |", "",
          "## 3. Per-criterion mean absolute error", "", "| Criterion | MAE (marks) |", "|---|---|"]
    for k, v in b["per_criterion_mae"].items():
        L.append(f"| {k} | {v:.2f} |")
    L += ["", "## 4. Can BLEU / ROUGE-L grade on their own?", "",
          "| Metric | Pearson vs human | Spearman vs human |", "|---|---|---|"]
    for k, v in b["metric_corr"].items():
        L.append(f"| {k} | {_f(v['pearson'])} | {_f(v['spearman'])} |")
    disc = _discordant(df, "ROUGE-L")
    L += ["", f"With only {st['n']} items these correlations are unstable. A more telling check is pairwise ordering: "
          f"ROUGE-L orders {disc[0]} of {disc[1]} answer pairs differently from the human graders"
          + (f" (e.g. {', '.join(disc[2][:3])})." if disc[2] else ".") +
          " Lexical overlap rewards wording that matches the model answer, so correct paraphrases score low and long "
          "answers that reuse the right words but state wrong facts can score high. BLEU/ROUGE are therefore used here "
          "as baseline features, not as the grade."]
    return "\n".join(L) + "\n"
