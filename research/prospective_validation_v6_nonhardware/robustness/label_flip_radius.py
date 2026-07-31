#!/usr/bin/env python3
"""Post-hoc exact adversarial label-flip radii for sealed V5 labels."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


SOURCE_HASHES = {
    "so101.parquet": "0c249334caef8506ee4d15b5ea4d7b52ecc6afa7662010eadeff5d88d0dfc320",
    "bimanual_so101.parquet": "e147be28c0b6a06ffe54ff3f4bbe37135f749c545cbb26516d4702da3c0fd6b0",
}
POLICIES = ("pi0", "pi0.5", "grootn1.7")
CONTRACTS = {
    "RW0_failure_only": {"successful": 0.0, "suboptimal": 0.0, "failure": 1.0},
    "RW1_half_suboptimal": {"successful": 0.0, "suboptimal": 0.5, "failure": 1.0},
    "RW2_non_success": {"successful": 0.0, "suboptimal": 1.0, "failure": 1.0},
}
PAIRS = (("pi0", "pi0.5"), ("pi0", "grootn1.7"), ("pi0.5", "grootn1.7"))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_episodes(data_dir: Path) -> pd.DataFrame:
    frames = []
    for filename, expected in SOURCE_HASHES.items():
        path = data_dir / filename
        if sha256(path) != expected:
            raise RuntimeError(f"source hash mismatch: {filename}")
        frame = pd.read_parquet(path, columns=["id", "quality_label"])
        parts = frame["id"].astype(str).str.split("/")
        frame["episode_key"] = parts.map(lambda x: "/".join(x[:-1]))
        frame["task_id"] = parts.map(lambda x: x[1])
        frame["policy"] = parts.map(lambda x: x[2])
        frames.append(frame)
    camera = pd.concat(frames, ignore_index=True)
    if set(camera.groupby("episode_key").size()) != {3}:
        raise RuntimeError("camera census mismatch")
    if int(camera.groupby("episode_key")["quality_label"].nunique().max()) != 1:
        raise RuntimeError("camera label disagreement")
    episodes = camera.drop_duplicates("episode_key")
    episodes = episodes.loc[episodes["policy"].isin(POLICIES)].copy()
    if len(episodes) != 1078 or episodes["task_id"].nunique() != 12:
        raise RuntimeError("V5 episode census mismatch")
    return episodes


def task_macro_risk(episodes: pd.DataFrame, policy: str, weights: dict[str, float]) -> float:
    subset = episodes.loc[episodes["policy"] == policy].copy()
    subset["risk"] = subset["quality_label"].map(weights)
    return float(subset.groupby("task_id")["risk"].mean().mean())


def scalar_candidates(
    episodes: pd.DataFrame,
    a: str,
    b: str,
    weights: dict[str, float],
    direction: int,
) -> list[float]:
    task_count = episodes["task_id"].nunique()
    cell_sizes = episodes.groupby(["task_id", "policy"]).size().to_dict()
    deltas = []
    for row in episodes.loc[episodes["policy"].isin((a, b))].itertuples():
        sign = 1.0 if row.policy == a else -1.0
        scale = sign / (task_count * cell_sizes[(row.task_id, row.policy)])
        current = weights[row.quality_label]
        for target, target_weight in weights.items():
            if target == row.quality_label:
                continue
            delta = scale * (target_weight - current)
            if direction * delta < 0:
                deltas.append(delta)
    return sorted(deltas, reverse=direction < 0)


def crossing_counts(margin: float, deltas: list[float]) -> tuple[int, int]:
    if margin == 0:
        return 0, 1
    total = margin
    tie = None
    strict = None
    for k, delta in enumerate(deltas, start=1):
        total += delta
        if tie is None and margin * total <= 0:
            tie = k
        if margin * total < 0:
            strict = k
            break
    if tie is None or strict is None:
        raise RuntimeError("insufficient adversarial candidates")
    return tie, strict


def joint_extreme_candidates(episodes: pd.DataFrame, a: str, b: str, direction: int) -> list[float]:
    task_count = episodes["task_id"].nunique()
    cell_sizes = episodes.groupby(["task_id", "policy"]).size().to_dict()
    effects = []
    for row in episodes.loc[episodes["policy"].isin((a, b))].itertuples():
        sign = 1.0 if row.policy == a else -1.0
        scale = sign / (task_count * cell_sizes[(row.task_id, row.policy)])
        if direction > 0:
            eligible = (row.policy == a and row.quality_label == "failure") or (
                row.policy == b and row.quality_label == "successful"
            )
            delta = -abs(scale)
        else:
            eligible = (row.policy == a and row.quality_label == "successful") or (
                row.policy == b and row.quality_label == "failure"
            )
            delta = abs(scale)
        if eligible:
            effects.append(delta)
    return sorted(effects, reverse=direction < 0)


def joint_crossing(margins: list[float], deltas: list[float]) -> tuple[int, int]:
    if not (all(x > 0 for x in margins) or all(x < 0 for x in margins)):
        raise RuntimeError("pair direction is not common across contracts")
    direction = 1 if margins[0] > 0 else -1
    totals = list(margins)
    tie = None
    strict = None
    for k, delta in enumerate(deltas, start=1):
        totals = [x + delta for x in totals]
        if tie is None and all(direction * x <= 0 for x in totals):
            tie = k
        if all(direction * x < 0 for x in totals):
            strict = k
            break
    if tie is None or strict is None:
        raise RuntimeError("insufficient joint extreme-flip candidates")
    return tie, strict


def main(data_dir: Path, output: Path) -> None:
    if output.exists():
        raise RuntimeError(f"write-once output exists: {output}")
    episodes = load_episodes(data_dir)
    results = {}
    for a, b in PAIRS:
        by_contract = {}
        margins = []
        for contract, weights in CONTRACTS.items():
            margin = task_macro_risk(episodes, a, weights) - task_macro_risk(episodes, b, weights)
            margins.append(margin)
            direction = 1 if margin > 0 else -1
            tie, strict = crossing_counts(
                margin, scalar_candidates(episodes, a, b, weights, direction)
            )
            by_contract[contract] = {
                "observed_margin_a_minus_b": margin,
                "minimum_flips_to_tie_or_reverse": tie,
                "minimum_flips_to_strict_reverse": strict,
                "strict_reverse_fraction_all_episodes": strict / len(episodes),
            }
        common_direction = 1 if margins[0] > 0 else -1
        joint_tie, joint_strict = joint_crossing(
            margins, joint_extreme_candidates(episodes, a, b, common_direction)
        )
        results[f"{a}_minus_{b}"] = {
            "by_contract": by_contract,
            "all_contracts_simultaneous": {
                "minimum_extreme_flips_to_tie_or_reverse": joint_tie,
                "minimum_extreme_flips_to_strict_reverse": joint_strict,
                "strict_reverse_fraction_all_episodes": joint_strict / len(episodes),
            },
        }
    payload = {
        "schema_version": 1,
        "evidence_label": "POSTHOC_LABEL_ROBUSTNESS",
        "source_hashes": SOURCE_HASHES,
        "episodes": len(episodes),
        "tasks": int(episodes["task_id"].nunique()),
        "policies": list(POLICIES),
        "contracts": CONTRACTS,
        "pairwise_results": results,
        "claim_boundary": "adversarial sensitivity threshold, not actual label-error prevalence or inter-rater reliability",
        "script_sha256": sha256(Path(__file__)),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".partial")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output)
    print(json.dumps({"status": "PASS", "output": str(output)}, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    main(args.data_dir, args.output)

