"""ExamJudge - Automated Descriptive Exam Assessment Engine (LLM-as-a-Judge). Streamlit dashboard."""
import json
import os
import hmac
import re
import html
import hashlib

import pandas as pd
import streamlit as st

from engine import analysis
from engine.benchmark import (load_benchmark, load_sample, render_benchmark_markdown, run_benchmark,
                               benchmark_template_csv, parse_benchmark_csv)
from engine.judge import JudgeConfig, grade_answer
from engine.llm_client import GEMINI, LLMError, OFFLINE, PROVIDERS
from engine.pdf_utils import MAX_UPLOAD_BYTES, ExtractionError, extract_text
from engine.prompts import build_grading_messages, read_prompt
from engine.reporting import bias_markdown
from engine.rubric import DEFAULT_RUBRIC, clean_rubric, total_marks

st.set_page_config(page_title="ExamJudge - LLM exam grader", page_icon="🎓", layout="wide")

MAX_BATCH_ANSWERS = 10
MAX_LLM_CALLS_PER_SESSION = 60
MAX_QUESTION_CHARS = 10_000
MAX_MODEL_ANSWER_CHARS = 30_000

st.markdown("""
<style>
.hero{padding:1.2rem 1.6rem;border-radius:16px;color:#fff;margin-bottom:1rem;
 background:linear-gradient(120deg,#4F46E5 0%,#7C3AED 55%,#DB2777 100%);}
.hero h1{margin:0;font-size:1.9rem;color:#fff}
.hero p{margin:.3rem 0 0;opacity:.92}
.badge{display:inline-block;padding:.15rem .6rem;border-radius:999px;background:#EEF2FF;color:#3730A3;
 font-size:.78rem;font-weight:600;margin-right:.35rem}
.score{font-size:2.2rem;font-weight:800;color:#4F46E5;line-height:1}
.card{border:1px solid #E5E7EB;border-radius:12px;padding:.8rem 1rem;background:#fff;margin:.3rem 0}
</style>
<div class="hero"><h1>🎓 ExamJudge</h1>
<p>Rubric-based descriptive-answer grading with an LLM judge or offline baseline, criterion-wise rationales, and BLEU/ROUGE metrics.</p></div>
""", unsafe_allow_html=True)


# ------------------------------------------------------------------ helpers
def secret(name: str) -> str:
    """Read a server-side Streamlit secret/environment variable; never render its value."""
    try:
        v = st.secrets.get(name)
    except Exception:
        v = None
    return str(v or os.environ.get(name, "")).strip()


SERVER_GEMINI_KEY = secret("GEMINI_API_KEY")
APP_PASSWORD = secret("APP_PASSWORD")

# A server-side model key must never be used by an anonymously accessible app.
# For local/offline use no secrets are required. If a Gemini key is set, an app
# password is mandatory before any grading UI or API operation is exposed.
if SERVER_GEMINI_KEY and not APP_PASSWORD:
    st.error("Secure setup required: GEMINI_API_KEY is configured but APP_PASSWORD is missing. Add both to Streamlit Secrets, then reboot the app.")
    st.stop()


def _logout() -> None:
    # Clear prior users' student answers/results on shared devices.
    for key in list(st.session_state.keys()):
        try:
            del st.session_state[key]
        except Exception:
            pass
    st.session_state["authenticated"] = False


def _authenticate() -> None:
    if not APP_PASSWORD or st.session_state.get("authenticated", False):
        return
    st.markdown("## 🔐 ExamJudge access")
    st.caption("This deployment is password protected. Ask the app owner for the access password.")
    with st.form("login_form", clear_on_submit=True):
        entered = st.text_input("App password", type="password")
        submitted = st.form_submit_button("Unlock app", type="primary")
    if submitted:
        if hmac.compare_digest(entered.encode("utf-8"), APP_PASSWORD.encode("utf-8")):
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    st.stop()


_authenticate()


def default_provider() -> str:
    return GEMINI if SERVER_GEMINI_KEY else OFFLINE


