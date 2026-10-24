"""Rubric helpers: validation, (de)serialisation, formatting for prompts."""
from __future__ import annotations
import json
from typing import Any

DEFAULT_RUBRIC = [
    {"name": "Technical Accuracy", "max_marks": 4,
     "description": "Concepts are described correctly, with no factual or conceptual errors.",
     "keywords": []},
    {"name": "Completeness", "max_marks": 3,
     "description": "All the key points required by the question are covered.",
     "keywords": []},
    {"name": "Nomenclature", "max_marks": 3,
     "description": "Correct technical terminology, symbols and standard names are used.",
     "keywords": []},
]


def clean_rubric(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate + normalise rubric rows (accepts keywords as list or comma string)."""
    out = []
    for r in rows:
        name = str(r.get("name", "") or "").strip()
        if not name or name.lower() == "nan":
            continue
        if len(name) > 100:
            raise ValueError("Criterion names must be 100 characters or fewer")
        try:
            mx = float(r.get("max_marks", 0))
        except (TypeError, ValueError):
            raise ValueError(f"Criterion '{name}': max_marks must be a number")
        if mx <= 0 or mx != mx:
            raise ValueError(f"Criterion '{name}': max_marks must be > 0")
        kw = r.get("keywords", [])
        if isinstance(kw, str):
            kw = [k.strip() for k in kw.split(",") if k.strip()]
        elif not isinstance(kw, (list, tuple)):
            kw = []
        desc = r.get("description", "")
        desc = "" if desc is None or (isinstance(desc, float) and desc != desc) else str(desc).strip()
        if len(desc) > 1000:
            raise ValueError(f"Criterion '{name}': description must be 1,000 characters or fewer")
        if len(kw) > 40:
            raise ValueError(f"Criterion '{name}': use at most 40 keywords")
        kw = [str(k).strip()[:120] for k in kw if str(k).strip()]
        out.append({"name": name, "max_marks": mx, "description": desc, "keywords": kw})
    if len(out) > 12:
        raise ValueError("Rubric may contain at most 12 criteria")
    if not out:
        raise ValueError("Rubric needs at least one criterion")
    names = [c["name"].lower() for c in out]
    if len(set(names)) != len(names):
        raise ValueError("Criterion names must be unique")
    return out


def total_marks(rubric) -> float:
    return float(sum(c["max_marks"] for c in rubric))


def fmt(x: float) -> str:
    return f"{x:g}"


def rubric_to_text(rubric) -> str:
    lines = []
    for i, c in enumerate(rubric, 1):
        lines.append(f"{i}. {c['name']} - {fmt(c['max_marks'])} marks: {c['description']}")
    lines.append(f"TOTAL: {fmt(total_marks(rubric))} marks")
    return "\n".join(lines)


def load_rubric(path: str) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        return clean_rubric(json.load(f))
