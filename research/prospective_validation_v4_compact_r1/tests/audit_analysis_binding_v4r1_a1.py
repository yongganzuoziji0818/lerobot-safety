#!/usr/bin/env python3
"""Fail-closed exact-delta audit for the V4R1-A1 analysis successor."""

from __future__ import annotations

import difflib
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "analysis" / "analyze_formal_results_v4r1.py"
SUCCESSOR = ROOT / "analysis" / "analyze_formal_results_v4r1_a1.py"
SOURCE_SHA256 = "6d64cde5d55aa587df02aec183f289b0e9e271b46cdc2e8e32bb9ba7ace0cdae"
EXPECTED_REPLACEMENTS = {
    (
        'FORMAL_RECEIPT = V4R1 / "governance" / '
        '"FORMAL_EXECUTION_RECEIPT.json"'
    ): (
        'FORMAL_RECEIPT = V4R1 / "governance" / '
        '"FORMAL_EXECUTION_RECEIPT_E1.json"'
    ),
    (
        '        authorization.get("status") != '
        '"AUTHORIZED_V4R1_FORMAL_EXECUTION"'
    ): (
        '        authorization.get("status") != '
        '"AUTHORIZED_V4R1_E1_FORMAL_EXECUTION"'
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if sha256(SOURCE) != SOURCE_SHA256:
        raise RuntimeError("FROZEN_SOURCE_HASH_DRIFT")
    source_lines = SOURCE.read_text(encoding="utf-8").splitlines()
    successor_lines = SUCCESSOR.read_text(encoding="utf-8").splitlines()
    changes = [
        line
        for line in difflib.ndiff(source_lines, successor_lines)
        if line.startswith("- ") or line.startswith("+ ")
    ]
    expected = []
    for old, new in EXPECTED_REPLACEMENTS.items():
        expected.extend([f"- {old}", f"+ {new}"])
    if changes != expected:
        raise RuntimeError(
            "UNAUTHORIZED_ANALYSIS_DELTA:"
            + json.dumps(changes, ensure_ascii=True)
        )
    print(
        json.dumps(
            {
                "status": "PASS_V4R1_A1_EXACT_TWO_REPLACEMENT_AUDIT",
                "source_sha256": sha256(SOURCE),
                "successor_sha256": sha256(SUCCESSOR),
                "changed_lines": 2,
                "scientific_analysis_changed": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
