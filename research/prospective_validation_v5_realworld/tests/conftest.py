"""Public-release import path for the byte-identical frozen V5 test."""

from __future__ import annotations

import sys
from pathlib import Path


ANALYSIS = Path(__file__).resolve().parents[1] / "analysis"
sys.path.insert(0, str(ANALYSIS))
