# -*- coding: utf-8 -*-
"""
prob_model.py

Загрузка и применение "вероятностной" модели на основе бэктеста:
мы не угадываем будущее, а показываем эмпирические вероятности для похожих сетапов.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


@dataclass(frozen=True)
class ProbEstimate:
    n: int
    p_tp1: float
    p_tp2: float
    p_tp3: float
    p_sl: float
    avg_r: float


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def load_model(path: str) -> Optional[Dict[str, Any]]:
    try:
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _bucket_quality(q: int) -> str:
    if q < 50:
        return "<50"
    if q < 60:
        return "50-59"
    if q < 70:
        return "60-69"
    if q < 80:
        return "70-79"
    return "80+"


def estimate(
    model: Dict[str, Any],
    *,
    setup: str,
    direction: str,
    trend: str,
    quality: int,
) -> Optional[ProbEstimate]:
    """
    Возвращает вероятность достижений целей/стопа для похожего набора условий.
    Ключ: setup|direction|trend|q_bucket
    """
    if not model:
        return None

    setup = (setup or "UNKNOWN").upper()
    direction = (direction or "UNKNOWN").upper()
    trend = (trend or "UNKNOWN").upper()
    q_bucket = _bucket_quality(int(quality or 0))

    key = f"{setup}|{direction}|{trend}|{q_bucket}"
    row = (model.get("buckets") or {}).get(key)
    if not isinstance(row, dict):
        # fallback: ignore trend
        key2 = f"{setup}|{direction}|ANY|{q_bucket}"
        row = (model.get("buckets") or {}).get(key2)
    if not isinstance(row, dict):
        return None

    n = int(row.get("n") or 0)
    if n <= 0:
        return None

    return ProbEstimate(
        n=n,
        p_tp1=_safe_float(row.get("p_tp1")),
        p_tp2=_safe_float(row.get("p_tp2")),
        p_tp3=_safe_float(row.get("p_tp3")),
        p_sl=_safe_float(row.get("p_sl")),
        avg_r=_safe_float(row.get("avg_r")),
    )