def reserve_api_budget(estimated_calls: int) -> bool:
    """Basic per-session guard; provider-side quota/billing controls are still required."""
    if provider == OFFLINE:
        return True
    used = int(st.session_state.get("llm_calls_used", 0))
    if used + estimated_calls > MAX_LLM_CALLS_PER_SESSION:
        st.error(f"This session's safety limit is {MAX_LLM_CALLS_PER_SESSION} estimated Gemini calls. Start a new session or reduce the workflow size. This is a per-session guard, not a global quota.")
        return False
    st.session_state["llm_calls_used"] = used + estimated_calls
    return True


def safe_filename(value: str, fallback: str = "student") -> str:
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "")).strip("._")[:80]
    return name or fallback


def rubric_df_from(rubric) -> pd.DataFrame:
    return pd.DataFrame([{"name": c["name"], "max_marks": c["max_marks"], "description": c["description"],
                          "keywords": ", ".join(c.get("keywords", []))} for c in rubric])


def load_sample_cb():
    s = load_sample()
    st.session_state["question"] = s["question"]
    st.session_state["model_answer"] = s["model_answer"]
    st.session_state["rubric_df"] = rubric_df_from(s["rubric"])
    st.session_state.pop("rubric_editor", None)
    st.session_state["use_bench"] = False


def export_json(name, res) -> dict:
    return {"student": name, "judge": res["judge"], "temperature": res["temperature"],
            "total": res["total"], "max_total": res["max_total"],
            "score_sheet": [{"criterion": c["name"], "score": c["score"], "max_marks": c["max_marks"],
                             "reasoning": c["reasoning"], "evidence": c["evidence"],
                             "deficiencies": c["deficiencies"]} for c in res["criteria"]],
            "conceptual_deficiencies": res["conceptual_deficiencies"], "strengths": res["strengths"],
            "feedback": res["feedback"], "baseline_metrics": res["metrics"], "warnings": res["warnings"]}


