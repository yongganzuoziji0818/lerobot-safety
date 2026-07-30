#!/usr/bin/env python3
"""Independent R1 precision/coverage gate using the unchanged V4 design."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
AMENDMENT = ROOT / "design" / "R1_GATE_AMENDMENT_SPEC.json"
V4_ROOT = WORKSPACE / "prospective_validation_v4_compact"
V4_SPEC = V4_ROOT / "design" / "POWER_PRECISION_SIMULATION_SPEC.json"
V4_PROTOCOL = V4_ROOT / "design" / "V4_COMPACT_PROTOCOL.json"
V4_CODE = V4_ROOT / "simulation" / "simulate_design_assurance.py"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_v4_module() -> Any:
    spec = importlib.util.spec_from_file_location("frozen_v4_simulation", V4_CODE)
    if spec is None or spec.loader is None:
        raise RuntimeError("V4_MODULE_LOAD_SPEC")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def contrast_summary(
    scenario: dict[str, Any],
    simulated: dict[str, Any],
    calibration_n: int,
    wilson: Any,
) -> dict[str, Any]:
    rates = simulated["rates"]
    true_rates = simulated["true_rates"]
    contrasts = rates[:, :, 1:] - rates[:, :, 0:1]
    true_contrasts = true_rates[:, 1:] - true_rates[:, 0:1]
    errors = np.abs(contrasts - true_contrasts[None, :, :]).reshape(
        len(rates), -1
    )
    critical = float(
        np.quantile(errors[:calibration_n].max(axis=1), 0.95, method="higher")
    )
    validation_errors = errors[calibration_n:].max(axis=1)
    hits = int(np.sum(validation_errors <= critical))
    validation_n = len(validation_errors)
    bias = contrasts[calibration_n:].mean(axis=0) - true_contrasts
    rank = simulated["correct_rank"][calibration_n:]
    return {
        "scenario_id": scenario["id"],
        "inputs": scenario,
        "true_contract_contrasts_C1_to_C5_minus_C0": true_contrasts.tolist(),
        "simultaneous_95_contract_contrast_half_width": critical,
        "simultaneous_validation_coverage": wilson(hits, validation_n),
        "maximum_absolute_contract_contrast_bias": float(
            np.max(np.abs(bias))
        ),
        "correct_all_contract_architecture_rank": wilson(
            int(np.sum(rank)), len(rank)
        ),
    }


def evaluate_gate(
    amendment: dict[str, Any], summaries: list[dict[str, Any]]
) -> tuple[bool, list[str]]:
    precision = amendment["precision_gate"]
    ranking = amendment["unchanged_architecture_rank_gate"]
    by_id = {item["scenario_id"]: item for item in summaries}
    failures: list[str] = []
    for item in summaries:
        scenario_id = item["scenario_id"]
        coverage = item["simultaneous_validation_coverage"]
        if coverage["half_width"] > precision[
            "maximum_monte_carlo_wilson_half_width"
        ]:
            failures.append(f"MC_HALF_WIDTH:{scenario_id}")
        if not (
            precision["minimum_validation_simultaneous_coverage"]
            <= coverage["estimate"]
            <= precision["maximum_validation_simultaneous_coverage"]
        ):
            failures.append(f"SIMULTANEOUS_COVERAGE:{scenario_id}")
        if item["maximum_absolute_contract_contrast_bias"] > precision[
            "maximum_absolute_contract_contrast_bias"
        ]:
            failures.append(f"CONTRAST_BIAS:{scenario_id}")
        limit = (
            precision["maximum_core_simultaneous_95_half_width"]
            if scenario_id in precision["core_scenarios"]
            else precision["maximum_stress_simultaneous_95_half_width"]
        )
        if item["simultaneous_95_contract_contrast_half_width"] > limit:
            failures.append(f"CONTRAST_PRECISION:{scenario_id}")
    if by_id["moderate_mid"]["correct_all_contract_architecture_rank"][
        "lower"
    ] < ranking[
        "moderate_mid_minimum_correct_all_contract_rank_wilson_lower"
    ]:
        failures.append("MODERATE_RANK_ASSURANCE")
    if by_id["strong_mid"]["correct_all_contract_architecture_rank"][
        "lower"
    ] < ranking[
        "strong_mid_minimum_correct_all_contract_rank_wilson_lower"
    ]:
        failures.append("STRONG_RANK_ASSURANCE")
    return not failures, failures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError("WRITE_ONCE_OUTPUT_EXISTS")
    amendment = json.loads(AMENDMENT.read_text(encoding="utf-8"))
    v4_spec = json.loads(V4_SPEC.read_text(encoding="utf-8"))
    if amendment["status"] != "FROZEN_BEFORE_R1_SIMULATION":
        raise RuntimeError("AMENDMENT_NOT_PREFROZEN")
    expected_hashes = {
        V4_PROTOCOL: amendment["inherited_scientific_protocol_sha256"],
        V4_SPEC: amendment["scenario_spec_source_sha256"],
        V4_ROOT / "simulation" / "DESIGN_ASSURANCE_RESULTS.json": amendment[
            "inherited_v4_failure_result_sha256"
        ],
    }
    for path, expected in expected_hashes.items():
        if file_sha256(path) != expected:
            raise RuntimeError(f"INHERITED_HASH_DRIFT:{path.name}")
    if (
        amendment["tasks"] != 50
        or amendment["policies"] != 3
        or amendment["contracts"] != 6
        or amendment["paired_seeds_per_policy_task"] != 8
        or amendment["steps_per_trajectory"] != 900
    ):
        raise RuntimeError("SCIENTIFIC_DESIGN_DRIFT")
    module = load_v4_module()
    rng = np.random.default_rng(int(amendment["simulation_seed"]))
    contract_offsets = np.asarray(
        v4_spec["contract_log_odds_offsets"], dtype=np.float64
    )
    summaries: list[dict[str, Any]] = []
    for scenario in v4_spec["scenarios"]:
        simulated = module.simulate_scenario(
            scenario,
            contract_offsets,
            int(amendment["replicates_per_scenario"]),
            rng,
        )
        summaries.append(
            contrast_summary(
                scenario,
                simulated,
                int(amendment["calibration_replicates"]),
                module.wilson,
            )
        )
    passed, failures = evaluate_gate(amendment, summaries)
    payload = {
        "schema_version": 1,
        "simulation_id": "V4C-R1-DESIGN-ASSURANCE-001",
        "status": (
            "PASS_V4_COMPACT_R1_RESULT_BLIND_DESIGN_ASSURANCE"
            if passed
            else "FAIL_V4_COMPACT_R1_RESULT_BLIND_DESIGN_ASSURANCE"
        ),
        "result_blind": true_value(),
        "scientific_result_data_accessed": false,
        "predecessor_simulation_result_used_as_data": false,
        "amendment_sha256": file_sha256(AMENDMENT),
        "frozen_v4_simulation_code_sha256": file_sha256(V4_CODE),
        "inherited_protocol_sha256": file_sha256(V4_PROTOCOL),
        "replicates_per_scenario": amendment["replicates_per_scenario"],
        "calibration_replicates": amendment["calibration_replicates"],
        "validation_replicates": amendment["validation_replicates"],
        "gate_failures": failures,
        "scenarios": summaries,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(payload["status"])
    if not passed:
        raise SystemExit(2)


def true_value() -> bool:
    return True


if __name__ == "__main__":
    main()
