#!/usr/bin/env python3
"""Read-only audit of one sealed V4R1-E1 OpenPI pre-step gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from production_common_v4r1 import file_sha256


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", choices=("pi0", "pi05"), required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if list(args.output.rglob("*.partial*")):
        raise RuntimeError("PARTIAL_ENGINEERING_GATE_ARTIFACT")
    if list(args.output.rglob("*failure*.json")):
        raise RuntimeError("FAILURE_ENGINEERING_GATE_ARTIFACT")
    manifest = args.output / "ENGINEERING_GATE_MANIFEST.sha256"
    entries = 0
    for line in manifest.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        target = args.output / relative
        if not target.is_file() or file_sha256(target) != expected:
            raise RuntimeError(f"ENGINEERING_GATE_MANIFEST:{relative}")
        entries += 1
    receipt = json.loads(
        (args.output / "engineering_gate_receipt.json").read_text(
            encoding="utf-8"
        )
    )
    if (
        receipt.get("status") != "PASS_V4R1_E1_OPENPI_PRESTEP_GATE"
        or receipt.get("attempt_id") != args.attempt_id
        or receipt.get("policy") != args.policy
        or receipt.get("environment_step_called") is not False
        or receipt.get("environment_actions") != 0
        or receipt.get("formal_scientific_trajectories") != 0
        or receipt.get("adapter_action_mutation") is not False
        or entries < 10
    ):
        raise RuntimeError("ENGINEERING_GATE_RECEIPT")
    print(
        "PASS_V4R1_E1_OPENPI_PRESTEP_GATE_AUDIT "
        f"policy={args.policy} entries={entries}"
    )


if __name__ == "__main__":
    main()
