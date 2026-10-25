# Five-answer human-graded benchmark

The bundled answer files and the marks in `human_grades.json` are **illustrative fixtures only**. They are not independently graded by real examiners. The formal Benchmark vs human workflow does not display or use these marks by default.

## Create the required benchmark report

1. Open **Grade answers** and enter the reference question, model answer, and the final marking rubric.
2. Open **Benchmark vs human** and download the blank five-answer CSV template. It is generated from the active rubric, so criterion names and maximum marks match the current exam.
3. Replace the five rows with five de-identified student IDs, each complete answer, and human-assigned marks for every criterion. Keep CSV column headings unchanged.
4. Have a human evaluator grade each response independently against the official question, model answer, and rubric. Do not invent or infer the human marks from ExamJudge's automated output.
5. Save as CSV UTF-8 and upload the file. Review the preview and confirm only if the marks truly were assigned independently by a human.
6. Run the benchmark. It will compare those same five answers against the currently active question, model answer, and rubric, and generate the Markdown/CSV reports.

The app validates exactly five unique IDs, five non-empty answers, required criterion columns, numeric marks, and mark ranges. A checkbox is an attestation, not an external audit. Retain the original grading records. Five answers are enough for a course demonstration, not strong general-validity claims; use a larger dataset and preferably two independent human graders for a stronger study.

## Generate reports from a local CSV

The CLI uses the repository's sample TCP question/model answer/rubric. The CSV must match those criterion names unless you update the CLI data files accordingly.

```powershell
python scripts/run_reports.py --provider offline --benchmark-csv path\to\real_benchmark.csv --confirm-human-grades
```

For Gemini, configure `GEMINI_API_KEY` in the environment and use `--provider gemini`; this makes live API requests and may consume quota. `--demo` generates illustrative-only reports under `reports/demo/`, never as the default formal reports. Formal runs are not generated without a provided CSV and explicit confirmation.
