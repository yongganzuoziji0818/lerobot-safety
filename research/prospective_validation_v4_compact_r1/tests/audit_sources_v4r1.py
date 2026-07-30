#!/usr/bin/env python3
"""Static fail-closed audit of the V4-R1 frozen source contract."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION = ROOT / "production"
PROTOCOL = ROOT.parent / "prospective_validation_v4_compact" / "design" / "V4_COMPACT_PROTOCOL.json"
GATE = ROOT / "design" / "R1_GATE_AMENDMENT_SPEC.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    gate = json.loads(GATE.read_text(encoding="utf-8"))
    if (
        protocol["task_count"] != 50
        or protocol["seeds_per_policy_task"] != 8
        or protocol["environment_steps_per_trajectory"] != 900
        or protocol["planned_formal_scientific_trajectories"] != 1200
        or protocol["contracts"] != ["C0", "C1", "C2", "C3", "C4", "C5"]
        or gate["formal_scientific_design_changed"] is not False
    ):
        raise RuntimeError("PROTOCOL_DRIFT")
    python_files = sorted(PRODUCTION.glob("*.py"))
    if len(python_files) != 8:
        raise RuntimeError(f"PYTHON_SOURCE_CENSUS:{len(python_files)}")
    for path in python_files:
        ast.parse(path.read_text(encoding="utf-8"))
    client = (PRODUCTION / "formal_rollout_client_v4r1.py").read_text(encoding="utf-8")
    required = [
        "PAIRED_ENVIRONMENT_SEEDS = (42, 43, 44, 45, 46, 47, 48, 49)",
        "FORMAL_HORIZON = 900",
        "while episode_environment_actions < horizon:",
        "first_success_step",
        "adapter_action_mutation",
        "validate_groot_chunk",
        "validate_openpi_chunk",
    ]
    forbidden = [
        "while episode_environment_actions < horizon and not success",
        "get_task_horizon",
        "planned_formal_scientific_trajectories\") != 7500",
    ]
    if any(token not in client for token in required) or any(
        token in client for token in forbidden
    ):
        raise RuntimeError("CLIENT_SOURCE_CONTRACT")
    if sha(PROTOCOL) != gate["inherited_scientific_protocol_sha256"]:
        raise RuntimeError("INHERITED_PROTOCOL_HASH")
    print("PASS_V4R1_STATIC_SOURCE_AUDIT")


if __name__ == "__main__":
    main()
