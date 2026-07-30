"""Frozen V5 analysis for ArmnetBench physical SO-101 rollouts."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd


PROTOCOL_ID = "CDSE-ARMNET-V5-RW-001"
DATASET_COMMIT = "a5030e049922bd89417b8aa79672c3e89e0bed6d"
SOURCE_HASHES = {
    "so101.parquet": "0c249334caef8506ee4d15b5ea4d7b52ecc6afa7662010eadeff5d88d0dfc320",
    "bimanual_so101.parquet": "e147be28c0b6a06ffe54ff3f4bbe37135f749c545cbb26516d4702da3c0fd6b0",
}
POLICIES = ("pi0", "pi0.5", "grootn1.7")
CONTRACTS = {
    "RW0_failure_only": {
        "successful": 0.0,
        "suboptimal": 0.0,
        "failure": 1.0,
    },
    "RW1_half_suboptimal": {
        "successful": 0.0,
        "suboptimal": 0.5,
        "failure": 1.0,
    },
    "RW2_non_success": {
        "successful": 0.0,
        "suboptimal": 1.0,
        "failure": 1.0,
    },
}
EXPECTED_CELL_COUNTS = {
    ("eye_drops_to_shelf", "pi0"): 29,
    ("transfer_cube", "pi0.5"): 29,
}
EXPECTED_TASKS = (
    "block_stack",
    "cable_clip",
    "cable_unclip",
    "eye_drops_to_basket",
    "eye_drops_to_shelf",
    "ring_insert",
    "tool_insert",
    "tool_removal",
    "fold_tea_towel",
    "insert_candle",
    "open_lamp_door",
    "transfer_cube",
)
BOOTSTRAP_REPLICATES = 50_000
BOOTSTRAP_SEED = 2_026_073_001
ALPHA = 0.05


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def adjusted_percentile_interval(
    samples: np.ndarray, family_size: int
) -> tuple[float, float]:
    tail = ALPHA / (2.0 * family_size)
    return (
        float(np.quantile(samples, tail)),
        float(np.quantile(samples, 1.0 - tail)),
    )


def load_episode_table(data_dir: Path) -> pd.DataFrame:
    frames = []
    for filename, expected_hash in SOURCE_HASHES.items():
        path = data_dir / filename
        if sha256(path) != expected_hash:
            raise RuntimeError(f"source hash mismatch: {filename}")
        frame = pd.read_parquet(path, columns=["id", "quality_label"])
        frame["embodiment"] = filename.removesuffix(".parquet")
        frames.append(frame)
    camera_table = pd.concat(frames, ignore_index=True)
    parts = camera_table["id"].astype(str).str.split("/")
    if not bool(parts.map(len).eq(6).all()):
        raise RuntimeError("unexpected ArmnetBench ID grammar")
    camera_table["episode_key"] = parts.map(lambda item: "/".join(item[:-1]))
    camera_table["task_id"] = parts.map(lambda item: item[1])
    camera_table["policy"] = parts.map(lambda item: item[2])

    cameras_per_episode = camera_table.groupby("episode_key").size()
    if set(cameras_per_episode.tolist()) != {3}:
        raise RuntimeError("each episode must have exactly three camera rows")
    label_counts = camera_table.groupby("episode_key")["quality_label"].nunique()
    if int(label_counts.max()) != 1:
        raise RuntimeError("camera-row label disagreement")

    episodes = camera_table.drop_duplicates("episode_key").copy()
    episodes = episodes.loc[episodes["policy"].isin(POLICIES)].copy()
    observed_labels = set(episodes["quality_label"].astype(str))
    if observed_labels != {"successful", "suboptimal", "failure"}:
        raise RuntimeError(f"unexpected label vocabulary: {observed_labels}")
    if tuple(sorted(episodes["task_id"].unique())) != tuple(sorted(EXPECTED_TASKS)):
        raise RuntimeError("task set mismatch")

    counts = episodes.groupby(["task_id", "policy"]).size()
    if len(counts) != 36:
        raise RuntimeError("task-policy coverage mismatch")
    for task in EXPECTED_TASKS:
        for policy in POLICIES:
            expected = EXPECTED_CELL_COUNTS.get((task, policy), 30)
            observed = int(counts.loc[(task, policy)])
            if observed != expected:
                raise RuntimeError(
                    f"cell count mismatch: {task}/{policy}={observed}, "
                    f"expected={expected}"
                )
    if len(episodes) != 1_078:
        raise RuntimeError("episode census mismatch")
    return episodes[
        ["episode_key", "task_id", "policy", "quality_label", "embodiment"]
    ].reset_index(drop=True)


def risk_array(labels: pd.Series, contract: str) -> np.ndarray:
    mapping = CONTRACTS[contract]
    return labels.map(mapping).to_numpy(dtype=float)


def task_policy_risks(episodes: pd.DataFrame, contract: str) -> pd.DataFrame:
    work = episodes.copy()
    work["risk"] = risk_array(work["quality_label"], contract)
    return (
        work.groupby(["task_id", "policy"], as_index=False)["risk"]
        .mean()
        .sort_values(["task_id", "policy"])
    )


def point_estimands(episodes: pd.DataFrame) -> dict:
    output: dict[str, dict] = {}
    pairs = list(itertools.combinations(POLICIES, 2))
    for contract in CONTRACTS:
        cell = task_policy_risks(episodes, contract)
        pivot = cell.pivot(index="task_id", columns="policy", values="risk")
        macro = {p: float(pivot[p].mean()) for p in POLICIES}
        micro = {
            p: float(
                risk_array(
                    episodes.loc[episodes["policy"].eq(p), "quality_label"],
                    contract,
                ).mean()
            )
            for p in POLICIES
        }
        contrasts = {
            f"{a}_minus_{b}": float(macro[a] - macro[b]) for a, b in pairs
        }
        values = np.asarray([macro[p] for p in POLICIES])
        tied = len(set(np.round(values, 15))) != len(POLICIES)
        order = [p for p, _ in sorted(macro.items(), key=lambda kv: (kv[1], kv[0]))]
        output[contract] = {
            "macro_task_equal_risk": macro,
            "micro_episode_risk": micro,
            "pairwise_macro_differences": contrasts,
            "point_order_low_to_high_risk": order,
            "risk_tie": bool(tied),
        }
    orders = [tuple(output[c]["point_order_low_to_high_risk"]) for c in CONTRACTS]
    output["ranking_summary"] = {
        "identical_strict_order_across_contracts": bool(
            len(set(orders)) == 1
            and not any(output[c]["risk_tie"] for c in CONTRACTS)
        ),
        "orders": {c: list(order) for c, order in zip(CONTRACTS, orders)},
    }
    return output


def bootstrap(episodes: pd.DataFrame) -> dict:
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    tasks = np.asarray(EXPECTED_TASKS)
    pairs = list(itertools.combinations(POLICIES, 2))
    labels_by_cell = {
        (task, policy): episodes.loc[
            episodes["task_id"].eq(task) & episodes["policy"].eq(policy),
            "quality_label",
        ].to_numpy()
        for task in EXPECTED_TASKS
        for policy in POLICIES
    }
    maps = {
        contract: {
            label: score for label, score in CONTRACTS[contract].items()
        }
        for contract in CONTRACTS
    }
    contract_names = list(CONTRACTS)
    boot_risk = np.empty(
        (BOOTSTRAP_REPLICATES, len(contract_names), len(POLICIES)), dtype=float
    )
    for replicate in range(BOOTSTRAP_REPLICATES):
        sampled_tasks = rng.choice(tasks, size=len(tasks), replace=True)
        task_means = np.empty(
            (len(sampled_tasks), len(contract_names), len(POLICIES)), dtype=float
        )
        for task_index, task in enumerate(sampled_tasks):
            for policy_index, policy in enumerate(POLICIES):
                labels = labels_by_cell[(str(task), policy)]
                sampled = rng.choice(labels, size=len(labels), replace=True)
                for contract_index, contract in enumerate(contract_names):
                    mapping = maps[contract]
                    task_means[task_index, contract_index, policy_index] = (
                        np.mean([mapping[str(label)] for label in sampled])
                    )
        boot_risk[replicate] = task_means.mean(axis=0)

    pair_family: dict[str, dict] = {}
    for contract_index, contract in enumerate(contract_names):
        for a, b in pairs:
            a_index = POLICIES.index(a)
            b_index = POLICIES.index(b)
            samples = (
                boot_risk[:, contract_index, a_index]
                - boot_risk[:, contract_index, b_index]
            )
            low, high = adjusted_percentile_interval(samples, family_size=9)
            pair_family[f"{contract}:{a}_minus_{b}"] = {
                "simultaneous_95_low": low,
                "simultaneous_95_high": high,
                "excludes_zero": bool(low > 0.0 or high < 0.0),
            }

    width_family: dict[str, dict] = {}
    low_index = contract_names.index("RW0_failure_only")
    high_index = contract_names.index("RW2_non_success")
    for policy_index, policy in enumerate(POLICIES):
        samples = (
            boot_risk[:, high_index, policy_index]
            - boot_risk[:, low_index, policy_index]
        )
        low, high = adjusted_percentile_interval(samples, family_size=3)
        width_family[policy] = {
            "point_interpretation": "task-macro suboptimal rate",
            "simultaneous_95_low": low,
            "simultaneous_95_high": high,
        }
    return {
        "replicates": BOOTSTRAP_REPLICATES,
        "seed": BOOTSTRAP_SEED,
        "method": "two-stage paired-task bootstrap",
        "pairwise_contrast_family_size": 9,
        "pairwise_contrasts": pair_family,
        "contract_width_family_size": 3,
        "contract_widths": width_family,
    }


def partial_identification(points: dict) -> dict:
    failure = points["RW0_failure_only"]["macro_task_equal_risk"]
    non_success = points["RW2_non_success"]["macro_task_equal_risk"]
    pairs = list(itertools.combinations(POLICIES, 2))
    return {
        "policy_risk_lambda_0_to_1": {
            policy: [float(failure[policy]), float(non_success[policy])]
            for policy in POLICIES
        },
        "pair_difference_common_lambda": {
            f"{a}_minus_{b}": [
                float(min(failure[a] - failure[b], non_success[a] - non_success[b])),
                float(max(failure[a] - failure[b], non_success[a] - non_success[b])),
            ]
            for a, b in pairs
        },
        "pair_difference_policy_specific_lambda": {
            f"{a}_minus_{b}": [
                float(failure[a] - non_success[b]),
                float(non_success[a] - failure[b]),
            ]
            for a, b in pairs
        },
    }


def embodiment_descriptives(episodes: pd.DataFrame) -> dict:
    result = {}
    for embodiment, subset in episodes.groupby("embodiment"):
        result[str(embodiment)] = point_estimands(subset)
    return result


def leave_one_task_out(episodes: pd.DataFrame) -> dict:
    result = {}
    for omitted in EXPECTED_TASKS:
        subset = episodes.loc[~episodes["task_id"].eq(omitted)]
        result[omitted] = point_estimands(subset)["ranking_summary"]
    return result


def write_once_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    episodes = load_episode_table(args.data_dir)
    points = point_estimands(episodes)
    payload = {
        "schema_version": 1,
        "protocol_id": PROTOCOL_ID,
        "dataset_revision_commit": DATASET_COMMIT,
        "source_hashes": SOURCE_HASHES,
        "sample": {
            "episodes": int(len(episodes)),
            "tasks": int(episodes["task_id"].nunique()),
            "policies": list(POLICIES),
            "task_policy_cells": int(
                episodes[["task_id", "policy"]].drop_duplicates().shape[0]
            ),
            "label_counts": {
                str(k): int(v)
                for k, v in episodes["quality_label"].value_counts().items()
            },
        },
        "contracts": CONTRACTS,
        "primary_point_estimands": points,
        "bootstrap": bootstrap(episodes),
        "partial_identification": partial_identification(points),
        "embodiment_descriptives": embodiment_descriptives(episodes),
        "leave_one_task_out": leave_one_task_out(episodes),
        "cross_benchmark_pooling": False,
        "claim_boundary": (
            "Released physical SO-101 benchmark rollouts; no deployment-safety "
            "or physical contact-force validation claim."
        ),
    }
    write_once_json(args.output, payload)
    print(f"PASS_V5_FORMAL_ANALYSIS {args.output}")


if __name__ == "__main__":
    main()

