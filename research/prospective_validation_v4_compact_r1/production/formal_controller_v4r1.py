#!/usr/bin/env python3
"""Single-executor exact-once controller for V4-Compact-R1."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path("/workspace/lerobot-safety")
V3B = ROOT / "research" / "prospective_validation_v3b"
V4R1 = ROOT / "research" / "prospective_validation_v4_compact_r1"
PRODUCTION = V4R1 / "production"
TASK_FILE = V3B / "benchmark" / "task_set_target50.txt"
LOCK = ROOT / "control" / "cdse_formal_single_executor.lock"
FREEZE_MANIFEST = V4R1 / "V4R1_PRODUCTION_FREEZE_MANIFEST.sha256"
FORMAL_RECEIPT = V4R1 / "governance" / "FORMAL_EXECUTION_RECEIPT.json"
PYTHON = ROOT / ".venv-robocasa-v2-py311" / "bin" / "python"

sys.path.insert(0, str(PRODUCTION))
from production_common_v4r1 import file_sha256, write_json_once  # noqa: E402


def tasks() -> list[str]:
    values = [
        line.strip()
        for line in TASK_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    if len(values) != 50 or len(set(values)) != 50:
        raise RuntimeError("TASK_CENSUS")
    return values


def validate_authorization(attempt_id: str) -> dict[str, Any]:
    if not FREEZE_MANIFEST.is_file() or not FORMAL_RECEIPT.is_file():
        raise RuntimeError("FORMAL_FREEZE_OR_RECEIPT_MISSING")
    receipt = json.loads(FORMAL_RECEIPT.read_text(encoding="utf-8"))
    if (
        receipt.get("status") != "AUTHORIZED_V4R1_FORMAL_EXECUTION"
        or receipt.get("formal_execution_allowed") is not True
        or receipt.get("formal_attempt_id") != attempt_id
        or receipt.get("production_freeze_manifest_sha256")
        != file_sha256(FREEZE_MANIFEST)
        or receipt.get("planned_formal_scientific_trajectories") != 1200
        or receipt.get("seeds_per_policy_task") != 8
        or receipt.get("environment_steps_per_trajectory") != 900
        or receipt.get("executor") != "L40S_ONLY_SINGLE_EXECUTOR"
    ):
        raise RuntimeError("INVALID_FORMAL_EXECUTION_RECEIPT")
    return receipt


def atomic_state(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def run_checked(command: list[str], env: dict[str, str]) -> None:
    completed = subprocess.run(command, env=env, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            f"SUBPROCESS_EXIT:{completed.returncode}:{command[1]}"
        )


def audit_shard(
    *,
    attempt_id: str,
    policy: str,
    task: str,
    task_ordinal: int,
    shard: Path,
    environment: dict[str, str],
) -> None:
    run_checked(
        [
            str(PYTHON),
            str(PRODUCTION / "audit_task_shard_v4r1.py"),
            "--policy",
            policy,
            "--mode",
            "learned",
            "--attempt-id",
            attempt_id,
            "--task",
            task,
            "--task-ordinal",
            str(task_ordinal),
            "--output",
            str(shard),
        ],
        environment,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt-id", required=True)
    args = parser.parse_args()

    validate_authorization(args.attempt_id)
    output = (
        ROOT
        / "artifacts"
        / "prospective_validation_v4_compact_r1"
        / "formal"
        / args.attempt_id
    )
    if not output.exists():
        output.mkdir(parents=True, exist_ok=False)
    state_path = output / "runtime_state.json"
    failure_path = output / "controller_failure.json"
    final_receipt = output / "formal_run_receipt.json"
    final_manifest = output / "FORMAL_RUN_MANIFEST.sha256"
    if failure_path.exists():
        raise RuntimeError("TERMINAL_CONTROLLER_FAILURE_EXISTS")
    if final_receipt.exists() or final_manifest.exists():
        if not final_receipt.is_file() or not final_manifest.is_file():
            raise RuntimeError("INCOMPLETE_FINAL_FORMAL_SEAL")
        environment = dict(os.environ)
        run_checked(
            [
                str(PYTHON),
                str(PRODUCTION / "audit_formal_run_v4r1.py"),
                "--attempt-id",
                args.attempt_id,
                "--output",
                str(output),
            ],
            environment,
        )
        print("PASS_V4R1_COMPLETE_FORMAL_RUN_ALREADY_SEALED")
        return

    LOCK.parent.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    environment["V4R1_PARENT_LOCK_HELD"] = "1"
    task_list = tasks()
    completed_shards = 0
    current_policy = None
    current_task = None
    current_task_ordinal = None
    with LOCK.open("a+b") as lock_handle:
        try:
            fcntl.flock(
                lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB
            )
        except BlockingIOError as exc:
            raise RuntimeError("SINGLE_EXECUTOR_LOCK_REFUSED") from exc
        try:
            for policy_index, policy in enumerate(("pi0", "pi05", "groot")):
                current_policy = policy
                for task_ordinal, task in enumerate(task_list):
                    current_task = task
                    current_task_ordinal = task_ordinal
                    shard = (
                        output
                        / "shards"
                        / policy
                        / f"{task_ordinal:02d}_{task}"
                    )
                    atomic_state(
                        state_path,
                        {
                            "schema_version": 1,
                            "status": "AUDITING_OR_STARTING_POLICY_TASK_SHARD",
                            "attempt_id": args.attempt_id,
                            "policy": policy,
                            "policy_index": policy_index,
                            "task": task,
                            "task_ordinal": task_ordinal,
                            "completed_policy_task_shards": completed_shards,
                            "completed_formal_scientific_trajectories": (
                                completed_shards * 8
                            ),
                            "executor": "L40S_ONLY_SINGLE_EXECUTOR",
                            "timestamp": datetime.now().astimezone().isoformat(),
                        },
                    )
                    if shard.exists():
                        audit_shard(
                            attempt_id=args.attempt_id,
                            policy=policy,
                            task=task,
                            task_ordinal=task_ordinal,
                            shard=shard,
                            environment=environment,
                        )
                    else:
                        run_checked(
                            [
                                "bash",
                                str(
                                    PRODUCTION
                                    / "run_task_shard_v4r1.sh"
                                ),
                                "learned",
                                policy,
                                str(task_ordinal),
                                args.attempt_id,
                                str(48201 + policy_index),
                                str(shard),
                            ],
                            environment,
                        )
                        audit_shard(
                            attempt_id=args.attempt_id,
                            policy=policy,
                            task=task,
                            task_ordinal=task_ordinal,
                            shard=shard,
                            environment=environment,
                        )
                    completed_shards += 1
                    atomic_state(
                        state_path,
                        {
                            "schema_version": 1,
                            "status": "POLICY_TASK_SHARD_SEALED",
                            "attempt_id": args.attempt_id,
                            "policy": policy,
                            "task": task,
                            "task_ordinal": task_ordinal,
                            "completed_policy_task_shards": completed_shards,
                            "completed_formal_scientific_trajectories": (
                                completed_shards * 8
                            ),
                            "executor": "L40S_ONLY_SINGLE_EXECUTOR",
                            "timestamp": datetime.now().astimezone().isoformat(),
                        },
                    )
            run_checked(
                [
                    str(PYTHON),
                    str(PRODUCTION / "seal_formal_run_v4r1.py"),
                    "--attempt-id",
                    args.attempt_id,
                    "--output",
                    str(output),
                ],
                environment,
            )
            run_checked(
                [
                    str(PYTHON),
                    str(PRODUCTION / "audit_formal_run_v4r1.py"),
                    "--attempt-id",
                    args.attempt_id,
                    "--output",
                    str(output),
                ],
                environment,
            )
            atomic_state(
                state_path,
                {
                    "schema_version": 1,
                    "status": "PASS_V4R1_COMPLETE_FORMAL_RUN",
                    "attempt_id": args.attempt_id,
                    "completed_policy_task_shards": 150,
                    "completed_formal_scientific_trajectories": 1200,
                    "executor": "L40S_ONLY_SINGLE_EXECUTOR",
                    "timestamp": datetime.now().astimezone().isoformat(),
                },
            )
        except BaseException as exc:
            if not failure_path.exists():
                write_json_once(
                    failure_path,
                    {
                        "schema_version": 1,
                        "status": "FAIL_V4R1_FORMAL_CONTROLLER_TERMINAL",
                        "attempt_id": args.attempt_id,
                        "policy": current_policy,
                        "task": current_task,
                        "task_ordinal": current_task_ordinal,
                        "completed_policy_task_shards": completed_shards,
                        "completed_formal_scientific_trajectories": (
                            completed_shards * 8
                        ),
                        "timestamp": datetime.now().astimezone().isoformat(),
                        "exception_type": type(exc).__name__,
                        "exception": str(exc),
                        "automatic_retry_allowed": False,
                    },
                )
            atomic_state(
                state_path,
                {
                    "schema_version": 1,
                    "status": "FAIL_V4R1_FORMAL_CONTROLLER_TERMINAL",
                    "attempt_id": args.attempt_id,
                    "policy": current_policy,
                    "task": current_task,
                    "task_ordinal": current_task_ordinal,
                    "completed_policy_task_shards": completed_shards,
                    "completed_formal_scientific_trajectories": (
                        completed_shards * 8
                    ),
                    "executor": "L40S_ONLY_SINGLE_EXECUTOR",
                    "human_intervention_required": True,
                    "timestamp": datetime.now().astimezone().isoformat(),
                },
            )
            raise


if __name__ == "__main__":
    main()
