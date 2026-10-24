"""Baseline similarity metrics between student answer and model answer.

Uses the Hugging Face `evaluate` library (BLEU, ROUGE) when available and
falls back to faithful pure-Python implementations if the metric scripts
cannot be downloaded (offline / restricted network)."""
from __future__ import annotations
import math
import re
from collections import Counter
from functools import lru_cache


def tokenize(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", s.lower())


def _lcs_len(a, b) -> int:
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0]
        for j, y in enumerate(b, 1):
            cur.append(prev[j - 1] + 1 if x == y else max(prev[j], cur[j - 1]))
        prev = cur
    return prev[-1]


def _rouge_n(pred, ref, n):
    pg = Counter(tuple(pred[i:i + n]) for i in range(len(pred) - n + 1))
    rg = Counter(tuple(ref[i:i + n]) for i in range(len(ref) - n + 1))
    overlap = sum((pg & rg).values())
    p = overlap / max(sum(pg.values()), 1)
    r = overlap / max(sum(rg.values()), 1)
    return 0.0 if p + r == 0 else 2 * p * r / (p + r)


def _fallback(student: str, ref: str) -> dict:
    p, r = tokenize(student), tokenize(ref)
    lcs = _lcs_len(p, r)
    prec, rec = lcs / max(len(p), 1), lcs / max(len(r), 1)
    rl = 0.0 if prec + rec == 0 else 2 * prec * rec / (prec + rec)
    logs = 0.0
    for n in range(1, 5):
        pg = Counter(tuple(p[i:i + n]) for i in range(len(p) - n + 1))
        rg = Counter(tuple(r[i:i + n]) for i in range(len(r) - n + 1))
        match, total = sum((pg & rg).values()), sum(pg.values())
        if n == 1:
            if total == 0 or match == 0:
                logs = float("-inf")
                break
            logs += math.log(match / total)
        else:
            logs += math.log((match + 1) / (total + 1))
    if logs == float("-inf") or not p:
        bleu = 0.0
    else:
        bp = 1.0 if len(p) > len(r) else math.exp(1 - len(r) / max(len(p), 1))
        bleu = bp * math.exp(logs / 4)
    return {"bleu": bleu, "rouge1": _rouge_n(p, r, 1), "rouge2": _rouge_n(p, r, 2),
            "rougeL": rl, "rougeL_recall": rec, "backend": "pure-python fallback"}


def cosine_similarity(a: str, b: str) -> float:
    ca, cb = Counter(tokenize(a)), Counter(tokenize(b))
    dot = sum(ca[k] * cb[k] for k in ca)
    na = math.sqrt(sum(v * v for v in ca.values()))
    nb = math.sqrt(sum(v * v for v in cb.values()))
    return dot / (na * nb) if na and nb else 0.0


@lru_cache(maxsize=1)
def _load_evaluate():
    try:
        import evaluate
        return evaluate.load("bleu"), evaluate.load("rouge")
    except Exception:
        return None


def compute_metrics(student: str, model_answer: str) -> dict:
    """Return BLEU, ROUGE-1/2/L, ROUGE-L recall and cosine similarity (all 0-1)."""
    base = _fallback(student, model_answer)
    loaded = _load_evaluate()
    if loaded and student.strip():
        try:
            bleu_m, rouge_m = loaded
            try:
                b = bleu_m.compute(predictions=[student], references=[[model_answer]])["bleu"]
            except ZeroDivisionError:
                b = 0.0
            r = rouge_m.compute(predictions=[student], references=[model_answer])
            base.update({"bleu": float(b), "rouge1": float(r["rouge1"]),
                         "rouge2": float(r["rouge2"]), "rougeL": float(r["rougeL"]),
                         "backend": "HF evaluate (bleu, rouge)"})
        except Exception:
            pass
    base["cosine"] = cosine_similarity(student, model_answer)
    base["word_count"] = len(tokenize(student))
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in base.items()}
