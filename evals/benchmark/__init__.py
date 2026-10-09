"""Offline / live / baseline evaluation benchmark package for AI Career OS.

This package is evaluation infrastructure. Offline mode never calls providers.
Live and baseline modes exit safely with NOT_RUN when keys or consented samples
are missing. Do not treat synthetic fixture scores as product quality evidence.
"""

from __future__ import annotations

__all__ = ["SUITE_NAMES", "MODES"]

SUITE_NAMES = ("jd", "match", "rewrite", "interview", "all")
MODES = ("offline", "live", "baseline")
