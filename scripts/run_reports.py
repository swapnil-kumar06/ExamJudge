"""Regenerate all reports from a real run.

  python scripts/run_reports.py                      # offline baseline (no key needed)
  GEMINI_API_KEY=... python scripts/run_reports.py --provider gemini --model gemini-2.5-flash
"""
import argparse, os, sys, json, datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.llm_client import PROVIDERS, OFFLINE
from engine.judge import JudgeConfig
from engine.benchmark import load_sample, load_benchmark, run_benchmark, render_benchmark_markdown
from engine import analysis
from engine.reporting import bias_markdown, project_markdown

KEYS = {"gemini": "Google Gemini", "offline": OFFLINE}
REPORTS = Path(__file__).resolve().parent.parent / "reports"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="offline", choices=list(KEYS))
    ap.add_argument("--model", default="")
    ap.add_argument("--no-few-shot", action="store_true")
    ap.add_argument("--repeats", type=int, default=3)
    args = ap.parse_args()
    name = KEYS[args.provider]
    pc = PROVIDERS[name]
    key = os.environ.get(pc["env"], "") if pc["env"] else ""
    if name != OFFLINE and not key:
        sys.exit(f"Set {pc['env']} in the environment first.")
    cfg = JudgeConfig(provider=name, api_key=key, base_url=pc["base_url"],
                      model=args.model or pc["model"], few_shot=not args.no_few_shot)
    sample, bench = load_sample(), load_benchmark()
    b = run_benchmark(cfg, sample, bench)
    a = analysis.run_all(cfg, sample, bench, b, repeats=args.repeats)
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "benchmark_report.md").write_text(render_benchmark_markdown(b, cfg), encoding="utf-8")
    (REPORTS / "bias_consistency_analysis.md").write_text(bias_markdown(a, cfg, b), encoding="utf-8")
    (REPORTS / "project_report.md").write_text(project_markdown(b, a, cfg), encoding="utf-8")
    b["df"].to_csv(REPORTS / "benchmark_scores.csv", index=False)
    print("Reports written to", REPORTS)


if __name__ == "__main__":
    main()
