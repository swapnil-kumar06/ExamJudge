"""Benchmark utilities: automated scores compared with human reference marks.

The bundled data is illustrative only. For a real evaluation, provide exactly five
independently human-graded answers via the benchmark CSV template.
"""
from __future__ import annotations

import copy
import io
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .judge import JudgeConfig, grade_answer
from .rubric import load_rubric
from .stats import agreement, pearson, spearman

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "sample"
BENCH = ROOT / "data" / "benchmark"
REQUIRED_BASE_COLUMNS = ("student", "answer")


def load_sample() -> dict:
    return {
        "question": (SAMPLE / "question.txt").read_text(encoding="utf-8").strip(),
        "model_answer": (SAMPLE / "model_answer.txt").read_text(encoding="utf-8").strip(),
        "rubric": load_rubric(str(SAMPLE / "rubric.json")),
    }


def load_benchmark() -> dict:
    """Load the bundled *illustrative* dataset. It is never real human-study data."""
    meta = json.loads((BENCH / "human_grades.json").read_text(encoding="utf-8"))
    students = []
    for source in meta["students"]:
        student = copy.deepcopy(source)
        student["text"] = (BENCH / "student_answers" / student["file"]).read_text(encoding="utf-8").strip()
        student["human_total"] = sum(float(v) for v in student["human"].values())
        student["human_data_is_real"] = False
        students.append(student)
    meta["students"] = students
    meta["human_data_is_real"] = False
    meta["human_data_note"] = meta.get(
        "note", "Illustrative data bundled with the project; not independently human-graded."
    )
    meta["source"] = "bundled illustrative sample"
    if "max_total" not in meta:
        meta["max_total"] = sum(c["max_marks"] for c in load_sample()["rubric"])
    return meta


def benchmark_template_csv(rubric: list[dict], n_students: int = 5) -> str:
    """Return a blank CSV template for a five-answer independently graded benchmark."""
    if n_students != 5:
        raise ValueError("The project benchmark deliverable expects exactly five student answers.")
    cols = ["student", "answer"] + [c["name"] for c in rubric]
    rows = [{"student": f"student_{i}", "answer": "", **{c["name"]: "" for c in rubric}}
            for i in range(1, n_students + 1)]
    return pd.DataFrame(rows, columns=cols).to_csv(index=False)


def parse_benchmark_csv(content: bytes | str, rubric: list[dict]) -> dict:
    """Validate a user-supplied five-answer CSV. It does not attest that marks are genuine.

    Expected columns: student, answer, and one numeric column whose header exactly
    matches every rubric criterion's name.
    """
    if isinstance(content, bytes):
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ValueError("The benchmark CSV must be UTF-8 encoded. Save it as CSV UTF-8.") from None
    else:
        text = str(content)
    if len(text.encode("utf-8")) > 2_000_000:
        raise ValueError("Benchmark CSV exceeds the 2 MB limit.")
    try:
        frame = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
    except Exception as exc:
        raise ValueError(f"Could not read benchmark CSV: {exc}") from None

    required = list(REQUIRED_BASE_COLUMNS) + [c["name"] for c in rubric]
    missing = [col for col in required if col not in frame.columns]
    if missing:
        raise ValueError("CSV is missing required column(s): " + ", ".join(missing))
    if len(frame) != 5:
        raise ValueError(f"The benchmark must contain exactly five student answers; found {len(frame)} rows.")

    students: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    max_total = sum(float(c["max_marks"]) for c in rubric)
    for idx, row in frame.iterrows():
        student_id = str(row["student"]).strip()
        answer = str(row["answer"]).strip()
        display_row = idx + 2  # header is row 1 in a spreadsheet
        if not student_id:
            raise ValueError(f"CSV row {display_row}: student ID cannot be blank.")
        if student_id in seen_ids:
            raise ValueError(f"CSV row {display_row}: duplicate student ID '{student_id}'.")
        seen_ids.add(student_id)
        if not answer:
            raise ValueError(f"CSV row {display_row}: answer text for {student_id} is blank.")
        if len(answer) > 60_000:
            raise ValueError(f"CSV row {display_row}: answer for {student_id} exceeds 60,000 characters.")

        marks: dict[str, float] = {}
        for criterion in rubric:
            name = criterion["name"]
            raw = str(row[name]).strip()
            try:
                score = float(raw)
            except (TypeError, ValueError):
                raise ValueError(f"CSV row {display_row}: '{name}' for {student_id} must be a number.") from None
            maximum = float(criterion["max_marks"])
            if not pd.notna(score) or not (0 <= score <= maximum):
                raise ValueError(
                    f"CSV row {display_row}: '{name}' for {student_id} must be between 0 and {maximum:g}."
                )
            marks[name] = score
        students.append({
            "id": student_id,
            "file": "uploaded_csv",
            "text": answer,
            "human": marks,
            "human_total": sum(marks.values()),
            "human_data_is_real": False,
        })

    return {
        "students": students,
        "max_total": max_total,
        "source": "uploaded benchmark CSV (pending human-grade confirmation)",
        "human_data_is_real": False,
        "human_data_note": "Uploaded data; the evaluator must confirm human marks were assigned independently.",
    }


