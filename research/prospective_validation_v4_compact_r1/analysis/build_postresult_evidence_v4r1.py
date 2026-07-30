#!/usr/bin/env python3
"""Build deterministic result-reporting sidecars from sealed analyses only."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCI = ROOT.parent
V4 = ROOT / "analysis_results" / "V4R1-A1-ANALYSIS-001.json"
LIBERO = (
    SCI
    / "postresult_reframe"
    / "phase4_evidence"
    / "raw_remote"
    / "fixed_census_analysis.json"
)
OUT = ROOT / "postresult_evidence"
EXPECTED = {
    V4: "7a6cc1c97baaacdc0185504ed813a2f431bd45a639e1d086789cd16973e50c5b",
    LIBERO: "4d77af0938eb896ac9f812391583589076e5fd2d24736e05d1061f9463e045f2",
}
POLICIES = ("pi0", "pi05", "groot")
CONTRACTS = tuple(f"C{index}" for index in range(6))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json_once(path: Path, value: Any) -> None:
    if path.exists():
        raise RuntimeError(f"WRITE_ONCE_EXISTS:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_csv_once(path: Path, rows: list[dict[str, Any]]) -> None:
    if path.exists():
        raise RuntimeError(f"WRITE_ONCE_EXISTS:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    for path, expected in EXPECTED.items():
        if sha256(path) != expected:
            raise RuntimeError(f"INPUT_HASH:{path}")
    v4 = json.loads(V4.read_bytes())
    libero = json.loads(LIBERO.read_bytes())
    intervals = {
        item["estimand"]: item for item in v4["bootstrap"]["intervals"]
    }
    rate_rows: list[dict[str, Any]] = []
    for policy in POLICIES:
        for contract in CONTRACTS:
            label = f"rate:{policy}:{contract}"
            item = intervals[label]
            cells = [
                cell
                for cell in v4["partial_identification_task_cells"]
                if cell["policy"] == policy and cell["contract"] == contract
            ]
            rate_rows.append(
                {
                    "policy": policy,
                    "contract": contract,
                    "rate_per_1000_steps": item["estimate"],
                    "simultaneous_95_lower": item["simultaneous_95_lower"],
                    "simultaneous_95_upper": item["simultaneous_95_upper"],
                    "partial_lower_mean": sum(
                        cell["lower_bound_per_1000_steps"] for cell in cells
                    )
                    / 50,
                    "partial_upper_mean": sum(
                        cell["upper_bound_per_1000_steps"] for cell in cells
                    )
                    / 50,
                    "indeterminate_trajectories": sum(
                        cell["indeterminate"] for cell in cells
                    ),
                }
            )
    contrast_rows = [
        {
            "estimand": item["estimand"],
            "estimate": item["estimate"],
            "simultaneous_95_lower": item["simultaneous_95_lower"],
            "simultaneous_95_upper": item["simultaneous_95_upper"],
            "simultaneous_interval_excludes_zero": (
                item["simultaneous_95_lower"] > 0
                or item["simultaneous_95_upper"] < 0
            ),
        }
        for item in v4["bootstrap"]["intervals"]
        if item["estimand"].startswith(("contract:", "width:", "margin:"))
    ]
    libero_widths = {
        family: max(values["risk_mean_by_contract"].values())
        - min(values["risk_mean_by_contract"].values())
        for family, values in libero["family_summary"].items()
    }
    libero_orders = []
    for contract in libero["contracts"]:
        libero_orders.append(
            [
                family
                for family, _ in sorted(
                    libero["family_summary"].items(),
                    key=lambda item: item[1]["risk_mean_by_contract"][contract],
                )
            ]
        )
    cross_benchmark = {
        "protocol": "SEPARATE_DOMAINS_NO_POOLING",
        "libero": {
            "design_status": "HISTORICAL_POST_HOC",
            "trajectories": libero["trajectories"],
            "tasks": libero["tasks"],
            "risk_scale": "equal_task_weighted_trajectory_violation_proportion",
            "contract_widths": libero_widths,
            "strict_common_order": (
                libero_orders[0]
                if all(order == libero_orders[0] for order in libero_orders)
                else None
            ),
        },
        "robocasa": {
            "design_status": "PROSPECTIVE_FROZEN",
            "trajectories": v4["formal_scientific_trajectories"],
            "tasks": 50,
            "risk_scale": "matched_determinate_event_rate_per_1000_steps",
            "contract_widths": v4["estimands"]["contract_widths"],
            "ranking_robustness": v4["estimands"]["ranking_robustness"],
            "strict_common_order": v4["estimands"][
                "strict_common_architecture_order"
            ],
        },
        "classifications": {
            "cardinal_contract_sensitivity": "MIXED",
            "contract_robust_point_order": (
                "REPRODUCED_AT_BENCHMARK_PATTERN_LEVEL_ONLY"
            ),
            "direct_policy_effect_replication": "NOT_COMPARABLE",
            "pooled_effect_or_interval": "PROHIBITED_AND_NOT_COMPUTED",
        },
        "interpretation": (
            "The historical LIBERO domain shows large finite-contract widths, "
            "whereas the prospective RoboCasa domain shows small point widths "
            "whose simultaneous intervals include zero. Both domains exhibit "
            "a strict common point ordering over their own registered policy "
            "sets, but policy identities and risk scales are not exchangeable."
        ),
    }
    summary = {
        "schema_version": 1,
        "status": "PASS_V4R1_POSTRESULT_REPORTING_SIDECAR",
        "claim_boundary": (
            "Deterministic reporting of sealed estimands; no resampling, "
            "recomputation, pooling, new hypothesis test, or causal claim."
        ),
        "inputs": {str(path.relative_to(SCI)): digest for path, digest in EXPECTED.items()},
        "robocasa": {
            "formal_scientific_trajectories": 1200,
            "episode_contract_rows": 7200,
            "invalid_contract_rows": 0,
            "matched_exposure_steps_per_trajectory": 900,
            "bootstrap_replicates": 10000,
            "simultaneous_family_size": 57,
            "simultaneous_critical_value": v4["bootstrap"][
                "max_absolute_centered_deviation_critical"
            ],
            "rates": v4["estimands"]["rates"],
            "contract_widths": v4["estimands"]["contract_widths"],
            "ranking_robustness": v4["estimands"]["ranking_robustness"],
            "strict_common_order": v4["estimands"][
                "strict_common_architecture_order"
            ],
            "simultaneous_intervals_excluding_zero": [
                row["estimand"]
                for row in contrast_rows
                if row["simultaneous_interval_excludes_zero"]
            ],
            "descriptive_success": v4["task_success_descriptive_only"],
        },
        "cross_benchmark": cross_benchmark,
    }
    write_json_once(OUT / "V4R1_POSTRESULT_SUMMARY.json", summary)
    write_csv_once(OUT / "table_policy_contract_rates.csv", rate_rows)
    write_csv_once(OUT / "table_registered_contrasts.csv", contrast_rows)
    write_json_once(OUT / "CROSS_BENCHMARK_NO_POOLING_AUDIT.json", cross_benchmark)
    print("PASS_V4R1_POSTRESULT_REPORTING_SIDECAR")


if __name__ == "__main__":
    main()
