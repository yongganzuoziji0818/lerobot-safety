#!/usr/bin/env python3
"""Aggregate all 150 sealed V4-Compact-R1 policy-task shards."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from production_common_v4r1 import file_sha256, write_json_once

ROOT = Path("/workspace/lerobot-safety")
V3B = ROOT / "research" / "prospective_validation_v3b"
V4R1 = ROOT / "research" / "prospective_validation_v4_compact_r1"
TASK_FILE = V3B / "benchmark" / "task_set_target50.txt"
FREEZE_MANIFEST = V4R1 / "V4R1_PRODUCTION_FREEZE_MANIFEST.sha256"
FORMAL_AUTHORIZATION = V4R1 / "governance" / "FORMAL_EXECUTION_RECEIPT.json"


def write_text_once(path: Path, text: str) -> None:
    if path.exists():
        raise RuntimeError(f"WRITE_ONCE_EXISTS:{path}")
    temporary = path.with_suffix(path.suffix + f".partial.{os.getpid()}")
    temporary.write_text(text, encoding="utf-8")
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def tasks() -> list[str]:
    values = [
        line.strip()
        for line in TASK_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    if len(values) != 50 or len(set(values)) != 50:
        raise RuntimeError("TASK_CENSUS")
    return values


def add_totals(destination: dict[str, int], source: dict[str, Any]) -> None:
    for key in destination:
        destination[key] += int(source[key])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    receipt_path = args.output / "formal_run_receipt.json"
    manifest_path = args.output / "FORMAL_RUN_MANIFEST.sha256"
    failure_path = args.output / "formal_run_seal_failure.json"
    for path in (receipt_path, manifest_path, failure_path):
        if path.exists():
            raise RuntimeError(f"TERMINAL_FORMAL_SEAL_ARTIFACT_EXISTS:{path}")
    try:
        task_list = tasks()
        shard_records = []
        total_trajectories = 0
        total_environment_actions = 0
        total_policy_calls = 0
        total_successes = 0
        diagnostics_total = {
            "declared_box_violation_total": 0,
            "robosuite_continuous_saturation_total": 0,
            "robocasa_binary_mapping_change_total": 0,
            "source_defined_endogenous_mapping_total": 0,
        }
        for policy in ("pi0", "pi05", "groot"):
            for task_ordinal, task in enumerate(task_list):
                shard = (
                    args.output
                    / "shards"
                    / policy
                    / f"{task_ordinal:02d}_{task}"
                )
                shard_receipt_path = shard / "shard_receipt.json"
                shard_manifest_path = shard / "SHARD_MANIFEST.sha256"
                receipt = json.loads(
                    shard_receipt_path.read_text(encoding="utf-8")
                )
                if (
                    receipt.get("status")
                    != "PASS_V4R1_FORMAL_POLICY_TASK_SHARD"
                    or receipt.get("attempt_id") != args.attempt_id
                    or receipt.get("policy") != policy
                    or receipt.get("task") != task
                    or receipt.get("task_ordinal") != task_ordinal
                    or receipt.get("mode") != "learned"
                    or receipt.get("episode_count") != 8
                    or receipt.get("formal_scientific_trajectories") != 8
                    or receipt.get("adapter_action_mutation") is not False
                ):
                    raise RuntimeError(
                        f"FORMAL_SHARD_RECEIPT:{policy}:{task_ordinal}:{task}"
                    )
                total_trajectories += int(
                    receipt["formal_scientific_trajectories"]
                )
                total_environment_actions += int(
                    receipt["environment_actions"]
                )
                total_policy_calls += int(receipt["learned_policy_calls"])
                total_successes += int(receipt["successes"])
                add_totals(diagnostics_total, receipt["action_diagnostics"])
                shard_records.append(
                    {
                        "policy": policy,
                        "task_ordinal": task_ordinal,
                        "task": task,
                        "shard_receipt_sha256": file_sha256(
                            shard_receipt_path
                        ),
                        "shard_manifest_sha256": file_sha256(
                            shard_manifest_path
                        ),
                        "formal_scientific_trajectories": 8,
                        "environment_actions": receipt[
                            "environment_actions"
                        ],
                        "learned_policy_calls": receipt[
                            "learned_policy_calls"
                        ],
                        "successes": receipt["successes"],
                    }
                )
        if len(shard_records) != 150 or total_trajectories != 1200:
            raise RuntimeError(
                f"FORMAL_CENSUS:{len(shard_records)}:{total_trajectories}"
            )
        authorization = json.loads(
            FORMAL_AUTHORIZATION.read_text(encoding="utf-8")
        )
        if (
            authorization.get("formal_attempt_id") != args.attempt_id
            or authorization.get("formal_execution_allowed") is not True
        ):
            raise RuntimeError("FORMAL_AUTHORIZATION_IDENTITY")
        write_json_once(
            receipt_path,
            {
                "schema_version": 1,
                "status": "PASS_V4R1_COMPLETE_FORMAL_RUN",
                "attempt_id": args.attempt_id,
                "executor": "L40S_ONLY_SINGLE_EXECUTOR",
                "policy_order": ["pi0", "pi05", "groot"],
                "task_count": 50,
                "policy_task_shard_count": 150,
                "formal_scientific_trajectories": total_trajectories,
                "environment_actions": total_environment_actions,
                "learned_policy_calls": total_policy_calls,
                "task_successes": total_successes,
                "action_diagnostics": diagnostics_total,
                "production_freeze_manifest_sha256": file_sha256(
                    FREEZE_MANIFEST
                ),
                "formal_execution_receipt_sha256": file_sha256(
                    FORMAL_AUTHORIZATION
                ),
                "shards": shard_records,
                "timestamp": datetime.now().astimezone().isoformat(),
            },
        )
        manifest_entries = [
            f"{file_sha256(FREEZE_MANIFEST)}  "
            "research/prospective_validation_v4_compact_r1/"
            "V4R1_PRODUCTION_FREEZE_MANIFEST.sha256",
            f"{file_sha256(FORMAL_AUTHORIZATION)}  "
            "research/prospective_validation_v4_compact_r1/governance/"
            "FORMAL_EXECUTION_RECEIPT.json",
            f"{file_sha256(receipt_path)}  formal_run_receipt.json",
        ]
        for record in shard_records:
            prefix = (
                f"shards/{record['policy']}/"
                f"{record['task_ordinal']:02d}_{record['task']}"
            )
            manifest_entries.append(
                f"{record['shard_receipt_sha256']}  "
                f"{prefix}/shard_receipt.json"
            )
            manifest_entries.append(
                f"{record['shard_manifest_sha256']}  "
                f"{prefix}/SHARD_MANIFEST.sha256"
            )
        write_text_once(
            manifest_path, "\n".join(manifest_entries) + "\n"
        )
        print(
            "PASS_V4R1_COMPLETE_FORMAL_RUN "
            f"shards=150 trajectories={total_trajectories}"
        )
    except BaseException as exc:
        if not failure_path.exists():
            write_json_once(
                failure_path,
                {
                    "schema_version": 1,
                    "status": "FAIL_V4R1_FORMAL_RUN_SEAL_TERMINAL",
                    "attempt_id": args.attempt_id,
                    "timestamp": datetime.now().astimezone().isoformat(),
                    "exception_type": type(exc).__name__,
                    "exception": str(exc),
                    "automatic_retry_allowed": False,
                },
            )
        raise


if __name__ == "__main__":
    main()
