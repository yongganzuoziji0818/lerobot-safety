#!/usr/bin/env python3
"""Read-only top-level integrity audit for a sealed V3-B2 formal run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from production_common_v4r1 import file_sha256

ROOT = Path("/workspace/lerobot-safety")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if list(args.output.rglob("*.partial*")):
        raise RuntimeError("PARTIAL_FORMAL_ARTIFACT")
    if list(args.output.rglob("*failure*.json")):
        raise RuntimeError("TERMINAL_FORMAL_FAILURE_ARTIFACT")
    manifest_path = args.output / "FORMAL_RUN_MANIFEST.sha256"
    entries = 0
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        expected, relative = line.split("  ", 1)
        if relative.startswith("research/"):
            target = ROOT / relative
        else:
            target = args.output / relative
        if not target.is_file() or file_sha256(target) != expected:
            raise RuntimeError(f"FORMAL_RUN_MANIFEST_ENTRY:{relative}")
        entries += 1
    receipt = json.loads(
        (args.output / "formal_run_receipt.json").read_text(encoding="utf-8")
    )
    if (
        entries != 303
        or receipt.get("status") != "PASS_V4R1_COMPLETE_FORMAL_RUN"
        or receipt.get("attempt_id") != args.attempt_id
        or receipt.get("policy_task_shard_count") != 150
        or receipt.get("formal_scientific_trajectories") != 1200
        or len(receipt.get("shards", [])) != 150
        or receipt.get("executor") != "L40S_ONLY_SINGLE_EXECUTOR"
    ):
        raise RuntimeError("FORMAL_RUN_RECEIPT_OR_CENSUS")
    print(
        "PASS_V4R1_COMPLETE_FORMAL_RUN_AUDIT "
        "manifest_entries=303 shards=150 trajectories=1200"
    )


if __name__ == "__main__":
    main()
