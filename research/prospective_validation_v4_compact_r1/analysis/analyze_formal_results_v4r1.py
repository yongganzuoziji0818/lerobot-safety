#!/usr/bin/env python3
"""Frozen post-result analysis for V4-Compact-R1."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path("/workspace/lerobot-safety")
if ROOT.is_dir():
    V3B = ROOT / "research" / "prospective_validation_v3b"
    V4R1 = ROOT / "research" / "prospective_validation_v4_compact_r1"
else:
    SCI_ROOT = Path(__file__).resolve().parents[2]
    V3B = SCI_ROOT / "prospective_validation_v3b"
    V4R1 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V3B / "scripts"))
sys.path.insert(0, str(V4R1 / "production"))

from evaluator_primary import CONTRACTS, evaluate as evaluate_primary  # noqa: E402
from evaluator_reference import evaluate as evaluate_reference  # noqa: E402
from production_common_v4r1 import file_sha256, write_json_once  # noqa: E402

POLICIES = ("pi0", "pi05", "groot")
PAIRS = (("pi0", "pi05"), ("pi0", "groot"), ("pi05", "groot"))
SEEDS = tuple(range(42, 50))
TASK_FILE = V3B / "benchmark" / "task_set_target50.txt"
FORMAL_RECEIPT = V4R1 / "governance" / "FORMAL_EXECUTION_RECEIPT.json"
BOOTSTRAP_REPLICATES = 10_000
BOOTSTRAP_SEED = 20_260_728
STRATA = (tuple(range(0, 18)), tuple(range(18, 34)), tuple(range(34, 50)))


def tasks() -> list[str]:
    values = [
        line.strip()
        for line in TASK_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    if len(values) != 50 or len(set(values)) != 50:
        raise RuntimeError("TASK_CENSUS")
    return values


def load_rows(formal_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    authorization = json.loads(FORMAL_RECEIPT.read_text(encoding="utf-8"))
    run_receipt = json.loads(
        (formal_root / "formal_run_receipt.json").read_text(encoding="utf-8")
    )
    if (
        authorization.get("status") != "AUTHORIZED_V4R1_FORMAL_EXECUTION"
        or run_receipt.get("status") != "PASS_V4R1_COMPLETE_FORMAL_RUN"
        or run_receipt.get("attempt_id")
        != authorization.get("formal_attempt_id")
        or run_receipt.get("formal_scientific_trajectories") != 1200
        or run_receipt.get("policy_task_shard_count") != 150
    ):
        raise RuntimeError("FORMAL_RUN_RECEIPT")
    task_values = tasks()
    rows: list[dict[str, Any]] = []
    trajectory_keys: set[tuple[str, int, int]] = set()
    for policy in POLICIES:
        for ordinal, task in enumerate(task_values):
            shard = formal_root / "shards" / policy / f"{ordinal:02d}_{task}"
            shard_receipt = json.loads(
                (shard / "shard_receipt.json").read_text(encoding="utf-8")
            )
            if (
                shard_receipt.get("status")
                != "PASS_V4R1_FORMAL_POLICY_TASK_SHARD"
                or shard_receipt.get("episode_count") != 8
                or shard_receipt.get("formal_scientific_trajectories") != 8
            ):
                raise RuntimeError(f"SHARD_RECEIPT:{policy}:{ordinal}")
            for episode_index, environment_seed in enumerate(SEEDS):
                episode_dir = shard / "episodes" / f"{episode_index:02d}"
                receipt_path = episode_dir / "episode_receipt.json"
                trace_path = episode_dir / "trace.json.gz"
                episode = json.loads(receipt_path.read_text(encoding="utf-8"))
                key = (policy, ordinal, environment_seed)
                if key in trajectory_keys:
                    raise RuntimeError(f"DUPLICATE_TRAJECTORY:{key}")
                trajectory_keys.add(key)
                if (
                    episode.get("status") != "PASS_V4R1_FORMAL_EPISODE"
                    or episode.get("attempt_id")
                    != authorization.get("formal_attempt_id")
                    or episode.get("policy") != policy
                    or episode.get("task") != task
                    or episode.get("task_ordinal") != ordinal
                    or episode.get("episode_index") != episode_index
                    or episode.get("environment_seed") != environment_seed
                    or episode.get("environment_actions") != 900
                    or episode.get("formal_horizon") != 900
                    or episode.get("terminal_reason") != "horizon"
                    or episode.get("trace_sha256") != file_sha256(trace_path)
                    or episode.get("dual_evaluator_exact_agreement") is not True
                    or episode.get("invalid_contracts") != []
                    or episode.get("adapter_action_mutation") is not False
                ):
                    raise RuntimeError(
                        f"EPISODE_RECEIPT:{policy}:{ordinal}:{episode_index}"
                    )
                with gzip.open(trace_path, "rt", encoding="ascii") as handle:
                    trace = json.load(handle)
                for contract in CONTRACTS:
                    primary = evaluate_primary(trace, contract)
                    reference = evaluate_reference(trace, contract)
                    if (
                        primary != reference
                        or primary != episode["verdicts"].get(contract)
                        or primary["verdict"] == "INVALID"
                    ):
                        raise RuntimeError(
                            f"EVALUATOR:{policy}:{ordinal}:"
                            f"{environment_seed}:{contract}"
                        )
                    rows.append(
                        {
                            "policy": policy,
                            "task_ordinal": ordinal,
                            "task": task,
                            "environment_seed": environment_seed,
                            "contract": contract,
                            "verdict": primary["verdict"],
                            "success": bool(episode["success"]),
                            "first_success_step": episode.get(
                                "first_success_step"
                            ),
                        }
                    )
    if len(trajectory_keys) != 1200 or len(rows) != 7200:
        raise RuntimeError(
            f"ROW_CENSUS:{len(trajectory_keys)}:{len(rows)}"
        )
    return rows, run_receipt


def task_cells(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["policy"], row["task_ordinal"], row["contract"])].append(row)
    cells: list[dict[str, Any]] = []
    for policy in POLICIES:
        for ordinal in range(50):
            for contract in CONTRACTS:
                group = grouped[(policy, ordinal, contract)]
                seeds = sorted(int(row["environment_seed"]) for row in group)
                counts = {
                    verdict: sum(row["verdict"] == verdict for row in group)
                    for verdict in ("SAFE", "VIOLATION", "INDETERMINATE")
                }
                determinate = counts["SAFE"] + counts["VIOLATION"]
                if len(group) != 8 or seeds != list(SEEDS) or determinate == 0:
                    raise RuntimeError(
                        f"TASK_CELL:{policy}:{ordinal}:{contract}"
                    )
                rate = (
                    1000.0
                    * counts["VIOLATION"]
                    / (900.0 * determinate)
                )
                cells.append(
                    {
                        "policy": policy,
                        "task_ordinal": ordinal,
                        "contract": contract,
                        "safe": counts["SAFE"],
                        "violations": counts["VIOLATION"],
                        "indeterminate": counts["INDETERMINATE"],
                        "determinate_exposure_steps": 900 * determinate,
                        "rate_per_1000_steps": rate,
                        "lower_bound_per_1000_steps": (
                            1000.0 * counts["VIOLATION"] / 7200.0
                        ),
                        "upper_bound_per_1000_steps": (
                            1000.0
                            * (
                                counts["VIOLATION"]
                                + counts["INDETERMINATE"]
                            )
                            / 7200.0
                        ),
                    }
                )
    if len(cells) != 900:
        raise RuntimeError("TASK_CELL_CENSUS")
    return cells


def vector_from_cells(
    cells: list[dict[str, Any]],
    sampled_ordinals: list[int] | None = None,
) -> tuple[list[str], list[float], dict[str, Any]]:
    lookup = {
        (cell["policy"], cell["task_ordinal"], cell["contract"]): float(
            cell["rate_per_1000_steps"]
        )
        for cell in cells
    }
    ordinals = sampled_ordinals if sampled_ordinals is not None else list(range(50))
    rates: dict[tuple[str, str], float] = {}
    labels: list[str] = []
    values: list[float] = []
    for policy in POLICIES:
        for contract in CONTRACTS:
            value = sum(lookup[(policy, ordinal, contract)] for ordinal in ordinals) / len(ordinals)
            rates[(policy, contract)] = value
            labels.append(f"rate:{policy}:{contract}")
            values.append(value)
    contrasts: dict[str, float] = {}
    widths: dict[str, float] = {}
    for policy in POLICIES:
        reference = rates[(policy, "C0")]
        policy_values = [rates[(policy, contract)] for contract in CONTRACTS]
        for contract in CONTRACTS[1:]:
            value = rates[(policy, contract)] - reference
            contrasts[f"{policy}:{contract}-C0"] = value
            labels.append(f"contract:{policy}:{contract}-C0")
            values.append(value)
        width = max(policy_values) - min(policy_values)
        widths[policy] = width
        labels.append(f"width:{policy}")
        values.append(width)
    margins: dict[str, float] = {}
    pair_signs: dict[tuple[str, str], list[int]] = {}
    for first, second in PAIRS:
        signs: list[int] = []
        for contract in CONTRACTS:
            margin = rates[(first, contract)] - rates[(second, contract)]
            margins[f"{first}-{second}:{contract}"] = margin
            labels.append(f"margin:{first}-{second}:{contract}")
            values.append(margin)
            signs.append(0 if margin == 0.0 else (1 if margin > 0.0 else -1))
        pair_signs[(first, second)] = signs
    robustness: dict[str, float] = {}
    for pair, signs in pair_signs.items():
        score = sum(sign == signs[0] for sign in signs) / len(signs)
        key = f"{pair[0]}-{pair[1]}"
        robustness[key] = score
        labels.append(f"rank_robustness:{key}")
        values.append(score)
    strict_orders = []
    for contract in CONTRACTS:
        ordered = sorted(POLICIES, key=lambda policy: rates[(policy, contract)])
        distinct = len({rates[(policy, contract)] for policy in POLICIES}) == 3
        strict_orders.append(tuple(ordered) if distinct else tuple())
    summary = {
        "rates": {f"{p}:{c}": v for (p, c), v in rates.items()},
        "contract_contrasts": contrasts,
        "contract_widths": widths,
        "architecture_margins": margins,
        "ranking_robustness": robustness,
        "strict_common_architecture_order": (
            list(strict_orders[0])
            if strict_orders[0]
            and all(order == strict_orders[0] for order in strict_orders)
            else None
        ),
    }
    return labels, values, summary


def bootstrap(cells: list[dict[str, Any]], point: list[float]) -> dict[str, Any]:
    rng = random.Random(BOOTSTRAP_SEED)
    maxima: list[float] = []
    replicates: list[list[float]] = []
    labels, _, _ = vector_from_cells(cells)
    for _ in range(BOOTSTRAP_REPLICATES):
        sampled = [
            ordinal
            for stratum in STRATA
            for ordinal in rng.choices(stratum, k=len(stratum))
        ]
        replicate_labels, values, _ = vector_from_cells(cells, sampled)
        if replicate_labels != labels:
            raise RuntimeError("BOOTSTRAP_LABEL_DRIFT")
        replicates.append(values)
        maxima.append(max(abs(value - centre) for value, centre in zip(values, point)))
    critical = sorted(maxima)[int(0.95 * BOOTSTRAP_REPLICATES) - 1]
    intervals = [
        {
            "estimand": label,
            "estimate": estimate,
            "simultaneous_95_lower": estimate - critical,
            "simultaneous_95_upper": estimate + critical,
        }
        for label, estimate in zip(labels, point)
    ]
    return {
        "replicates": BOOTSTRAP_REPLICATES,
        "seed": BOOTSTRAP_SEED,
        "resampling_unit": "task_within_frozen_stratum",
        "family_size": len(labels),
        "max_absolute_centered_deviation_critical": critical,
        "intervals": intervals,
    }


def success_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[str, int, int], dict[str, Any]] = {}
    for row in rows:
        key = (row["policy"], row["task_ordinal"], row["environment_seed"])
        unique.setdefault(key, row)
    result = []
    for policy in POLICIES:
        policy_rows = [row for key, row in unique.items() if key[0] == policy]
        result.append(
            {
                "policy": policy,
                "trajectories": len(policy_rows),
                "successes": sum(bool(row["success"]) for row in policy_rows),
                "success_rate_descriptive": sum(bool(row["success"]) for row in policy_rows) / len(policy_rows),
                "median_first_success_step_descriptive": (
                    sorted(
                        int(row["first_success_step"])
                        for row in policy_rows
                        if row["first_success_step"] is not None
                    )[sum(row["first_success_step"] is not None for row in policy_rows) // 2]
                    if any(row["first_success_step"] is not None for row in policy_rows)
                    else None
                ),
            }
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--formal-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError("WRITE_ONCE_OUTPUT_EXISTS")
    rows, run_receipt = load_rows(args.formal_root)
    cells = task_cells(rows)
    labels, point, summary = vector_from_cells(cells)
    bootstrap_result = bootstrap(cells, point)
    payload = {
        "schema_version": 1,
        "status": "PASS_V4R1_FROZEN_ANALYSIS",
        "attempt_id": run_receipt["attempt_id"],
        "formal_scientific_trajectories": 1200,
        "episode_contract_rows": 7200,
        "invalid_contract_rows": 0,
        "independent_inference_unit": "task",
        "matched_exposure_steps_per_trajectory": 900,
        "estimand_labels": labels,
        "estimands": summary,
        "bootstrap": bootstrap_result,
        "partial_identification_task_cells": cells,
        "task_success_descriptive_only": success_summary(rows),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json_once(args.output, payload)
    print(
        "PASS_V4R1_FROZEN_ANALYSIS "
        f"trajectories=1200 rows=7200 bootstrap={BOOTSTRAP_REPLICATES}"
    )


if __name__ == "__main__":
    main()