def run_benchmark(cfg: JudgeConfig, sample=None, bench=None, progress=None):
    sample = sample or load_sample()
    bench = bench or load_benchmark()
    students = bench.get("students", [])
    if not students:
        raise ValueError("Benchmark dataset contains no student answers.")

    rows, results = [], {}
    for i, student in enumerate(students):
        res = grade_answer(student["text"], sample["question"], sample["model_answer"], sample["rubric"], cfg)
        results[student["id"]] = res
        human_total = float(student.get("human_total", sum(student["human"].values())))
        row = {
            "student": student["id"],
            "words": res["metrics"]["word_count"],
            "human_total": human_total,
            "auto_total": res["total"],
            "error": res["total"] - human_total,
            "BLEU": res["metrics"]["bleu"],
            "ROUGE-L": res["metrics"]["rougeL"],
        }
        for criterion in sample["rubric"]:
            name = criterion["name"]
            row[f"human_{name}"] = float(student["human"][name])
            row[f"auto_{name}"] = next(c["score"] for c in res["criteria"] if c["name"] == name)
        rows.append(row)
        if progress:
            progress((i + 1) / len(students))

    df = pd.DataFrame(rows)
    max_total = float(bench.get("max_total", sum(c["max_marks"] for c in sample["rubric"])))
    stats = agreement(df["auto_total"], df["human_total"], max_total)
    per_criterion = {
        criterion["name"]: float((df[f"auto_{criterion['name']}"] - df[f"human_{criterion['name']}"]).abs().mean())
        for criterion in sample["rubric"]
    }
    metric_corr = {
        metric: {"pearson": pearson(df[metric], df["human_total"]),
                 "spearman": spearman(df[metric], df["human_total"])}
        for metric in ("BLEU", "ROUGE-L")
    }
    first_result = next(iter(results.values()))
    return {
        "df": df,
        "stats": stats,
        "per_criterion_mae": per_criterion,
        "metric_corr": metric_corr,
        "results": results,
        "max_total": max_total,
        "judge": first_result["judge"],
        "data_source": bench.get("source", "unknown source"),
        "human_data_is_real": bool(bench.get("human_data_is_real", False)),
        "human_data_note": bench.get("human_data_note", "Human-grade provenance was not recorded."),
    }


def _discordant(df, col):
    import itertools
    bad, total, examples = 0, 0, []
    for i, j in itertools.combinations(range(len(df)), 2):
        human_delta = df["human_total"].iloc[i] - df["human_total"].iloc[j]
        metric_delta = df[col].iloc[i] - df[col].iloc[j]
        if human_delta == 0:
            continue
        total += 1
        if human_delta * metric_delta < 0:
            bad += 1
            examples.append(f"{df['student'].iloc[i]} vs {df['student'].iloc[j]}")
    return bad, total, examples


def _f(value, nd=2):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "n/a"
    return "n/a" if pd.isna(value) else f"{value:.{nd}f}"


