#!/usr/bin/env python3
"""Deterministically derive decision regions from sealed V4/V5 summaries."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


EXPECTED_V4_SHA256 = "7a6cc1c97baaacdc0185504ed813a2f431bd45a639e1d086789cd16973e50c5b"
EXPECTED_V5_SHA256 = "2f522de7173c181dad34ff7efd079821159bf915998670aad0c6126783d7c538"
EXPECTED_V6_MANIFEST_SHA256 = "858bda2ad7a6e652b717889f7d69a053bfd1e55a47369c4fcc26f0765b1bbcc6"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def summarize_domain(domain: str, unit: str, rates: dict[str, dict[str, float]], order: list[str]) -> dict:
    rows = []
    for policy in order:
        values = rates[policy]
        minimum = min(values.values())
        maximum = max(values.values())
        rows.append(
            {
                "domain": domain,
                "policy": policy,
                "unit": unit,
                "minimum_point_risk": minimum,
                "maximum_point_risk": maximum,
                "threshold_ambiguity_band": [minimum, maximum],
                "band_left_closed_right_open": True,
                "band_width": maximum - minimum,
                "argmin_contracts": sorted(k for k, v in values.items() if v == minimum),
                "argmax_contracts": sorted(k for k, v in values.items() if v == maximum),
            }
        )

    edges = []
    for lower, higher in zip(order, order[1:]):
        paired_gap = min(rates[higher][c] - rates[lower][c] for c in rates[lower])
        arbitrary_gap = min(rates[higher].values()) - max(rates[lower].values())
        edges.append(
            {
                "domain": domain,
                "lower_point_risk_policy": lower,
                "higher_point_risk_policy": higher,
                "paired_contract_minimum_gap": paired_gap,
                "arbitrary_contract_minimum_gap": arbitrary_gap,
                "point_order_robust_paired_contract": paired_gap > 0,
                "point_order_robust_arbitrary_contract": arbitrary_gap > 0,
                "sampling_separation_not_inferred": True,
            }
        )
    return {"decision_regions": rows, "adjacent_order_edges": edges}


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    extension_root = Path(__file__).resolve().parents[1]
    v4_path = project_root / "prospective_validation_v4_compact_r1" / "analysis_results" / "V4R1-A1-ANALYSIS-001.json"
    v5_path = project_root / "prospective_validation_v5_realworld" / "postresult" / "V5-ARMBENCH-FORMAL-ANALYSIS-001" / "reporting" / "V5_POLICY_CONTRACT_RISKS.csv"
    v6_manifest = project_root / "prospective_validation_v6_nonhardware" / "V6_NONHARDWARE_TERMINAL_MANIFEST.sha256"

    observed = {
        "v4_aggregate_sha256": sha256(v4_path),
        "v5_policy_contract_table_sha256": sha256(v5_path),
        "v6_terminal_manifest_sha256": sha256(v6_manifest),
    }
    expected = {
        "v4_aggregate_sha256": EXPECTED_V4_SHA256,
        "v5_policy_contract_table_sha256": EXPECTED_V5_SHA256,
        "v6_terminal_manifest_sha256": EXPECTED_V6_MANIFEST_SHA256,
    }
    if observed != expected:
        raise SystemExit(f"input hash mismatch: observed={observed!r}")

    v4 = json.loads(v4_path.read_text(encoding="utf-8"))
    v4_flat = v4["estimands"]["rates"]
    v4_rates: dict[str, dict[str, float]] = {"pi0": {}, "pi0.5": {}, "groot_n1.5": {}}
    v4_policy_map = {"pi0": "pi0", "pi05": "pi0.5", "groot": "groot_n1.5"}
    for key, value in v4_flat.items():
        policy, contract = key.split(":", 1)
        v4_rates[v4_policy_map[policy]][contract] = float(value)

    v5_rates: dict[str, dict[str, float]] = {"pi0": {}, "pi0.5": {}, "groot_n1.7": {}}
    v5_policy_map = {"pi0": "pi0", "pi0.5": "pi0.5", "grootn1.7": "groot_n1.7"}
    with v5_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            v5_rates[v5_policy_map[row["policy"]]][row["contract"]] = float(row["task_macro_risk"])

    v4_summary = summarize_domain(
        "prospective_robocasa",
        "events_per_1000_environment_steps",
        v4_rates,
        ["pi0.5", "pi0", "groot_n1.5"],
    )
    v5_summary = summarize_domain(
        "external_armnetbench_physical_episodes",
        "equal_task_macro_outcome_risk",
        v5_rates,
        ["pi0.5", "pi0", "groot_n1.7"],
    )

    payload = {
        "schema_version": 1,
        "status": "PASS_DETERMINISTIC_POSTHOC_REPORTING_EXTENSION",
        "analysis_type": "deterministic_posthoc_decision_consequence_map",
        "input_sha256": observed,
        "domains": [v4_summary, v5_summary],
        "decision_rule": "accept if point risk <= tau; robust accept if max risk <= tau; robust reject if min risk > tau; otherwise defer",
        "claim_boundary": "threshold bands are not safety limits, confidence intervals, calibrated consequences, or deployment recommendations; point-order gaps do not replace frozen simultaneous sampling intervals",
        "no_resampling_or_model_fitting": True,
        "no_domain_pooling": True,
    }
    output = extension_root / "results" / "DECISION_CONSEQUENCE_MAP.json"
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
