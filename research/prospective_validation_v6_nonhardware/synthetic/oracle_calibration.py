#!/usr/bin/env python3
"""Prospectively frozen known-ground-truth calibration for V6."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


SEED = 2_026_080_101
MC_REPEATS = 500
COVERAGE_REPEATS = 200
BOOTSTRAP_REPEATS = 1_000
STRATA = 3
POPULATION_PER_STRATUM = 128
SAMPLED_PER_STRATUM = 16
PAIRED_SEEDS = 8
POLICIES = ("pi0", "pi05", "groot")
CONTRACTS = ("C0", "C1", "C2", "C3", "C4", "C5")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def oracle_probabilities(scenario: str) -> np.ndarray:
    """Return [stratum, type, policy, contract] oracle probabilities."""
    type_index = np.arange(POPULATION_PER_STRATUM, dtype=float)
    task_wave = 0.045 * np.sin(2.0 * np.pi * type_index / POPULATION_PER_STRATUM)
    base = np.stack([0.18 + 0.08 * s + task_wave for s in range(STRATA)])
    policy = np.array([0.055, -0.035, 0.135], dtype=float)
    contract = np.array([0.0, -0.018, 0.022, 0.010, -0.026, 0.030])
    interaction = np.zeros((3, 6), dtype=float)
    if scenario == "stable":
        interaction = np.array(
            [
                [0.0, 0.004, -0.003, 0.002, 0.003, -0.004],
                [0.0, -0.002, 0.003, -0.001, 0.001, 0.002],
                [0.0, 0.001, -0.002, 0.003, -0.003, 0.001],
            ]
        )
    elif scenario == "reversal":
        interaction = np.array(
            [
                [0.0, 0.004, -0.003, 0.002, 0.003, -0.004],
                [0.0, -0.002, 0.115, -0.001, 0.001, 0.002],
                [0.0, 0.001, -0.002, 0.003, -0.003, 0.001],
            ]
        )
    else:
        raise ValueError(scenario)
    value = (
        base[:, :, None, None]
        + policy[None, None, :, None]
        + contract[None, None, None, :]
        + interaction[None, None, :, :]
    )
    return np.clip(value, 0.02, 0.95)


def truth_summary(probabilities: np.ndarray) -> dict[str, object]:
    rates = probabilities.mean(axis=(0, 1))
    orders = [tuple(np.argsort(rates[:, c]).tolist()) for c in range(len(CONTRACTS))]
    return {
        "rates": rates,
        "orders": orders,
        "identical_strict_order": len(set(orders)) == 1
        and all(len(set(rates[:, c])) == len(POLICIES) for c in range(len(CONTRACTS))),
    }


def sample_dataset(probabilities: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    sampled = []
    for s in range(STRATA):
        selected = rng.integers(0, POPULATION_PER_STRATUM, size=SAMPLED_PER_STRATUM)
        sampled.append(probabilities[s, selected])
    task_prob = np.concatenate(sampled, axis=0)
    common = rng.random((STRATA * SAMPLED_PER_STRATUM, len(POLICIES), PAIRED_SEEDS, 1))
    return (common < task_prob[:, :, None, :]).astype(float)


def estimate(data: np.ndarray) -> np.ndarray:
    return data.mean(axis=(0, 2))


def observed_identical_strict_order(rates: np.ndarray) -> bool:
    orders = [tuple(np.argsort(rates[:, c]).tolist()) for c in range(len(CONTRACTS))]
    return len(set(orders)) == 1 and all(
        len(set(rates[:, c])) == len(POLICIES) for c in range(len(CONTRACTS))
    )


def bootstrap_radius(data: np.ndarray, rng: np.random.Generator) -> float:
    task_means = data.mean(axis=2)
    point = task_means.mean(axis=0)
    boot = np.empty((BOOTSTRAP_REPEATS, len(POLICIES), len(CONTRACTS)))
    for b in range(BOOTSTRAP_REPEATS):
        blocks = []
        for s in range(STRATA):
            start = s * SAMPLED_PER_STRATUM
            idx = start + rng.integers(0, SAMPLED_PER_STRATUM, size=SAMPLED_PER_STRATUM)
            blocks.append(task_means[idx])
        boot[b] = np.concatenate(blocks, axis=0).mean(axis=0)
    max_deviation = np.max(np.abs(boot - point[None, :, :]), axis=(1, 2))
    return float(np.quantile(max_deviation, 0.95))


def main(output: Path) -> None:
    if output.exists():
        raise RuntimeError(f"write-once output exists: {output}")
    rng = np.random.default_rng(SEED)
    scenario_results: dict[str, object] = {}
    for scenario in ("stable", "reversal"):
        probabilities = oracle_probabilities(scenario)
        truth = truth_summary(probabilities)
        estimates = np.empty((MC_REPEATS, len(POLICIES), len(CONTRACTS)))
        classifications = []
        for i in range(MC_REPEATS):
            estimates[i] = estimate(sample_dataset(probabilities, rng))
            classifications.append(observed_identical_strict_order(estimates[i]))
        true_rates = np.asarray(truth["rates"])
        mean_bias = estimates.mean(axis=0) - true_rates
        expected_class = bool(truth["identical_strict_order"])
        accuracy = float(np.mean(np.asarray(classifications) == expected_class))
        scenario_results[scenario] = {
            "truth_rates": {
                POLICIES[p]: {CONTRACTS[c]: float(true_rates[p, c]) for c in range(6)}
                for p in range(3)
            },
            "truth_identical_strict_order": expected_class,
            "maximum_absolute_mean_bias": float(np.max(np.abs(mean_bias))),
            "classification_accuracy": accuracy,
        }

    stable_prob = oracle_probabilities("stable")
    stable_truth = np.asarray(truth_summary(stable_prob)["rates"])
    covered = 0
    radii = []
    for _ in range(COVERAGE_REPEATS):
        data = sample_dataset(stable_prob, rng)
        point = estimate(data)
        radius = bootstrap_radius(data, rng)
        radii.append(radius)
        covered += int(bool(np.all(np.abs(point - stable_truth) <= radius)))
    coverage = covered / COVERAGE_REPEATS

    gates = {
        "stable_maximum_absolute_mean_bias_le_0_01": scenario_results["stable"]["maximum_absolute_mean_bias"] <= 0.01,
        "reversal_maximum_absolute_mean_bias_le_0_01": scenario_results["reversal"]["maximum_absolute_mean_bias"] <= 0.01,
        "stable_classification_accuracy_ge_0_80": scenario_results["stable"]["classification_accuracy"] >= 0.80,
        "reversal_classification_accuracy_ge_0_80": scenario_results["reversal"]["classification_accuracy"] >= 0.80,
        "simultaneous_coverage_in_0_90_1_00": 0.90 <= coverage <= 1.00,
    }
    payload = {
        "schema_version": 1,
        "evidence_label": "PROSPECTIVE_SYNTHETIC_CALIBRATION",
        "seed": SEED,
        "mc_repeats": MC_REPEATS,
        "coverage_repeats": COVERAGE_REPEATS,
        "bootstrap_repeats": BOOTSTRAP_REPEATS,
        "scenario_results": scenario_results,
        "simultaneous_coverage": coverage,
        "bootstrap_radius_median": float(np.median(radii)),
        "gates": gates,
        "status": "PASS" if all(gates.values()) else "FAIL",
        "claim_boundary": "software/statistical calibration only; no robot-safety evidence",
        "script_sha256": sha256(Path(__file__)),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".partial")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output)
    print(json.dumps({"status": payload["status"], "output": str(output)}, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    main(args.output)