def render_benchmark_markdown(b: dict, cfg: JudgeConfig) -> str:
    df, stats = b["df"], b["stats"]
    backend = next(iter(b["results"].values()))["metrics"]["backend"] if b.get("results") else "n/a"
    lines = [
        "# Benchmark Evaluation Report", "",
        f"**Judge:** {b['judge']}  ",
        f"**Dataset source:** {b.get('data_source', 'unknown source')}  ",
        f"**Human-grade provenance:** {'user-confirmed independently assigned human marks' if b.get('human_data_is_real') else 'NOT VERIFIED — illustrative/unconfirmed data'}  ",
        f"**Temperature:** 0.0  **Few-shot:** {cfg.few_shot}  **Baseline metrics shown to judge:** {cfg.include_metrics}  ",
        f"**Items:** {stats['n']} student answers, graded out of {b['max_total']:g} marks.  ",
        f"**BLEU/ROUGE backend:** {backend}", "",
    ]
    if cfg.offline:
        lines += [
            "> **Judge limitation:** this run used the offline keyword baseline, not an LLM. It is deterministic and can be fooled by keyword-heavy incorrect answers; the results do not measure Gemini performance.", ""
        ]
    if not b.get("human_data_is_real", False):
        lines += [
            "> **VALIDITY WARNING:** these human reference marks are illustrative or unconfirmed. MAE, RMSE, correlations, and tolerance rates below are software-pipeline diagnostics only and must not be reported as human-study results.", ""
        ]
    else:
        lines += [
            "> The user confirmed that reference marks were assigned independently. This is an application-level declaration, not an independent audit of the grading records.", ""
        ]
    lines += [
        "## 1. Score comparison", "",
        "| Student | Words | Reference total | Automated total | Error (auto-reference) | BLEU | ROUGE-L |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in df.iterrows():
        lines.append(
            f"| {row['student']} | {int(row['words'])} | {row['human_total']:g} | {row['auto_total']:g} | "
            f"{row['error']:+.1f} | {row['BLEU']:.3f} | {row['ROUGE-L']:.3f} |"
        )
    lines += [
        "", "## 2. Agreement statistics", "", "| Metric | Value |", "|---|---:|",
        f"| MAE (marks) | {_f(stats['MAE'])} ({_f(stats['MAE_pct_of_max'], 1)}% of maximum) |",
        f"| RMSE (marks) | {_f(stats['RMSE'])} |",
        f"| Mean signed error (+ = higher automated marks) | {_f(stats['mean_signed_error'], 2)} |",
        f"| Pearson r | {_f(stats['pearson'])} |",
        f"| Spearman rho | {_f(stats['spearman'])} |",
        f"| Within 0.5 mark | {stats['within_0.5'] * 100:.0f}% |",
        f"| Within 1.0 mark | {stats['within_1.0'] * 100:.0f}% |",
        "", "## 3. Per-criterion mean absolute error", "", "| Criterion | MAE (marks) |", "|---|---:|",
    ]
    for name, value in b["per_criterion_mae"].items():
        lines.append(f"| {name} | {value:.2f} |")
    lines += [
        "", "## 4. BLEU / ROUGE-L as baselines", "",
        "| Metric | Pearson vs reference grades | Spearman vs reference grades |",
        "|---|---:|---:|",
    ]
    for name, values in b["metric_corr"].items():
        lines.append(f"| {name} | {_f(values['pearson'])} | {_f(values['spearman'])} |")
    discordant = _discordant(df, "ROUGE-L")
    lines += [
        "", f"ROUGE-L ordered {discordant[0]} of {discordant[1]} non-tied pairs differently from the reference grades. "
        "With only five answers, correlations are highly unstable. BLEU/ROUGE measure lexical overlap, not correctness, "
        "and should be interpreted as supplementary baseline metrics rather than grades.",
        "", "## 5. Interpretation and limitations", "",
        "- Temperature 0.0 may reduce response variability but does not guarantee identical output from a hosted model.",
        "- A five-answer benchmark is a small demonstration and is not sufficient for broad reliability claims.",
        "- Human-agreement claims require independently assigned marks and retained grading records.",
        "- Review every generated score sheet before using marks for consequential academic decisions.",
    ]
    return "\n".join(lines) + "\n"
