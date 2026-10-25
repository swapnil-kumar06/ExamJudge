"""Regenerate ExamJudge reports from a five-answer benchmark CSV.

Formal reports are never generated from the bundled illustrative dataset by default.
Use --benchmark-csv and --confirm-human-grades for formal output, or --demo to
write clearly labelled pipeline-demonstration reports under reports/demo/.
"""
import argparse, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.llm_client import PROVIDERS, OFFLINE
from engine.judge import JudgeConfig
from engine.benchmark import (load_sample, load_benchmark, run_benchmark,
                              render_benchmark_markdown, parse_benchmark_csv)
from engine import analysis
from engine.reporting import bias_markdown, project_markdown

KEYS = {"gemini": "Google Gemini", "offline": OFFLINE}
ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--benchmark-csv", help="CSV with exactly five complete answers and criterion-level human marks")
    mode.add_argument("--demo", action="store_true", help="Use bundled illustrative data; writes only to reports/demo/")
    ap.add_argument("--provider", default="offline", choices=list(KEYS))
    ap.add_argument("--model", default="")
    ap.add_argument("--no-few-shot", action="store_true")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--confirm-human-grades", action="store_true",
                    help="Attest that the CSV marks were independently assigned by a human")
    args = ap.parse_args()
    if args.repeats < 2 or args.repeats > 5:
        sys.exit("--repeats must be between 2 and 5.")
    name = KEYS[args.provider]
    pc = PROVIDERS[name]
    key = os.environ.get(pc["env"], "") if pc["env"] else ""
    if name != OFFLINE and not key:
        sys.exit(f"Set {pc['env']} in the environment first.")
    if args.benchmark_csv and not args.confirm_human_grades:
        sys.exit("Formal reports require --confirm-human-grades after verifying the marks are genuine independent human grades. Use --demo for illustrative pipeline outputs.")

    cfg = JudgeConfig(provider=name, api_key=key, base_url=pc["base_url"],
                      model=args.model or pc["model"], few_shot=not args.no_few_shot)
    sample = load_sample()
    if args.demo:
        bench = load_benchmark()
        bench["human_data_is_real"] = False
        bench["human_data_note"] = "Bundled illustrative grades; not independently human graded."
        out_dir = REPORTS / "demo"
    else:
        try:
            csv_path = Path(args.benchmark_csv)
            bench = parse_benchmark_csv(csv_path.read_bytes(), sample["rubric"])
        except (OSError, ValueError) as exc:
            sys.exit(f"Invalid benchmark CSV: {exc}")
        bench["source"] = f"custom CSV: {Path(args.benchmark_csv).name}"
        bench["human_data_is_real"] = True
        bench["human_data_note"] = "CLI user attested marks were independently assigned; not externally audited."
        for student in bench["students"]:
            student["human_data_is_real"] = True
        out_dir = REPORTS

    b = run_benchmark(cfg, sample, bench)
    b["human_data_is_real"] = bool(bench.get("human_data_is_real", False))
    b["data_source"] = bench.get("source", "unknown source")
    a = analysis.run_all(cfg, sample, bench, b, repeats=args.repeats)
    out_dir.mkdir(exist_ok=True, parents=True)
    (out_dir / "benchmark_report.md").write_text(render_benchmark_markdown(b, cfg), encoding="utf-8")
    (out_dir / "bias_consistency_analysis.md").write_text(bias_markdown(a, cfg, b), encoding="utf-8")
    (out_dir / "project_report.md").write_text(project_markdown(b, a, cfg), encoding="utf-8")
    scores = b["df"].copy()
    rename = {column: column.replace("human_", "human_reference_")
              for column in scores.columns if column.startswith("human_")}
    rename.update({"human_total": "human_reference_total", "error": "auto_minus_human_reference"})
    scores = scores.rename(columns=rename)
    scores["dataset_source"] = b.get("data_source", "unknown source")
    scores["human_marks_user_attested"] = bool(b.get("human_data_is_real", False))
    scores["judge"] = b.get("judge", "unknown judge")
    scores.to_csv(out_dir / "benchmark_scores.csv", index=False)
    print("Reports written to", out_dir)
    if args.demo:
        print("WARNING: demo numbers are illustrative and must not be reported as a human-grading evaluation.")


if __name__ == "__main__":
    main()
