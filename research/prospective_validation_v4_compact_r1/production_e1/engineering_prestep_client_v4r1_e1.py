#!/usr/bin/env python3
"""Capture one learned OpenPI action and stop before any environment step."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import sys
from datetime import datetime
from pathlib import Path

import gymnasium as gym
import numpy as np
import robocasa  # noqa: F401

ROOT = Path("/workspace/lerobot-safety")
V3B = ROOT / "research" / "prospective_validation_v3b"
V3B1_REMOTE = ROOT / "research" / "prospective_validation_v3b1" / "remote"
V4R1 = ROOT / "research" / "prospective_validation_v4_compact_r1"
PRODUCTION = V4R1 / "production_e1"
sys.path.insert(0, str(V3B1_REMOTE))
sys.path.insert(0, str(PRODUCTION))

from ipc_wire_v3b1 import receive_message, send_message  # noqa: E402
from production_common_v4r1 import (  # noqa: E402
    KEYS,
    RawActionLedger,
    file_sha256,
    logical_array_sha256,
    openpi_action_diagnostics,
    openpi_step_actions,
    raw_observation,
    validate_openpi_chunk,
    write_json_once,
)

TASK_FILE = V3B / "benchmark" / "task_set_target50.txt"
MASTER_SEED = 42


def task_list() -> list[str]:
    tasks = [
        line.strip()
        for line in TASK_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    if len(tasks) != 50 or len(set(tasks)) != 50:
        raise RuntimeError("TASK_CENSUS")
    return tasks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", choices=("pi0", "pi05"), required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--task-ordinal", type=int, required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    tasks = task_list()
    if args.task_ordinal < 0 or args.task_ordinal >= len(tasks):
        raise RuntimeError("TASK_ORDINAL")
    task = tasks[args.task_ordinal]
    token_hex = os.environ.get("V4R1_IPC_TOKEN", "")
    if len(token_hex) != 64:
        raise RuntimeError("V4R1_IPC_TOKEN_REQUIRED")
    token = bytes.fromhex(token_hex)
    receipt_path = args.output / "engineering_client_receipt.json"
    failure_path = args.output / "engineering_client_failure.json"
    ledger_path = args.output / "raw_actions.ledger"
    for path in (receipt_path, failure_path, ledger_path):
        if path.exists():
            raise RuntimeError(f"WRITE_ONCE_EXISTS:{path}")

    env = None
    client = None
    ledger = None
    try:
        env = gym.make(
            f"robocasa/{task}",
            split="target",
            seed=MASTER_SEED,
        )
        observation, reset_info = env.reset()
        observation_arrays = raw_observation(observation)
        observation_sha = logical_array_sha256(observation_arrays)
        client = socket.create_connection(("127.0.0.1", args.port), timeout=60)
        client.settimeout(600)
        send_message(
            client,
            token,
            {
                "op": "infer",
                "attempt_id": args.attempt_id,
                "task": task,
                "task_ordinal": args.task_ordinal,
                "policy": args.policy,
                "mode": "engineering",
                "episode_index": 0,
                "call_index": 0,
                "observation_logical_sha256": observation_sha,
            },
            observation_arrays,
        )
        response, raw_actions = receive_message(client, token)
        if (
            response.get("op") != "raw_actions"
            or response.get("attempt_id") != args.attempt_id
            or response.get("task") != task
            or response.get("task_ordinal") != args.task_ordinal
            or response.get("policy") != args.policy
            or response.get("mode") != "engineering"
            or response.get("call_index") != 0
            or response.get("observation_logical_sha256") != observation_sha
            or response.get("action_logical_sha256")
            != logical_array_sha256(raw_actions)
            or set(raw_actions) != {"actions"}
        ):
            raise RuntimeError("IPC_RESPONSE_IDENTITY_OR_HASH")

        native = validate_openpi_chunk(raw_actions["actions"])
        frozen_copy = native.copy()
        diagnostics = openpi_action_diagnostics(native, env.action_space)
        step_actions = openpi_step_actions(native, env.action_space)
        reconstructed = np.stack(
            [
                np.concatenate([np.asarray(step[key]) for key in KEYS])
                for step in step_actions
            ],
            axis=0,
        )
        if not np.array_equal(native[:5], reconstructed):
            raise RuntimeError("OPENPI_STEP_RECONSTRUCTION_MUTATION")
        if not np.array_equal(native, frozen_copy):
            raise RuntimeError("OPENPI_DIAGNOSTIC_MUTATION")

        ledger = RawActionLedger(ledger_path)
        action_sha = ledger.append(
            call_index=0,
            observation_sha256=observation_sha,
            actions=raw_actions,
            diagnostics=diagnostics,
        )
        ledger.seal()
        if action_sha != response["action_logical_sha256"]:
            raise RuntimeError("LEDGER_ACTION_SHA256")

        digest = hashlib.sha256()
        digest.update((0).to_bytes(8, "big"))
        digest.update(bytes.fromhex(action_sha))
        send_message(
            client,
            token,
            {
                "op": "shutdown",
                "attempt_id": args.attempt_id,
                "task": task,
                "task_ordinal": args.task_ordinal,
                "policy": args.policy,
                "mode": "engineering",
                "call_count": 1,
                "action_sequence_sha256": digest.hexdigest(),
            },
        )
        acknowledgement, acknowledgement_arrays = receive_message(client, token)
        if (
            acknowledgement.get("op") != "shutdown_ack"
            or acknowledgement.get("attempt_id") != args.attempt_id
            or acknowledgement.get("task") != task
            or acknowledgement.get("task_ordinal") != args.task_ordinal
            or acknowledgement.get("policy") != args.policy
            or acknowledgement.get("mode") != "engineering"
            or acknowledgement.get("call_count") != 1
            or acknowledgement.get("action_sequence_sha256")
            != digest.hexdigest()
            or acknowledgement_arrays
        ):
            raise RuntimeError("IPC_SHUTDOWN_ACK")

        write_json_once(
            receipt_path,
            {
                "schema_version": 1,
                "status": "PASS_V4R1_E1_OPENPI_PRESTEP_CLIENT",
                "attempt_id": args.attempt_id,
                "policy": args.policy,
                "task": task,
                "task_ordinal": args.task_ordinal,
                "environment_seed": MASTER_SEED,
                "observation_logical_sha256": observation_sha,
                "raw_action_logical_sha256": action_sha,
                "raw_action_ledger_sha256": file_sha256(ledger_path),
                "raw_action_ledger_frames": 1,
                "action_diagnostics": diagnostics,
                "step_reconstruction_exact": True,
                "adapter_action_mutation": False,
                "environment_step_called": False,
                "environment_actions": 0,
                "formal_scientific_trajectories": 0,
                "reset_info_keys": sorted(
                    str(key) for key in (reset_info or {})
                ),
                "timestamp": datetime.now().astimezone().isoformat(),
            },
        )
        print("PASS_V4R1_E1_OPENPI_PRESTEP_CLIENT", flush=True)
    except BaseException as exc:
        if ledger is not None and not ledger.closed:
            ledger.seal()
        if not failure_path.exists():
            write_json_once(
                failure_path,
                {
                    "schema_version": 1,
                    "status": "FAIL_V4R1_E1_OPENPI_PRESTEP_CLIENT_TERMINAL",
                    "attempt_id": args.attempt_id,
                    "policy": args.policy,
                    "task": task,
                    "task_ordinal": args.task_ordinal,
                    "environment_actions": 0,
                    "formal_scientific_trajectories": 0,
                    "exception_type": type(exc).__name__,
                    "exception": str(exc),
                    "automatic_retry_allowed": False,
                    "timestamp": datetime.now().astimezone().isoformat(),
                },
            )
        raise
    finally:
        if client is not None:
            client.close()
        if env is not None:
            env.close()


if __name__ == "__main__":
    main()
