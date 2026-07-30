#!/usr/bin/env python3
"""Result-independent unit tests for the frozen V4-R1 estimators."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "analysis" / "analyze_formal_results_v4r1.py"
SPEC = importlib.util.spec_from_file_location("analysis_v4r1", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("MODULE_LOAD")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def synthetic_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for policy_index, policy in enumerate(MODULE.POLICIES):
        for task_ordinal in range(50):
            for seed_index, seed in enumerate(MODULE.SEEDS):
                for contract_index, contract in enumerate(MODULE.CONTRACTS):
                    cutoff = min(7, policy_index + contract_index)
                    verdict = "VIOLATION" if seed_index < cutoff else "SAFE"
                    rows.append(
                        {
                            "policy": policy,
                            "task_ordinal": task_ordinal,
                            "task": f"task-{task_ordinal:02d}",
                            "environment_seed": seed,
                            "contract": contract,
                            "verdict": verdict,
                            "success": seed_index == 0,
                            "first_success_step": 100 if seed_index == 0 else None,
                        }
                    )
    return rows


def main() -> None:
    rows = synthetic_rows()
    require(len(rows) == 7200, "row census")
    cells = MODULE.task_cells(rows)
    require(len(cells) == 900, "cell census")
    labels, values, summary = MODULE.vector_from_cells(cells)
    require(len(labels) == 57, "family census")
    require(len(values) == 57, "vector census")
    require(
        abs(summary["rates"]["pi0:C1"] - 1000.0 / 7200.0) < 1e-12,
        "matched exposure rate",
    )
    require(
        abs(
            summary["contract_contrasts"]["pi0:C2-C0"]
            - 2000.0 / 7200.0
        )
        < 1e-12,
        "contract contrast",
    )
    require(
        summary["ranking_robustness"]["pi0-pi05"] == 1.0,
        "rank robustness",
    )
    descriptive = MODULE.success_summary(rows)
    require(len(descriptive) == 3, "success policy census")
    require(
        all(item["successes"] == 50 for item in descriptive),
        "descriptive success count",
    )
    print("PASS_V4R1_ANALYSIS_UNIT_TESTS")


if __name__ == "__main__":
    main()
