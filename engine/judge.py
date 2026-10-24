"""Grading engine: evidence-based LLM-as-a-Judge (T=0.0) + offline keyword baseline."""
from __future__ import annotations
import math
import re
from dataclasses import dataclass, field

from .llm_client import OFFLINE, chat_json, LLMError
from .metrics import compute_metrics, tokenize
from .prompts import build_grading_messages, build_pairwise_messages
from .rubric import total_marks


@dataclass
class JudgeConfig:
    provider: str = OFFLINE
    api_key: str = ""
    base_url: str = ""
    model: str = "keyword-rubric-baseline"
    few_shot: bool = True
    include_metrics: bool = False     # feeding BLEU/ROUGE to the judge can anchor it; off by default
    max_retries: int = 2
    temperature: float = field(default=0.0, init=False)  # fixed by design

    @property
    def offline(self) -> bool:
        return self.provider == OFFLINE


def _round_half(x: float) -> float:
    return round(x * 2) / 2


def _as_list(v):
    if v is None:
        return []
    if isinstance(v, str):
        return [v] if v.strip() else []
    return [str(i) for i in v if str(i).strip()]


def normalise_result(raw: dict, rubric) -> dict:
    """Validate the judge JSON: align criteria with rubric, clamp, round, recompute total."""
    by_name = {str(c.get("name", "")).strip().lower(): c for c in raw.get("criteria", []) if isinstance(c, dict)}
    crits, warnings = [], []
    for rc in rubric:
        got = by_name.get(rc["name"].lower())
        if got is None:
            warnings.append(f"Judge omitted criterion '{rc['name']}' - scored 0")
            got = {}
        try:
            s = float(got.get("score", 0))
        except (TypeError, ValueError):
            s, _ = 0.0, warnings.append(f"Non-numeric score for '{rc['name']}'")
        if math.isnan(s):
            s = 0.0
        if s > rc["max_marks"] or s < 0:
            warnings.append(f"Score for '{rc['name']}' clamped into [0, {rc['max_marks']:g}]")
        s = _round_half(min(max(s, 0.0), rc["max_marks"]))
        crits.append({"name": rc["name"], "max_marks": rc["max_marks"], "score": s,
                      "reasoning": str(got.get("reasoning", "")),
                      "evidence": _as_list(got.get("evidence")),
                      "deficiencies": _as_list(got.get("deficiencies"))})
    return {"criteria": crits,
            "total": sum(c["score"] for c in crits),
            "max_total": total_marks(rubric),
            "conceptual_deficiencies": _as_list(raw.get("conceptual_deficiencies")),
            "strengths": _as_list(raw.get("strengths")),
            "feedback": str(raw.get("feedback", "")),
            "warnings": warnings}


# ---------------- offline keyword baseline ----------------
def _kw_hit(kw: str, answer_tokens: list[str]) -> bool:
    """kw may contain alternatives separated by '|'; multi-word phrases need every word (prefix match)."""
    for alt in kw.split("|"):
        words = tokenize(alt)
        if words and all(any(t.startswith(w[:5]) for t in answer_tokens) for w in words):
            return True
    return False


def baseline_grade(student, rubric, metrics) -> dict:
    toks = tokenize(student)
    crits = []
    for rc in rubric:
        kws = rc.get("keywords") or []
        if kws:
            hits = [k for k in kws if _kw_hit(k, toks)]
            cov = len(hits) / len(kws)
            miss = [k.split("|")[0] for k in kws if k not in hits]
            reasoning = (f"[offline baseline] {len(hits)}/{len(kws)} expected concepts found. "
                         f"Missing: {', '.join(miss) if miss else 'none'}. Cannot detect factual errors.")
            defs = [f"Missing concept: {m}" for m in miss]
        else:
            cov = min(1.0, metrics["rougeL_recall"] * 1.5)
            reasoning = "[offline baseline] no keywords defined; scored from ROUGE-L recall vs model answer."
            defs = [] if cov > 0.7 else ["Content overlaps little with the model answer"]
        crits.append({"name": rc["name"], "reasoning": reasoning, "evidence": [],
                      "deficiencies": defs, "score": _round_half(cov * rc["max_marks"])})
    return {"criteria": crits}


def grade_answer(student_text, question, model_answer, rubric, cfg: JudgeConfig, shuffle_rubric=None) -> dict:
    """Grade one answer. `shuffle_rubric` (list of indices) changes the criteria order shown to the judge."""
    metrics = compute_metrics(student_text, model_answer)
    shown = [rubric[i] for i in shuffle_rubric] if shuffle_rubric else rubric
    if not student_text.strip():
        raw = {"criteria": [], "feedback": "No answer text was found.",
               "conceptual_deficiencies": ["Blank answer"]}
        judge = "blank-answer rule"
    elif cfg.offline:
        raw = baseline_grade(student_text, shown, metrics)
        judge = "offline keyword baseline"
        missing = [d for c in raw["criteria"] for d in c["deficiencies"]]
        raw["conceptual_deficiencies"] = missing[:6]
        raw["feedback"] = ("Automatic baseline feedback: revise the missing concepts listed above and use "
                           "the standard technical terms. Connect an LLM judge for detailed, reasoned feedback.")
    else:
        msgs = build_grading_messages(question, model_answer, shown, student_text,
                                      few_shot=cfg.few_shot, metrics=metrics if cfg.include_metrics else None)
        raw = chat_json(cfg, msgs)
        judge = f"LLM-as-a-Judge ({cfg.provider} / {cfg.model})"
    res = normalise_result(raw, shown)
    if shuffle_rubric:  # restore canonical order for reporting
        order = {c["name"]: c for c in res["criteria"]}
        res["criteria"] = [order[c["name"]] for c in rubric]
    res.update({"judge": judge, "model": cfg.model, "temperature": 0.0, "metrics": metrics})
    return res


def pairwise_winner(question, model_answer, rubric, a, b, cfg: JudgeConfig) -> str:
    """Return 'A', 'B' or 'TIE' for the order (a, b) as presented."""
    if cfg.offline:
        ta = grade_answer(a, question, model_answer, rubric, cfg)["total"]
        tb = grade_answer(b, question, model_answer, rubric, cfg)["total"]
        return "A" if ta > tb else "B" if tb > ta else "TIE"
    raw = chat_json(cfg, build_pairwise_messages(question, model_answer, rubric, a, b))
    w = str(raw.get("winner", "")).strip().upper()
    if w not in {"A", "B", "TIE"}:
        raise LLMError(f"Bad pairwise verdict: {w}")
    return w