def stable_signature(payload) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def grade_inputs_signature(question, model_answer, rubric, files, pasted, use_bench, cfg) -> str:
    """Fingerprint all grade inputs so old score sheets are not shown for changed inputs."""
    uploaded = []
    for file in files or []:
        raw = file.getvalue()
        uploaded.append({"name": file.name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    sample_answers = []
    if use_bench:
        sample_answers = [
            {"id": item["id"], "sha256": hashlib.sha256(item["text"].encode("utf-8")).hexdigest()}
            for item in load_benchmark()["students"]
        ]
    return stable_signature({
        "question": question,
        "model_answer": model_answer,
        "rubric": rubric,
        "uploaded_files": uploaded,
        "pasted_answer": pasted,
        "use_bench": bool(use_bench),
        "sample_answers": sample_answers,
        "provider": cfg.provider,
        "model": cfg.model,
        "few_shot": cfg.few_shot,
        "include_metrics": cfg.include_metrics,
        "api_key_configured": bool(cfg.api_key),
    })


if "rubric_df" not in st.session_state:
    st.session_state["rubric_df"] = rubric_df_from(DEFAULT_RUBRIC)
    st.session_state.setdefault("question", "")
    st.session_state.setdefault("model_answer", "")

# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("⚙️ Judge settings")
    names = list(PROVIDERS)
    provider = st.selectbox("Judge", names, index=names.index(default_provider()))
    pc = PROVIDERS[provider]
    api_key = SERVER_GEMINI_KEY if provider == GEMINI else ""
    base_url = pc["base_url"]
    model = secret("GEMINI_MODEL") or pc["model"] if provider == GEMINI else pc["model"]
    if provider == OFFLINE:
        st.warning("Offline mode is a basic keyword baseline. It cannot reliably detect factual errors and is for demos only.")
        if SERVER_GEMINI_KEY:
            st.caption("Gemini is configured on the server; the key is not displayed in this interface.")
    elif not api_key:
        st.error("Gemini is not configured. Add GEMINI_API_KEY and APP_PASSWORD in Streamlit Secrets, then reboot the app.")
    else:
        st.success("Gemini key configured on the server")
        st.caption(f"Model: `{model}` · The key and endpoint are server-controlled and are never entered into the browser UI.")
        st.warning("Student answer text is sent to Google Gemini for grading. Obtain permission and remove identifying information before upload.")
    few_shot = st.toggle("Few-shot calibration examples", value=True)
    inc_metrics = st.toggle("Show BLEU/ROUGE to the judge", value=False,
                            help="Off by default: lexical scores can anchor the judge.")
    st.markdown("**Temperature:** `0.0` (fixed)")
    st.caption("The judge returns concise, evidence-based grading rationales.")
    st.caption("Temperature 0.0 reduces sampling variability but does not guarantee identical hosted-model results.")
    st.caption(f"Session usage guard: {st.session_state.get('llm_calls_used', 0)}/{MAX_LLM_CALLS_PER_SESSION} estimated Gemini calls")
    if APP_PASSWORD:
        st.button("Log out and clear this session", key="logout_button", on_click=_logout)


def get_cfg() -> JudgeConfig:
    return JudgeConfig(provider=provider, api_key=api_key, base_url=base_url, model=model,
                       few_shot=few_shot, include_metrics=inc_metrics)


tab_grade, tab_bench, tab_bias, tab_prompts = st.tabs(
    ["📝 Grade answers", "📊 Benchmark vs human", "🧪 Bias & consistency", "📚 Prompts & calibration"])

# ------------------------------------------------------------------ tab 1
with tab_grade:
    top = st.columns([3, 1])
    top[0].markdown("#### 1 · Exam setup")
    top[1].button("✨ Load sample exam", on_click=load_sample_cb, help="TCP congestion control question + 5 sample answers")
    left, right = st.columns(2)
    with left:
        question = st.text_area("Reference question", key="question", height=100)
        model_answer = st.text_area("Model answer (answer key)", key="model_answer", height=240)
    with right:
        st.markdown("**Marking rubric** - add/remove rows. *keywords* (optional, comma separated, `a|b` = alternatives) "
                    "are used only by the offline baseline.")
        edited = st.data_editor(st.session_state["rubric_df"], num_rows="dynamic", key="rubric_editor",
                                column_config={"max_marks": st.column_config.NumberColumn("max_marks", min_value=0.5, step=0.5),
                                               "description": st.column_config.TextColumn("description", width="large")})
        try:
            rubric = clean_rubric(edited.to_dict("records"))
            st.caption(f"Total: **{total_marks(rubric):g} marks** across {len(rubric)} criteria")
        except ValueError as e:
            rubric = None
            st.error(str(e))

    st.markdown("#### 2 · Student answers")
    c1, c2 = st.columns(2)
    files = c1.file_uploader("Upload answer PDFs (or .txt, max 10 MB each)", type=["pdf", "txt"], accept_multiple_files=True, help="Up to 10 files per grading run. PDFs are limited to 40 pages and 60,000 extracted characters.")
    pasted = c2.text_area("…or paste one answer", height=120)
    use_bench = c2.checkbox("Also grade the 5 sample answers", key="use_bench")
    current_grade_signature = grade_inputs_signature(
        question, model_answer, rubric, files, pasted, use_bench, get_cfg()
    )

    if st.button("🚀 Grade", type="primary"):
        if not question.strip() or not model_answer.strip() or rubric is None:
            st.error("Provide the question, model answer and a valid rubric.")
        elif len(question) > MAX_QUESTION_CHARS or len(model_answer) > MAX_MODEL_ANSWER_CHARS:
            st.error(f"Keep the question under {MAX_QUESTION_CHARS:,} characters and the model answer under {MAX_MODEL_ANSWER_CHARS:,} characters.")
        else:
            answers = []
            if len(files or []) > MAX_BATCH_ANSWERS:
                st.error(f"Upload no more than {MAX_BATCH_ANSWERS} files per grading run.")
            else:
                for f in files or []:
                    try:
                        if f.size > MAX_UPLOAD_BYTES:
                            raise ExtractionError("File exceeds the 10 MB upload limit.")
                        answers.append((safe_filename(f.name), extract_text(f.getvalue(), f.name)))
                    except ExtractionError as e:
                        st.error(f"{safe_filename(f.name)}: {e}")
                if pasted.strip() and len(pasted.strip()) <= 60_000:
                    answers.append(("pasted_answer", pasted.strip()))
                if use_bench:
                    answers += [(s["id"], s["text"]) for s in load_benchmark()["students"]]
                if pasted.strip() and len(pasted.strip()) > 60_000:
                    st.error("Pasted student answers must be 60,000 characters or fewer.")
                elif len(answers) > MAX_BATCH_ANSWERS:
                    st.error(f"This run contains {len(answers)} answers. The maximum is {MAX_BATCH_ANSWERS}; remove some files/sample answers.")
                elif not answers:
                    st.warning("Upload at least one answer, paste one, or tick the sample option.")
                elif not (get_cfg().offline or api_key) :
                    st.error("Choose Offline baseline or configure Gemini on the server.")
                elif reserve_api_budget(len(answers)):
                    cfg, out, bar = get_cfg(), [], st.progress(0.0)
                    for i, (name, text) in enumerate(answers):
                        try:
                            out.append({"name": name, "res": grade_answer(text, question, model_answer, rubric, cfg), "text": text})
                        except LLMError as e:
                            out.append({"name": name, "error": str(e)})
                        bar.progress((i + 1) / len(answers))
                    st.session_state["results"] = out
                    st.session_state["results_signature"] = current_grade_signature

    results = st.session_state.get("results")
    if results and st.session_state.get("results_signature") != current_grade_signature:
        st.warning("These score sheets are stale because the question, answer key, rubric, student answers, or judge settings changed. Click Grade again to refresh them.")
        results = None
    if results:
        st.markdown("#### 3 · Results")
        ok = [r for r in results if "res" in r]
        for r in results:
            if "error" in r:
                st.error(f"{r['name']}: {r['error']}")
        if ok:
            summary = pd.DataFrame([{"student": r["name"], "total": r["res"]["total"], "max": r["res"]["max_total"],
                                     "percent": round(100 * r["res"]["total"] / r["res"]["max_total"], 1),
                                     "BLEU": r["res"]["metrics"]["bleu"], "ROUGE-L": r["res"]["metrics"]["rougeL"]} for r in ok])
            st.dataframe(summary, hide_index=True)
            d1, d2 = st.columns(2)
            d1.download_button("⬇️ All score sheets (JSON)", json.dumps([export_json(r["name"], r["res"]) for r in ok], indent=2),
                               "score_sheets.json", "application/json")
            d2.download_button("⬇️ Summary (CSV)", summary.to_csv(index=False), "summary.csv", "text/csv")
            for k, r in enumerate(ok):
                res = r["res"]
                with st.expander(f"{r['name']}  -  {res['total']:g} / {res['max_total']:g}", expanded=(len(ok) == 1)):
                    a, b = st.columns([1, 2])
                    a.markdown(f"<div class='score'>{res['total']:g}<span style='font-size:1rem;color:#6B7280'> / {res['max_total']:g}</span></div>"
                               f"<span class='badge'>{html.escape(str(res['judge']))}</span>", unsafe_allow_html=True)
                    m = res["metrics"]
                    mc = b.columns(4)
                    mc[0].metric("BLEU", f"{m['bleu']:.3f}")
                    mc[1].metric("ROUGE-1", f"{m['rouge1']:.3f}")
                    mc[2].metric("ROUGE-L", f"{m['rougeL']:.3f}")
                    mc[3].metric("Cosine", f"{m['cosine']:.3f}")
                    st.dataframe(pd.DataFrame([{"Criterion": c["name"], "Score": c["score"], "Max": c["max_marks"]} for c in res["criteria"]]),
                                 hide_index=True)
                    st.bar_chart(pd.DataFrame({"fraction of marks": [c["score"] / c["max_marks"] for c in res["criteria"]]},
                                              index=[c["name"] for c in res["criteria"]]))
                    st.markdown("**🔎 Judge reasoning per criterion**")
                    for c in res["criteria"]:
                        st.markdown(f"<div class='card'><b>{html.escape(str(c['name']))}</b> - {c['score']:g}/{c['max_marks']:g}<br>{html.escape(str(c['reasoning']))}</div>",
                                    unsafe_allow_html=True)
                        if c["evidence"]:
                            st.text("Evidence: " + " · ".join(str(e) for e in c["evidence"]))
                        for d in c["deficiencies"]:
                            st.text("⚠️ " + str(d))
                    if res["conceptual_deficiencies"]:
                        st.markdown("**🧩 Conceptual deficiencies**")
                        for d in res["conceptual_deficiencies"]:
                            st.text("• " + str(d))
                    if res["strengths"]:
                        st.markdown("**💪 Strengths**")
                        for d in res["strengths"]:
                            st.text("• " + str(d))
                    st.text("Feedback: " + str(res["feedback"]))
                    for w in res["warnings"]:
                        st.warning(w)
                    st.json(export_json(r["name"], res), expanded=False)
                    st.download_button("⬇️ This score sheet (JSON)", json.dumps(export_json(r["name"], res), indent=2),
                                       f"{safe_filename(r['name'])}_score.json", "application/json", key=f"dl_{k}")
                    with st.expander("Extracted answer text"):
                        st.write(r["text"])

# ------------------------------------------------------------------ tab 2
with tab_bench:
    st.markdown("#### Automated scores vs independently human-graded answers")
    st.caption(
        "The formal benchmark uses the current question, model answer, and rubric from Grade answers. "
        "No bundled marks are treated as human grades. Upload five complete answers and independently assigned criterion marks."
    )

    benchmark_exam_ready = bool(
        question and question.strip() and model_answer and model_answer.strip() and rubric is not None
    )
    benchmark_exam = (
        {"question": question.strip(), "model_answer": model_answer.strip(), "rubric": rubric}
        if benchmark_exam_ready else None
    )
    benchmark_data = None
    benchmark_preview = None
    benchmark_data_error = None

    if not benchmark_exam_ready:
        st.warning("First fill in the Reference question, Model answer, and a valid rubric in the Grade answers tab. The benchmark will use those exact inputs.")
    elif total_marks(rubric) <= 0:
        st.error("The active rubric must have a positive total before benchmarking.")
        benchmark_exam_ready = False
        benchmark_exam = None

    if rubric is not None:
        st.download_button(
            "⬇️ Download blank five-answer CSV template",
            benchmark_template_csv(rubric),
            "benchmark_template.csv",
            "text/csv",
            help="The template uses criterion names and marks from the current Grade answers rubric.",
        )
        st.caption(
            "CSV columns: `student`, `answer`, and one column per criterion: "
            + ", ".join(f"`{c['name']}` (0–{c['max_marks']:g})" for c in rubric)
            + ". Provide exactly five unique student IDs, full answer texts, and marks independently assigned by a human evaluator."
        )
    else:
        st.info("Fix the rubric on the Grade answers tab before downloading the matching CSV template.")

    uploaded_benchmark = st.file_uploader(
        "Upload completed five-answer benchmark CSV (UTF-8)", type=["csv"], key="benchmark_csv_upload_v2"
    )
    # Bind the human-grade attestation to the exact CSV and exam setup. If either
    # changes, force a fresh confirmation rather than inheriting a stale checkbox.
    csv_digest = hashlib.sha256(uploaded_benchmark.getvalue()).hexdigest() if uploaded_benchmark is not None else "no-upload"
    attestation_context = stable_signature({
        "csv_sha256": csv_digest,
        "question": question or "",
        "model_answer": model_answer or "",
        "rubric": rubric,
    })
    if st.session_state.get("benchmark_attestation_context") != attestation_context:
        st.session_state["confirm_benchmark_human_grades_v2"] = False
        st.session_state["benchmark_attestation_context"] = attestation_context
    human_grade_confirmation = st.checkbox(
        "I confirm all five criterion-level reference marks were independently assigned by a human evaluator.",
        key="confirm_benchmark_human_grades_v2",
    )

    if uploaded_benchmark is not None:
        if rubric is None:
            benchmark_data_error = "Cannot validate the CSV until the rubric in Grade answers is valid."
            st.error(benchmark_data_error)
        else:
            try:
                benchmark_preview = parse_benchmark_csv(uploaded_benchmark.getvalue(), rubric)
                preview_df = pd.DataFrame([
                    {"student": student["id"], "answer words": len(student["text"].split()),
                     **{f"reference: {name}": score for name, score in student["human"].items()},
                     "reference total": student["human_total"]}
                    for student in benchmark_preview["students"]
                ])
                st.markdown("**CSV validation preview**")
                st.dataframe(preview_df, hide_index=True, use_container_width=True)
                if not benchmark_exam_ready:
                    st.warning("The CSV is structurally valid, but grading cannot run until the exam question, model answer, and rubric are complete.")
                elif not human_grade_confirmation:
                    st.warning("Reference marks are not confirmed. No formal benchmark metrics or human-agreement report will be generated until you confirm they were genuinely assigned by a human evaluator.")
                else:
                    benchmark_data = benchmark_preview
                    benchmark_data["human_data_is_real"] = True
                    benchmark_data["source"] = f"uploaded CSV: {safe_filename(uploaded_benchmark.name, 'benchmark.csv')}"
                    benchmark_data["human_data_note"] = (
                        "The app user attested that all criterion-level reference marks were independently assigned by a human evaluator. "
                        "This declaration is not an external audit."
                    )
                    for student in benchmark_data["students"]:
                        student["human_data_is_real"] = True
                    st.success("CSV passed validation and the user attested to genuine human grading. Keep the original grading records for auditability.")
            except ValueError as exc:
                benchmark_data_error = str(exc)
                st.error(benchmark_data_error)

    def _dataset_payload(data):
        if data is None:
            return None
        return {
            "source": data.get("source", "unknown"),
            "human_data_is_real": bool(data.get("human_data_is_real", False)),
            "students": [
                {"id": student["id"], "text": student["text"], "human": student["human"]}
                for student in data["students"]
            ],
        }

    def _result_signature(data, cfg, exam):
        payload = {
            "dataset": _dataset_payload(data),
            "provider": cfg.provider,
            "model": cfg.model,
            "few_shot": cfg.few_shot,
            "include_metrics": cfg.include_metrics,
            "question": exam["question"],
            "model_answer": exam["model_answer"],
            "rubric": exam["rubric"],
        }
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    cfg = get_cfg()
    current_benchmark_signature = (
        _result_signature(benchmark_data, cfg, benchmark_exam)
        if benchmark_data is not None and benchmark_exam is not None else None
    )

    if st.button("▶️ Run benchmark", type="primary", key="run_benchmark_button_v2"):
        if benchmark_data is None or benchmark_exam is None:
            st.error(benchmark_data_error or "To run a formal benchmark, provide a complete exam, a valid five-answer CSV, and confirm that the reference marks are genuine independent human grades.")
        elif not reserve_api_budget(len(benchmark_data["students"])):
            pass
        else:
            try:
                bar = st.progress(0.0)
                result = run_benchmark(cfg, benchmark_exam, benchmark_data, progress=bar.progress)
                result["human_data_is_real"] = True
                result["human_data_note"] = benchmark_data["human_data_note"]
                result["data_source"] = benchmark_data.get("source", "uploaded human-graded CSV")
                result["config_signature"] = current_benchmark_signature
                st.session_state["bench"] = result
                st.session_state["bench_cfg"] = cfg
            except (LLMError, ValueError) as exc:
                st.session_state.pop("bench", None)
                st.error(str(exc))

    benchmark_result = st.session_state.get("bench")
    if benchmark_result and benchmark_result.get("config_signature") != current_benchmark_signature:
        st.warning("These benchmark results are stale because the exam, rubric, reference marks, dataset, or judge settings changed. Run the benchmark again.")
        benchmark_result = None
    if benchmark_result and current_benchmark_signature is not None:
        st.info("Human marks are user-confirmed as independently assigned; the application does not independently audit the original grading records. With five answers, correlations are descriptive and unstable.")
        stats = benchmark_result["stats"]
        cols = st.columns(5)
        cols[0].metric("MAE vs human marks", f"{stats['MAE']:.2f}")
        cols[1].metric("Pearson r", "n/a" if pd.isna(stats["pearson"]) else f"{stats['pearson']:.2f}")
        cols[2].metric("Spearman ρ", "n/a" if pd.isna(stats["spearman"]) else f"{stats['spearman']:.2f}")
        cols[3].metric("Within 1 mark", f"{stats['within_1.0'] * 100:.0f}%")
        cols[4].metric("Mean signed error", f"{stats['mean_signed_error']:+.2f}", help="Positive means automated marks are higher than human marks.")
        st.caption(f"Judge: {benchmark_result['judge']} · Dataset: {benchmark_result.get('data_source', 'unknown source')} · n={stats['n']} · Max={benchmark_result['max_total']:g}")
        reference_col_rename = {column: column.replace("human_", "human_reference_")
                                for column in benchmark_result["df"].columns if column.startswith("human_")}
        reference_col_rename.update({"human_total": "human_reference_total", "error": "auto_minus_human_reference"})
        display_scores = benchmark_result["df"].rename(columns=reference_col_rename)
        st.dataframe(display_scores.round(3), hide_index=True, use_container_width=True)
        chart_df = benchmark_result["df"].rename(columns={"human_total": "human_reference_total"})
        st.bar_chart(chart_df.set_index("student")[["human_reference_total", "auto_total"]])
        st.download_button(
            "⬇️ Benchmark evaluation report (Markdown)",
            render_benchmark_markdown(benchmark_result, st.session_state["bench_cfg"]),
            "benchmark_report.md", "text/markdown",
        )
        csv_scores = display_scores.copy()
        csv_scores["dataset_source"] = benchmark_result.get("data_source", "unknown source")
        csv_scores["human_marks_user_attested"] = True
        csv_scores["judge"] = benchmark_result.get("judge", "unknown judge")
        st.download_button("⬇️ Benchmark scores (CSV)", csv_scores.to_csv(index=False), "benchmark_scores.csv", "text/csv")

# ------------------------------------------------------------------ tab 3
with tab_bias:
    st.markdown("#### Reliability and bias checks")
    st.caption(
        "Tests run against the same five uploaded answers and the current exam setup used by the benchmark. "
        "They measure repeatability, criterion-order sensitivity, verbosity padding, answer-position swaps, and answer-length correlation."
    )
    reps = st.slider("Repeatability runs", 2, 5, 3, key="bias_repeatability_runs_v2")
    if benchmark_data is None or benchmark_exam is None:
        st.warning("Upload five complete answers in Benchmark vs human, provide the current exam setup, and confirm the marks are genuine human grades before running formal bias and metric reports.")
    else:
        if provider == OFFLINE:
            st.info("Offline mode is a deterministic keyword baseline, not an LLM. Its repeatability/position tests validate the test harness only; use Gemini to measure LLM-specific behavior.")
        estimated_calls = len(benchmark_data["students"]) + reps + 3 + 4 + (len(benchmark_data["students"]) * (len(benchmark_data["students"]) - 1))
        st.caption(f"Estimated judge calls for this run: {estimated_calls}. For five answers, pairwise A/B swapping performs 20 pairwise calls, plus grading and other checks. Provider quotas may be lower.")
        if st.button("▶️ Run all checks", type="primary", key="run_bias_checks_button_v2"):
            cfg = get_cfg()
            if reserve_api_budget(estimated_calls):
                try:
                    bar = st.progress(0.0, text="Running reliability checks…")
                    benchmark_result_for_bias = run_benchmark(cfg, benchmark_exam, benchmark_data, progress=bar.progress)
                    benchmark_result_for_bias["human_data_is_real"] = True
                    benchmark_result_for_bias["human_data_note"] = benchmark_data.get("human_data_note", "Human marks user-attested.")
                    benchmark_result_for_bias["data_source"] = benchmark_data.get("source", "uploaded human-graded CSV")
                    sig = _result_signature(benchmark_data, cfg, benchmark_exam)
                    analysis_result = analysis.run_all(
                        cfg, benchmark_exam, benchmark_data, benchmark_result_for_bias,
                        repeats=reps, progress=bar.progress,
                    )
                    st.session_state["analysis"] = analysis_result
                    st.session_state["analysis_cfg"] = cfg
                    st.session_state["analysis_signature"] = sig
                    st.session_state["analysis_benchmark"] = benchmark_result_for_bias
                except (LLMError, ValueError) as exc:
                    st.session_state.pop("analysis", None)
                    st.error(str(exc))

    analysis_result = st.session_state.get("analysis")
    current_bias_signature = _result_signature(benchmark_data, get_cfg(), benchmark_exam) if benchmark_data is not None and benchmark_exam is not None else None
    if analysis_result and (current_bias_signature is None or st.session_state.get("analysis_signature") != current_bias_signature):
        st.warning("These bias results are stale because the exam, rubric, dataset, reference marks, or judge settings changed. Run the checks again.")
        analysis_result = None
    if analysis_result and current_bias_signature is not None:
        analysis_cfg = st.session_state["analysis_cfg"]
        analysis_benchmark = st.session_state["analysis_benchmark"]
        st.info("Bias diagnostics use the current five-answer dataset. Results are descriptive for n=5 and do not establish general reliability.")
        if analysis_cfg.offline:
            st.warning("Offline baseline is keyword-based and deterministic. Perfect repeatability or position consistency does not validate LLM grading.")
        repeat, order, position, length = (
            analysis_result["repeatability"], analysis_result["order"],
            analysis_result["position"], analysis_result["length"],
        )
        columns = st.columns(4)
        columns[0].metric("Repeat std (marks)", f"{repeat['std']:.2f}", help="Variation across repeated calls to the same judge and input.")
        columns[1].metric("Criterion-order Δ (marks)", f"{order['max_delta']:.1f}", help="Difference between original, reversed, and shuffled criterion order.")
        columns[2].metric("Position consistency", f"{position['consistency_rate'] * 100:.0f}%", help="Percent of pairs where the same student wins after answer positions are swapped.")
        human_agreement = position.get("human_agreement_rate")
        columns[3].metric("Pairwise agreement vs human", "n/a" if human_agreement is None else f"{human_agreement * 100:.0f}%")
        st.markdown("**Verbosity bias — irrelevant filler appended**")
        st.caption("A positive delta means the score increased after irrelevant filler was appended. This is a diagnostic probe, not proof of general fairness.")
        st.dataframe(pd.DataFrame(analysis_result["verbosity"]).T, use_container_width=True)
        st.markdown("**Pairwise A/B position swap**")
        pairwise_display = pd.DataFrame(position["rows"]).rename(columns={
            "human_winner": "human_reference_winner",
            "agrees_with_human": "agrees_with_human_reference",
        })
        st.dataframe(pairwise_display, hide_index=True, use_container_width=True)
        st.markdown("**Answer length vs score correlation**")
        length_display = {
            key.replace("human_", "human_reference_"): ("n/a" if pd.isna(value) else round(float(value), 3))
            for key, value in length.items()
        }
        st.dataframe(pd.DataFrame([length_display]), hide_index=True, use_container_width=True)
        st.download_button(
            "⬇️ Bias and consistency report (Markdown)",
            bias_markdown(analysis_result, analysis_cfg, analysis_benchmark),
            "bias_consistency_analysis.md", "text/markdown",
        )

# ------------------------------------------------------------------ tab 4
with tab_prompts:
    st.markdown("#### Evaluator prompt templates")
    st.caption("Files live in `prompts/`. Edit them and restart to change grader behaviour.")
    with st.expander("Judge system prompt (rubric rules, CoT protocol, calibration bands, JSON schema)", expanded=True):
        st.code(read_prompt("judge_system.md"), language="markdown")
    with st.expander("Few-shot scoring examples"):
        st.json(json.loads(read_prompt("few_shot.json")), expanded=False)
    with st.expander("Pairwise (position-consistency) prompt"):
        st.code(read_prompt("pairwise_system.md"), language="markdown")
    with st.expander("Calibration criteria"):
        st.markdown(read_prompt("calibration.md"))
    with st.expander("Exact messages that will be sent for the current exam setup"):
        if rubric and question.strip() and model_answer.strip():
            msgs = build_grading_messages(question, model_answer, rubric, "<<student answer text>>", few_shot=few_shot)
            st.code("\n\n".join(f"[{m['role']}]\n{m['content']}" for m in msgs[-1:]), language="markdown")
            st.caption(f"{len(msgs)} messages in total (system + {len(msgs)-2} few-shot turns + task).")
        else:
            st.write("Fill in the question, model answer and rubric on the first tab.")

