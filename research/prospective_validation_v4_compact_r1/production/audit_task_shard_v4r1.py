#!/usr/bin/env python3
"""Read-only integrity audit for a sealed V4-Compact-R1 task shard."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from production_common_v4r1 import file_sha256


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", choices=("pi0", "pi05", "groot"), required=True)
    parser.add_argument("--mode", choices=("zero", "learned"), required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--task-ordinal", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    partials = list(args.output.rglob("*.partial*"))
    failures = list(args.output.rglob("*failure*.json"))
    if partials or failures:
        raise RuntimeError(
            f"TERMINAL_OR_PARTIAL_ARTIFACTS:"
            f"partials={len(partials)}:failures={len(failures)}"
        )
    for runtime_file in (
        args.output / "client.exit_code.txt",
        args.output / "server.exit_code.txt",
        args.output / "seal.exit_code.txt",
        args.output / "controller.exit_code.txt",
    ):
        if runtime_file.read_text(encoding="utf-8").strip() != "0":
            raise RuntimeError(f"NONZERO_EXIT:{runtime_file.name}")

    manifest_path = args.output / "SHARD_MANIFEST.sha256"
    entries = 0
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        expected, relative = line.split("  ", 1)
        target = args.output / relative
        if not target.is_file() or file_sha256(target) != expected:
            raise RuntimeError(f"SHARD_MANIFEST_ENTRY:{relative}")
        entries += 1
    if entries < 1:
        raise RuntimeError("EMPTY_SHARD_MANIFEST")

    receipt = json.loads(
        (args.output / "shard_receipt.json").read_text(encoding="utf-8")
    )
    expected_status = (
        "PASS_V4R1_FORMAL_POLICY_TASK_SHARD"
        if args.mode == "learned"
        else "PASS_V4R1_NOPOLICY_RUNNER_GATE_SHARD"
    )
    expected_episodes = 8 if args.mode == "learned" else 1
    expected_formal = 8 if args.mode == "learned" else 0
    identity = {
        "attempt_id": args.attempt_id,
        "task": args.task,
        "task_ordinal": args.task_ordinal,
        "policy": args.policy,
        "mode": args.mode,
    }
    if (
        receipt.get("status") != expected_status
        or receipt.get("episode_count") != expected_episodes
        or receipt.get("formal_scientific_trajectories") != expected_formal
        or any(receipt.get(key) != value for key, value in identity.items())
    ):
        raise RuntimeError("SHARD_RECEIPT")
    print(
        f"PASS_V4R1_TASK_SHARD_AUDIT entries={entries} "
        f"episodes={expected_episodes} formal={expected_formal}"
    )


if __name__ == "__main__":
    main()
