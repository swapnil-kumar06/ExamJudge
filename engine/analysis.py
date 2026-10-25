"""Reliability & bias checks for the judge: repeatability, criteria-order invariance,
verbosity bias, position consistency (pairwise A/B swap), length-score correlation."""
from __future__ import annotations
import itertools
import random
import numpy as np

from .judge import JudgeConfig, grade_answer, pairwise_winner
from .stats import pearson, spearman

FILLER = (" It is also important to note that networking is a very broad and interesting field with many "
          "layers, protocols and devices, and that engineers have studied these systems for many decades. "
          "In general, the performance of computer systems depends on many different factors, and a careful "
          "and comprehensive discussion of all of them would be useful in a wider context.")


def repeatability(student, sample, cfg: JudgeConfig, n=3) -> dict:
    totals = [grade_answer(student, sample["question"], sample["model_answer"], sample["rubric"], cfg)["total"]
              for _ in range(n)]
    return {"runs": n, "totals": totals, "std": float(np.std(totals)), "range": float(max(totals) - min(totals))}


def criteria_order_invariance(student, sample, cfg: JudgeConfig, seed=7) -> dict:
    k = len(sample["rubric"])
    base = list(range(k))
    orders = {"original": base, "reversed": base[::-1]}
    rnd = random.Random(seed)
    shuffled = base[:]
    rnd.shuffle(shuffled)
    orders["shuffled"] = shuffled
    totals = {name: grade_answer(student, sample["question"], sample["model_answer"], sample["rubric"], cfg,
                                 shuffle_rubric=o)["total"] for name, o in orders.items()}
    return {"totals": totals, "max_delta": float(max(totals.values()) - min(totals.values()))}


def verbosity_bias(student, sample, cfg: JudgeConfig, repeats=3) -> dict:
    base = grade_answer(student, sample["question"], sample["model_answer"], sample["rubric"], cfg)["total"]
    padded_text = student + FILLER * repeats
    padded = grade_answer(padded_text, sample["question"], sample["model_answer"], sample["rubric"], cfg)["total"]
    return {"original_total": base, "padded_total": padded, "delta": padded - base,
            "words_added": len(padded_text.split()) - len(student.split())}


def position_consistency(students: list[dict], sample, cfg: JudgeConfig, progress=None) -> dict:
    """Compare pairwise winners after swapping answer positions.

    Human winners are deliberately suppressed unless the dataset was explicitly
    confirmed as independently human-graded; bundled illustrative marks must not
    be presented as observed human judgments.
    """
    pairs = list(itertools.combinations(range(len(students)), 2))
    rows, consistent = [], 0
    is_real = bool(students) and all(bool(s.get("human_data_is_real", False)) for s in students)
    for n, (i, j) in enumerate(pairs):
        a, b = students[i], students[j]
        w1 = pairwise_winner(sample["question"], sample["model_answer"], sample["rubric"], a["text"], b["text"], cfg)
        w2 = pairwise_winner(sample["question"], sample["model_answer"], sample["rubric"], b["text"], a["text"], cfg)
        first = {"A": a["id"], "B": b["id"], "TIE": "TIE"}[w1]
        second = {"A": b["id"], "B": a["id"], "TIE": "TIE"}[w2]
        ok = first == second
        consistent += int(ok)
        human_winner = None
        agrees = None
        if is_real:
            human_winner = (a["id"] if a["human_total"] > b["human_total"] else
                            b["id"] if b["human_total"] > a["human_total"] else "TIE")
            # Measure agreement separately from position consistency; do not conflate two different properties.
            agrees = (first == human_winner)
        rows.append({
            "pair": f"{a['id']} vs {b['id']}",
            "order_1_winner": first,
            "order_2_winner": second,
            "consistent": ok,
            "human_winner": human_winner if is_real else "n/a (unverified grades)",
            "agrees_with_human": agrees,
        })
        if progress:
            progress((n + 1) / len(pairs))
    return {
        "rows": rows,
        "pairs": len(pairs),
        "consistency_rate": consistent / len(pairs) if pairs else float("nan"),
        "human_agreement_rate": (sum(bool(r["agrees_with_human"]) for r in rows) / len(pairs))
        if pairs and is_real else None,
    }


def length_bias(df, reference_verified: bool = False) -> dict:
    """Correlate answer length with automated marks; reference correlations require attested human data."""
    unverified = float("nan")
    return {"auto_vs_length_pearson": pearson(df["words"], df["auto_total"]),
            "human_vs_length_pearson": pearson(df["words"], df["human_total"]) if reference_verified else unverified,
            "auto_vs_length_spearman": spearman(df["words"], df["auto_total"]),
            "human_vs_length_spearman": spearman(df["words"], df["human_total"]) if reference_verified else unverified}


def run_all(cfg: JudgeConfig, sample, bench, bench_result, repeats=3, progress=None) -> dict:
    students = bench["students"]
    # Propagate whether human marks are genuine so the analysis cannot accidentally
    # present bundled illustrative grades as real human agreement.
    for student in students:
        student["human_data_is_real"] = bool(bench.get("human_data_is_real", False))
    mid = students[1]["text"]
    repeat_result = repeatability(mid, sample, cfg, n=repeats)
    repeat_result["student_id"] = students[1]["id"]
    out = {
        "repeatability": repeat_result,
        "order": criteria_order_invariance(mid, sample, cfg),
        "verbosity": {s["id"]: verbosity_bias(s["text"], sample, cfg) for s in (students[2], students[3])},
        "position": position_consistency(students, sample, cfg, progress=progress),
        "length": length_bias(bench_result["df"], reference_verified=bool(bench.get("human_data_is_real", False))),
    }
    return out
