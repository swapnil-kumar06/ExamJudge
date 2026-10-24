"""Agreement statistics (numpy only)."""
from __future__ import annotations
import numpy as np


def _rank(x):
    x = np.asarray(x, float)
    order = x.argsort()
    ranks = np.empty(len(x))
    ranks[order] = np.arange(len(x), dtype=float)
    for v in np.unique(x):                    # average ties
        m = x == v
        ranks[m] = ranks[m].mean()
    return ranks


def pearson(a, b) -> float:
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 2 or a.std() == 0 or b.std() == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def spearman(a, b) -> float:
    return pearson(_rank(a), _rank(b))


def agreement(auto, human, max_total: float) -> dict:
    a, h = np.asarray(auto, float), np.asarray(human, float)
    err = a - h
    return {"n": int(len(a)),
            "MAE": float(np.abs(err).mean()),
            "RMSE": float(np.sqrt((err ** 2).mean())),
            "mean_signed_error": float(err.mean()),
            "pearson": pearson(a, h),
            "spearman": spearman(a, h),
            "within_0.5": float((np.abs(err) <= 0.5).mean()),
            "within_1.0": float((np.abs(err) <= 1.0).mean()),
            "MAE_pct_of_max": float(np.abs(err).mean() / max_total * 100)}
