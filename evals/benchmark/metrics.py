"""Deterministic metric helpers. Zero denominators return None (NOT_EVALUABLE)."""

from __future__ import annotations

from typing import Any


def safe_div(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def precision(tp: int, fp: int) -> float | None:
    return safe_div(tp, tp + fp)


def recall(tp: int, fn: int) -> float | None:
    return safe_div(tp, tp + fn)


def f1(p: float | None, r: float | None) -> float | None:
    if p is None or r is None:
        return None
    return safe_div(2 * p * r, p + r)


def accuracy(correct: int, total: int) -> float | None:
    return safe_div(correct, total)


def field_exact_match(expected: Any, actual: Any) -> bool:
    if expected is None and actual is None:
        return True
    if isinstance(expected, str) and isinstance(actual, str):
        return expected.strip() == actual.strip()
    return expected == actual
