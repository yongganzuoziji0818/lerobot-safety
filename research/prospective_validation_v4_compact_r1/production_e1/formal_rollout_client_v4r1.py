#!/usr/bin/env python3
"""RoboCasa-side runner for one V3-B2 policy-task shard."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import gymnasium as gym
import numpy as np
import robocasa  # noqa: F401

ROOT = Path("/workspace/lerobot-safety")
V3A3 = ROOT / "research" / "prospective_validation_v3a3"
V3B = ROOT / "research" / "prospective_validation_v3b"
V3B1_REMOTE = ROOT / "research" / "prospective_validation_v3b1" / "remote"
V4R1 = ROOT / "research" / "prospective_validation_v4_compact_r1"
PRODUCTION = V4R1 / "production_e1"
sys.path.insert(0, str(V3B1_REMOTE))
sys.path.insert(0, str(V3B / "scripts"))
sys.path.insert(0, str(PRODUCTION))

from evaluator_primary import CONTRACTS, evaluate as evaluate_primary  # noqa: E402
from evaluator_reference import evaluate as evaluate_reference  # noqa: E402
from ipc_wire_v3b1 import receive_message, send_message  # noqa: E402
from production_common_v4r1 import (  # noqa: E402
    RawActionLedger,
    file_sha256,
    groot_action_diagnostics,
    groot_step_actions,
    logical_array_sha256,
    merge_action_diagnostics,
    openpi_action_diagnostics,
    openpi_step_actions,
    raw_observation,
    validate_groot_chunk,
    validate_openpi_chunk,
    write_gzip_json_once,
    write_json_once,
)
from trace_adapter_v3 import TraceAdapterV3  # noqa: E402

MASTER_SEED = 42
PAIRED_ENVIRONMENT_SEEDS = (42, 43, 44, 45, 46, 47, 48, 49)
FORMAL_HORIZON = 900
POLICIES = ("pi0", "pi05", "groot")
TASK_FILE = V3B / "benchmark" / "task_set_target50.txt"
PROPERTY_BANK = V3B / "property_bank" / "PROPERTY_BANK_V3B.json"
TRACE_ADAPTER = V3B / "scripts" / "trace_adapter_v3.py"
FREEZE_MANIFEST = V4R1 / "V4R1_E1_PRODUCTION_FREEZE_MANIFEST.sha256"
PREDEPLOY_MANIFEST = V4R1 / "V4R1_E1_ENGINEERING_PREFREEZE_MANIFEST.sha256"
FORMAL_RECEIPT = V4R1 / "governance" / "FORMAL_EXECUTION_RECEIPT_E1.json"


def task_list() -> list[str]:
    values = [
        line.strip()
        for line in TASK_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    if len(values) != 50 or len(set(values)) != 50:
        raise RuntimeError("TASK_CENSUS")
    return values


def validate_formal_authorization(attempt_id: str) -> dict[str, Any]:
    if not FREEZE_MANIFEST.is_file() or not FORMAL_RECEIPT.is_file():
        raise RuntimeError("FORMAL_FREEZE_OR_RECEIPT_MISSING")
    receipt = json.loads(FORMAL_RECEIPT.read_text(encoding="utf-8"))
    if (
        receipt.get("status") != "AUTHORIZED_V4R1_E1_FORMAL_EXECUTION"
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


def source_receipts(formal: bool) -> dict[str, str]:
    protocol = FREEZE_MANIFEST if formal else PREDEPLOY_MANIFEST
    return {
        "protocol_manifest": file_sha256(protocol),
        "property_bank": file_sha256(PROPERTY_BANK),
        "adapter": file_sha256(TRACE_ADAPTER),
    }


def write_episode_receipt(
    *,
    output: Path,
    episode_index: int,
    payload: dict[str, Any],
) -> Path:
    path = output / "episodes" / f"{episode_index:02d}" / "episode_receipt.json"
    write_json_once(path, payload)
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", choices=POLICIES, required=True)
    parser.add_argument("--mode", choices=("zero", "learned"), required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--task-ordinal", type=int, required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    tasks = task_list()
    if args.task_ordinal < 0 or args.task_ordinal >= len(tasks):
        raise RuntimeError("TASK_ORDINAL")
    task = tasks[args.task_ordinal]
    formal = args.mode == "learned"
    authorization = (
        validate_formal_authorization(args.attempt_id) if formal else None
    )
    token_hex = os.environ.get("V4R1_IPC_TOKEN", "")
    if len(token_hex) != 64:
        raise RuntimeError("V4R1_IPC_TOKEN_REQUIRED")
    token = bytes.fromhex(token_hex)

    args.output.mkdir(parents=True, exist_ok=True)
    client_receipt_path = args.output / "client_receipt.json"
    shard_failure_path = args.output / "shard_failure.json"
    if client_receipt_path.exists() or shard_failure_path.exists():
        raise RuntimeError("TERMINAL_CLIENT_ARTIFACT_EXISTS")
    if list(args.output.rglob("*.partial*")):
        raise RuntimeError("PREEXISTING_PARTIAL_ARTIFACT")

    bank = json.loads(PROPERTY_BANK.read_text(encoding="utf-8"))
    sources = source_receipts(formal)
    episode_count = len(PAIRED_ENVIRONMENT_SEEDS) if formal else 1
    horizon = FORMAL_HORIZON if formal else 2
    call_index = 0
    action_digest = hashlib.sha256()
    episode_receipt_hashes: list[dict[str, Any]] = []
    total_environment_actions = 0
    total_successes = 0
    completed_formal_trajectories = 0
    total_action_diagnostics = {
        "declared_box_violation_total": 0,
        "robosuite_continuous_saturation_total": 0,
        "robocasa_binary_mapping_change_total": 0,
        "source_defined_endogenous_mapping_total": 0,
    }
    current_episode: int | None = None
    env = None
    client = None
    started = datetime.now().astimezone().isoformat()
    try:
        client = socket.create_connection(("127.0.0.1", args.port), timeout=60)
        client.settimeout(600)

        for episode_index in range(episode_count):
            environment_seed = (
                PAIRED_ENVIRONMENT_SEEDS[episode_index]
                if formal
                else MASTER_SEED
            )
            if env is not None:
                env.close()
            env = gym.make(
                f"robocasa/{task}",
                split="target",
                seed=environment_seed,
            )
            control_frequency = float(env.unwrapped.control_freq)
            current_episode = episode_index
            episode_dir = args.output / "episodes" / f"{episode_index:02d}"
            if episode_dir.exists():
                raise RuntimeError(
                    f"TERMINAL_EPISODE_DIRECTORY_EXISTS:{episode_index}"
                )
            episode_dir.mkdir(parents=True, exist_ok=False)
            ledger = RawActionLedger(episode_dir / "raw_actions.ledger")
            trace_path = episode_dir / "trace.json.gz"
            observation, reset_info = env.reset()
            adapter = TraceAdapterV3(env, task, bank, sources)
            episode_environment_actions = 0
            episode_policy_calls = 0
            episode_action_diagnostics = {
                "declared_box_violation_total": 0,
                "robosuite_continuous_saturation_total": 0,
                "robocasa_binary_mapping_change_total": 0,
                "source_defined_endogenous_mapping_total": 0,
            }
            terminated_signals = 0
            truncated_signals = 0
            success = False
            first_success_step: int | None = None
            terminal_reason = "horizon"
            pending_actions: list[dict[str, np.ndarray]] = []
            episode_exception: BaseException | None = None
            try:
                while episode_environment_actions < horizon:
                    if not pending_actions:
                        observation_arrays = raw_observation(observation)
                        observation_sha = logical_array_sha256(observation_arrays)
                        send_message(
                            client,
                            token,
                            {
                                "op": "infer",
                                "attempt_id": args.attempt_id,
                                "task": task,
                                "task_ordinal": args.task_ordinal,
                                "policy": args.policy,
                                "mode": args.mode,
                                "episode_index": episode_index,
                                "call_index": call_index,
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
                            or response.get("mode") != args.mode
                            or response.get("call_index") != call_index
                            or response.get("observation_logical_sha256")
                            != observation_sha
                            or response.get("action_logical_sha256")
                            != logical_array_sha256(raw_actions)
                        ):
                            raise RuntimeError("IPC_RESPONSE_IDENTITY_OR_HASH")

                        if args.policy == "groot":
                            raw_actions = validate_groot_chunk(raw_actions)
                            diagnostics = groot_action_diagnostics(
                                raw_actions, env.action_space
                            )
                            merge_action_diagnostics(
                                episode_action_diagnostics, diagnostics
                            )
                            merge_action_diagnostics(
                                total_action_diagnostics, diagnostics
                            )
                            pending_actions = groot_step_actions(raw_actions)
                        else:
                            if set(raw_actions) != {"actions"}:
                                raise RuntimeError(
                                    f"OPENPI_WIRE_KEY_CENSUS:{sorted(raw_actions)}"
                                )
                            validate_openpi_chunk(raw_actions["actions"])
                            diagnostics = openpi_action_diagnostics(
                                raw_actions["actions"], env.action_space
                            )
                            merge_action_diagnostics(
                                episode_action_diagnostics, diagnostics
                            )
                            merge_action_diagnostics(
                                total_action_diagnostics, diagnostics
                            )
                            pending_actions = openpi_step_actions(
                                raw_actions["actions"], env.action_space
                            )

                        action_sha = ledger.append(
                            call_index=call_index,
                            observation_sha256=observation_sha,
                            actions=raw_actions,
                            diagnostics=diagnostics,
                        )
                        if action_sha != response["action_logical_sha256"]:
                            raise RuntimeError("LEDGER_ACTION_SHA256")
                        action_digest.update(call_index.to_bytes(8, "big"))
                        action_digest.update(bytes.fromhex(action_sha))
                        call_index += 1
                        episode_policy_calls += int(formal)

                    action = pending_actions.pop(0)
                    observation, _, terminated, truncated, info = env.step(action)
                    episode_environment_actions += 1
                    total_environment_actions += 1
                    adapter.capture_step(
                        episode_environment_actions - 1,
                        episode_environment_actions / control_frequency,
                    )
                    step_success = bool(info.get("success", False))
                    if step_success and not success:
                        success = True
                        first_success_step = episode_environment_actions
                    terminated_signals += int(bool(terminated))
                    truncated_signals += int(bool(truncated))
                    if terminated or truncated:
                        terminal_reason = "simulator_failure"
                        raise RuntimeError(
                            "NONSUCCESS_GYMNASIUM_TERMINAL_SIGNAL:"
                            f"terminated={bool(terminated)}:"
                            f"truncated={bool(truncated)}"
                        )
            except BaseException as exc:
                episode_exception = exc
                if terminal_reason != "simulator_failure":
                    terminal_reason = "policy_failure"
            finally:
                ledger.seal()

            trace = adapter.finalize(terminal_reason)
            write_gzip_json_once(trace_path, trace)
            verdicts: dict[str, dict[str, str]] = {}
            evaluator_agreement = True
            invalid_contracts: list[str] = []
            for contract in CONTRACTS:
                primary = evaluate_primary(trace, contract)
                reference = evaluate_reference(trace, contract)
                if primary != reference:
                    evaluator_agreement = False
                if primary["verdict"] == "INVALID":
                    invalid_contracts.append(contract)
                verdicts[contract] = primary

            episode_status = (
                "PASS_V4R1_FORMAL_EPISODE"
                if formal and not invalid_contracts and episode_exception is None
                else (
                    "PASS_V4R1_NOPOLICY_RUNNER_GATE_EPISODE"
                    if not formal
                    and not invalid_contracts
                    and episode_exception is None
                    else "FAIL_V4R1_EPISODE_TERMINAL"
                )
            )
            receipt_payload = {
                "schema_version": 1,
                "status": episode_status,
                "attempt_id": args.attempt_id,
                "policy": args.policy,
                "task": task,
                "task_ordinal": args.task_ordinal,
                "episode_index": episode_index,
                "split": "target",
                "master_seed": MASTER_SEED,
                "environment_seed": environment_seed,
                "sequential_reset_index": episode_index,
                "formal_horizon": horizon,
                "terminal_reason": terminal_reason,
                "success": success,
                "first_success_step": first_success_step,
                "environment_actions": episode_environment_actions,
                "learned_policy_calls": episode_policy_calls,
                "terminated_signal_count": terminated_signals,
                "truncated_signal_count": truncated_signals,
                "adapter_indeterminate_reasons": trace[
                    "indeterminate_reasons"
                ],
                "verdicts": verdicts,
                "dual_evaluator_exact_agreement": evaluator_agreement,
                "invalid_contracts": invalid_contracts,
                "raw_action_ledger_sha256": file_sha256(
                    episode_dir / "raw_actions.ledger"
                ),
                "raw_action_ledger_frames": ledger.frames,
                "trace_sha256": file_sha256(trace_path),
                "action_diagnostics": episode_action_diagnostics,
                "adapter_action_mutation": False,
                "formal_scientific_trajectories": int(formal),
                "source_receipts": sources,
                "reset_info_keys": sorted(
                    str(key) for key in (reset_info or {})
                ),
                "exception_type": (
                    type(episode_exception).__name__
                    if episode_exception is not None
                    else None
                ),
                "exception": (
                    str(episode_exception)
                    if episode_exception is not None
                    else None
                ),
                "timestamp": datetime.now().astimezone().isoformat(),
            }
            episode_receipt = write_episode_receipt(
                output=args.output,
                episode_index=episode_index,
                payload=receipt_payload,
            )
            episode_receipt_hashes.append(
                {
                    "episode_index": episode_index,
                    "receipt_sha256": file_sha256(episode_receipt),
                    "trace_sha256": receipt_payload["trace_sha256"],
                    "raw_action_ledger_sha256": receipt_payload[
                        "raw_action_ledger_sha256"
                    ],
                }
            )
            if formal:
                completed_formal_trajectories += 1
            total_successes += int(success)
            if (
                episode_exception is not None
                or invalid_contracts
                or not evaluator_agreement
            ):
                raise RuntimeError(
                    f"TERMINAL_EPISODE_FAILURE:{episode_index}:"
                    f"{type(episode_exception).__name__ if episode_exception else 'INVALID'}:"
                    f"{episode_exception if episode_exception else invalid_contracts}"
                )

        send_message(
            client,
            token,
            {
                "op": "shutdown",
                "attempt_id": args.attempt_id,
                "task": task,
                "task_ordinal": args.task_ordinal,
                "policy": args.policy,
                "mode": args.mode,
                "call_count": call_index,
                "action_sequence_sha256": action_digest.hexdigest(),
            },
        )
        acknowledgement, acknowledgement_arrays = receive_message(client, token)
        if (
            acknowledgement.get("op") != "shutdown_ack"
            or acknowledgement.get("attempt_id") != args.attempt_id
            or acknowledgement.get("task") != task
            or acknowledgement.get("task_ordinal") != args.task_ordinal
            or acknowledgement.get("policy") != args.policy
            or acknowledgement.get("mode") != args.mode
            or acknowledgement.get("call_count") != call_index
            or acknowledgement.get("action_sequence_sha256")
            != action_digest.hexdigest()
            or acknowledgement_arrays
        ):
            raise RuntimeError("IPC_SHUTDOWN_ACK")

        write_json_once(
            client_receipt_path,
            {
                "schema_version": 1,
                "status": (
                    "PASS_V4R1_FORMAL_POLICY_TASK_CLIENT"
                    if formal
                    else "PASS_V4R1_NOPOLICY_RUNNER_GATE_CLIENT"
                ),
                "attempt_id": args.attempt_id,
                "policy": args.policy,
                "task": task,
                "task_ordinal": args.task_ordinal,
                "mode": args.mode,
                "started_at": started,
                "finished_at": datetime.now().astimezone().isoformat(),
                "master_seed": MASTER_SEED,
                "paired_environment_seeds": (
                    list(PAIRED_ENVIRONMENT_SEEDS) if formal else [MASTER_SEED]
                ),
                "sequential_resets": episode_count,
                "formal_horizon": horizon,
                "environment_actions": total_environment_actions,
                "learned_policy_calls": call_index if formal else 0,
                "formal_scientific_trajectories": (
                    completed_formal_trajectories if formal else 0
                ),
                "successes": total_successes,
                "action_call_count": call_index,
                "action_sequence_sha256": action_digest.hexdigest(),
                "action_diagnostics": total_action_diagnostics,
                "adapter_action_mutation": False,
                "episode_receipts": episode_receipt_hashes,
                "source_receipts": sources,
                "formal_execution_receipt_sha256": (
                    file_sha256(FORMAL_RECEIPT) if authorization else None
                ),
            },
        )
        print(
            "PASS_V4R1_FORMAL_POLICY_TASK_CLIENT"
            if formal
            else "PASS_V4R1_NOPOLICY_RUNNER_GATE_CLIENT",
            flush=True,
        )
    except BaseException as exc:
        if not shard_failure_path.exists():
            write_json_once(
                shard_failure_path,
                {
                    "schema_version": 1,
                    "status": "FAIL_V4R1_POLICY_TASK_CLIENT_TERMINAL",
                    "attempt_id": args.attempt_id,
                    "policy": args.policy,
                    "task": task,
                    "task_ordinal": args.task_ordinal,
                    "mode": args.mode,
                    "current_episode": current_episode,
                    "timestamp": datetime.now().astimezone().isoformat(),
                    "exception_type": type(exc).__name__,
                    "exception": str(exc),
                    "environment_actions": total_environment_actions,
                    "learned_policy_calls": call_index if formal else 0,
                    "completed_formal_scientific_trajectories": (
                        completed_formal_trajectories if formal else 0
                    ),
                    "automatic_retry_allowed": False,
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
