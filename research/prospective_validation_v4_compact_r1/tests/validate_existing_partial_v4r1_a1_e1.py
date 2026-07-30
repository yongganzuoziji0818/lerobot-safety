#!/usr/bin/env python3
"""Independent read-only validation of the preserved A1 payload."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PARTIAL = (
    ROOT
    / "analysis_results"
    / "V4R1-A1-ANALYSIS-001.json.partial.25832"
)
FINAL = ROOT / "analysis_results" / "V4R1-A1-ANALYSIS-001.json"
AUTHORIZATION = ROOT / "governance" / "FORMAL_EXECUTION_RECEIPT_E1.json"
FORMAL_ROOT = (
    ROOT
    / "remote_receipts"
    / "l40s_20260730_v4r1_e2_formal001_terminal_success"
    / "V4R1-E2-FORMAL-ROLLOUT-001"
)
RUN_RECEIPT = FORMAL_ROOT / "formal_run_receipt.json"
EXPECTED_PARTIAL_SHA256 = (
    "7a6cc1c97baaacdc0185504ed813a2f431bd45a639e1d086789cd16973e50c5b"
)
EXPECTED_AUTHORIZATION_SHA256 = (
    "5dde7ae1409ec8e1d21e74db319451913031a0d54028ededdf53b6021b517f3c"
)
EXPECTED_RUN_RECEIPT_SHA256 = (
    "c1cdfc4000eeb31e92fc6b8a106dc58ad9b0ca53930dacac747c49af1b5a0769"
)
POLICIES = {"pi0", "pi05", "groot"}
CONTRACTS = {f"C{index}" for index in range(6)}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    require(PARTIAL.is_file(), "PARTIAL_MISSING")
    require(not FINAL.exists(), "FINAL_ALREADY_EXISTS")
    require(sha256(PARTIAL) == EXPECTED_PARTIAL_SHA256, "PARTIAL_HASH")
    require(
        sha256(AUTHORIZATION) == EXPECTED_AUTHORIZATION_SHA256,
        "AUTHORIZATION_HASH",
    )
    require(
        sha256(RUN_RECEIPT) == EXPECTED_RUN_RECEIPT_SHA256,
        "RUN_RECEIPT_HASH",
    )
    payload = json.loads(PARTIAL.read_bytes())
    authorization = json.loads(AUTHORIZATION.read_bytes())
    run_receipt = json.loads(RUN_RECEIPT.read_bytes())
    attempt = "V4R1-E2-FORMAL-ROLLOUT-001"
    require(
        authorization.get("status")
        == "AUTHORIZED_V4R1_E1_FORMAL_EXECUTION",
        "AUTHORIZATION_STATUS",
    )
    require(
        authorization.get("formal_attempt_id") == attempt,
        "AUTHORIZATION_ATTEMPT",
    )
    require(
        run_receipt.get("status") == "PASS_V4R1_COMPLETE_FORMAL_RUN",
        "RUN_STATUS",
    )
    require(run_receipt.get("attempt_id") == attempt, "RUN_ATTEMPT")
    require(payload.get("attempt_id") == attempt, "PAYLOAD_ATTEMPT")
    require(
        payload.get("status") == "PASS_V4R1_FROZEN_ANALYSIS",
        "PAYLOAD_STATUS",
    )
    require(
        payload.get("formal_scientific_trajectories") == 1200,
        "TRAJECTORY_CENSUS",
    )
    require(payload.get("episode_contract_rows") == 7200, "ROW_CENSUS")
    require(payload.get("invalid_contract_rows") == 0, "INVALID_ROWS")
    labels = payload.get("estimand_labels", [])
    intervals = payload.get("bootstrap", {}).get("intervals", [])
    cells = payload.get("partial_identification_task_cells", [])
    descriptive = payload.get("task_success_descriptive_only", [])
    require(len(labels) == 57 and len(set(labels)) == 57, "LABEL_CENSUS")
    require(
        payload.get("bootstrap", {}).get("replicates") == 10_000,
        "BOOTSTRAP_CENSUS",
    )
    require(len(intervals) == 57, "INTERVAL_CENSUS")
    require(
        [item.get("estimand") for item in intervals] == labels,
        "INTERVAL_BINDING",
    )
    require(len(cells) == 900, "TASK_CELL_CENSUS")
    require(
        {
            (
                item.get("policy"),
                item.get("task_ordinal"),
                item.get("contract"),
            )
            for item in cells
        }
        == {
            (policy, task, contract)
            for policy in POLICIES
            for task in range(50)
            for contract in CONTRACTS
        },
        "TASK_CELL_BINDING",
    )
    require(
        {item.get("policy") for item in descriptive} == POLICIES,
        "DESCRIPTIVE_POLICY_CENSUS",
    )
    require(
        all(item.get("trajectories") == 400 for item in descriptive),
        "DESCRIPTIVE_TRAJECTORY_CENSUS",
    )
    print(
        json.dumps(
            {
                "status": "PASS_V4R1_A1_E1_EXISTING_PARTIAL_VALIDATION",
                "partial_sha256": sha256(PARTIAL),
                "authorization_sha256": sha256(AUTHORIZATION),
                "run_receipt_sha256": sha256(RUN_RECEIPT),
                "attempt_id": attempt,
                "formal_scientific_trajectories": 1200,
                "episode_contract_rows": 7200,
                "invalid_contract_rows": 0,
                "estimand_labels": 57,
                "bootstrap_replicates": 10_000,
                "bootstrap_intervals": 57,
                "task_cells": 900,
                "descriptive_policies": 3,
                "recomputed": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
