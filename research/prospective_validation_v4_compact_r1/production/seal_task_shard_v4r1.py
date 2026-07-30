#!/usr/bin/env python3
"""Seal one complete V4-Compact-R1 policy-task shard."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path("/workspace/lerobot-safety")
V3B = ROOT / "research" / "prospective_validation_v3b"
V3B1_REMOTE = ROOT / "research" / "prospective_validation_v3b1" / "remote"
PRODUCTION = (
    ROOT / "research" / "prospective_validation_v4_compact_r1" / "production"
)
sys.path.insert(0, str(V3B1_REMOTE))
sys.path.insert(0, str(V3B / "scripts"))
sys.path.insert(0, str(PRODUCTION))

from evaluator_primary import CONTRACTS, evaluate as evaluate_primary  # noqa: E402
from evaluator_reference import evaluate as evaluate_reference  # noqa: E402
from production_common_v4r1 import (  # noqa: E402
    audit_raw_action_ledger,
    file_sha256,
    write_json_once,
)


def write_text_once(path: Path, text: str) -> None:
    if path.exists():
        raise RuntimeError(f"WRITE_ONCE_EXISTS:{path}")
    temporary = path.with_suffix(path.suffix + f".partial.{os.getpid()}")
    if temporary.exists():
        raise RuntimeError(f"PARTIAL_EXISTS:{temporary}")
    temporary.write_text(text, encoding="utf-8")
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def add_totals(destination: dict[str, int], source: dict[str, Any]) -> None:
    for key in destination:
        destination[key] += int(source[key])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", choices=("pi0", "pi05", "groot"), required=True)
    parser.add_argument("--mode", choices=("zero", "learned"), required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--task-ordinal", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    receipt_path = args.output / "shard_receipt.json"
    manifest_path = args.output / "SHARD_MANIFEST.sha256"
    failure_path = args.output / "seal_failure.json"
    for path in (receipt_path, manifest_path, failure_path):
        if path.exists():
            raise RuntimeError(f"TERMINAL_SEAL_ARTIFACT_EXISTS:{path}")
    try:
        partials = sorted(str(path) for path in args.output.rglob("*.partial*"))
        failures = sorted(
            str(path.relative_to(args.output)).replace("\\", "/")
            for path in args.output.rglob("*failure*.json")
        )
        if partials:
            raise RuntimeError(f"PARTIAL_ARTIFACTS:{partials}")
        if failures:
            raise RuntimeError(f"FAILURE_ARTIFACTS:{failures}")

        server_path = args.output / "server" / "server_receipt.json"
        client_path = args.output / "client_receipt.json"
        server = json.loads(server_path.read_text(encoding="utf-8"))
        client = json.loads(client_path.read_text(encoding="utf-8"))
        identity = {
            "attempt_id": args.attempt_id,
            "task": args.task,
            "task_ordinal": args.task_ordinal,
            "policy": args.policy,
            "mode": args.mode,
        }
        for key, expected in identity.items():
            if server.get(key) != expected or client.get(key) != expected:
                raise RuntimeError(f"RECEIPT_IDENTITY:{key}")
        if server.get("status") != "PASS_V4R1_POLICY_TASK_SERVER":
            raise RuntimeError("SERVER_STATUS")
        expected_client_status = (
            "PASS_V4R1_FORMAL_POLICY_TASK_CLIENT"
            if args.mode == "learned"
            else "PASS_V4R1_NOPOLICY_RUNNER_GATE_CLIENT"
        )
        if client.get("status") != expected_client_status:
            raise RuntimeError("CLIENT_STATUS")

        expected_episodes = 8 if args.mode == "learned" else 1
        episode_dirs = sorted(
            path
            for path in (args.output / "episodes").iterdir()
            if path.is_dir()
        )
        if len(episode_dirs) != expected_episodes:
            raise RuntimeError(
                f"EPISODE_DIRECTORY_CENSUS:{len(episode_dirs)}:"
                f"{expected_episodes}"
            )

        global_sequence: list[dict[str, Any]] = []
        episode_receipt_hashes: list[dict[str, Any]] = []
        successes = 0
        environment_actions = 0
        formal_trajectories = 0
        diagnostics_total = {
            "declared_box_violation_total": 0,
            "robosuite_continuous_saturation_total": 0,
            "robocasa_binary_mapping_change_total": 0,
            "source_defined_endogenous_mapping_total": 0,
        }
        for expected_index, episode_dir in enumerate(episode_dirs):
            if episode_dir.name != f"{expected_index:02d}":
                raise RuntimeError(
                    f"EPISODE_DIRECTORY_SEQUENCE:{episode_dir.name}:"
                    f"{expected_index:02d}"
                )
            episode_receipt_path = episode_dir / "episode_receipt.json"
            trace_path = episode_dir / "trace.json.gz"
            ledger_path = episode_dir / "raw_actions.ledger"
            episode = json.loads(
                episode_receipt_path.read_text(encoding="utf-8")
            )
            if (
                episode.get("episode_index") != expected_index
                or episode.get("attempt_id") != args.attempt_id
                or episode.get("policy") != args.policy
                or episode.get("task") != args.task
                or episode.get("task_ordinal") != args.task_ordinal
                or episode.get("trace_sha256") != file_sha256(trace_path)
                or episode.get("raw_action_ledger_sha256")
                != file_sha256(ledger_path)
                or episode.get("dual_evaluator_exact_agreement") is not True
                or episode.get("invalid_contracts") != []
            ):
                raise RuntimeError(f"EPISODE_RECEIPT:{expected_index}")
            expected_status = (
                "PASS_V4R1_FORMAL_EPISODE"
                if args.mode == "learned"
                else "PASS_V4R1_NOPOLICY_RUNNER_GATE_EPISODE"
            )
            if episode.get("status") != expected_status:
                raise RuntimeError(f"EPISODE_STATUS:{expected_index}")
            if args.mode == "learned" and (
                episode.get("environment_seed") != 42 + expected_index
                or episode.get("environment_actions") != 900
                or episode.get("formal_horizon") != 900
                or episode.get("terminal_reason") != "horizon"
            ):
                raise RuntimeError(f"V4R1_EXPOSURE_OR_SEED:{expected_index}")
            with gzip.open(trace_path, "rt", encoding="ascii") as handle:
                trace = json.load(handle)
            for contract in CONTRACTS:
                primary = evaluate_primary(trace, contract)
                reference = evaluate_reference(trace, contract)
                if (
                    primary != reference
                    or episode["verdicts"].get(contract) != primary
                    or primary["verdict"] == "INVALID"
                ):
                    raise RuntimeError(
                        f"EPISODE_EVALUATOR:{expected_index}:{contract}"
                    )
            ledger_audit = audit_raw_action_ledger(ledger_path)
            if (
                ledger_audit["frames"]
                != episode.get("raw_action_ledger_frames")
            ):
                raise RuntimeError(f"LEDGER_FRAME_CENSUS:{expected_index}")
            global_sequence.extend(ledger_audit["sequence"])
            episode_receipt_hashes.append(
                {
                    "episode_index": expected_index,
                    "receipt_sha256": file_sha256(episode_receipt_path),
                    "trace_sha256": file_sha256(trace_path),
                    "raw_action_ledger_sha256": file_sha256(ledger_path),
                }
            )
            successes += int(bool(episode["success"]))
            environment_actions += int(episode["environment_actions"])
            formal_trajectories += int(
                episode["formal_scientific_trajectories"]
            )
            add_totals(diagnostics_total, episode["action_diagnostics"])

        action_digest = hashlib.sha256()
        for expected_call, record in enumerate(global_sequence):
            if record["call_index"] != expected_call:
                raise RuntimeError(
                    f"GLOBAL_ACTION_CALL_SEQUENCE:{record['call_index']}:"
                    f"{expected_call}"
                )
            action_digest.update(expected_call.to_bytes(8, "big"))
            action_digest.update(
                bytes.fromhex(record["action_logical_sha256"])
            )
        action_sequence_sha256 = action_digest.hexdigest()
        if (
            len(global_sequence) != server.get("action_call_count")
            or len(global_sequence) != client.get("action_call_count")
            or action_sequence_sha256
            != server.get("action_sequence_sha256")
            or action_sequence_sha256
            != client.get("action_sequence_sha256")
            or environment_actions != client.get("environment_actions")
            or successes != client.get("successes")
            or formal_trajectories
            != client.get("formal_scientific_trajectories")
            or diagnostics_total != client.get("action_diagnostics")
        ):
            raise RuntimeError("SERVER_CLIENT_EPISODE_AGGREGATE")
        if args.mode == "learned":
            if formal_trajectories != 8:
                raise RuntimeError("FORMAL_TRAJECTORY_CENSUS")
            if server.get("learned_policy_calls") != len(global_sequence):
                raise RuntimeError("SERVER_LEARNED_POLICY_CALL_CENSUS")
        elif (
            formal_trajectories != 0
            or server.get("learned_policy_calls") != 0
            or client.get("learned_policy_calls") != 0
        ):
            raise RuntimeError("NOPOLICY_GATE_SCIENTIFIC_COUNT")

        write_json_once(
            receipt_path,
            {
                "schema_version": 1,
                "status": (
                    "PASS_V4R1_FORMAL_POLICY_TASK_SHARD"
                    if args.mode == "learned"
                    else "PASS_V4R1_NOPOLICY_RUNNER_GATE_SHARD"
                ),
                **identity,
                "episode_count": expected_episodes,
                "environment_actions": environment_actions,
                "learned_policy_calls": (
                    len(global_sequence) if args.mode == "learned" else 0
                ),
                "formal_scientific_trajectories": formal_trajectories,
                "successes": successes,
                "action_call_count": len(global_sequence),
                "action_sequence_sha256": action_sequence_sha256,
                "action_diagnostics": diagnostics_total,
                "adapter_action_mutation": False,
                "server_receipt_sha256": file_sha256(server_path),
                "client_receipt_sha256": file_sha256(client_path),
                "episode_receipts": episode_receipt_hashes,
                "timestamp": datetime.now().astimezone().isoformat(),
            },
        )

        manifest_entries: list[str] = []
        excluded_runtime_files = {
            "controller.exit_code.txt",
            "seal.exit_code.txt",
            "seal.stderr.log",
            "seal.stdout.log",
        }
        for path in sorted(
            candidate
            for candidate in args.output.rglob("*")
            if candidate.is_file()
            and candidate != manifest_path
            and candidate != failure_path
            and str(candidate.relative_to(args.output)).replace("\\", "/")
            not in excluded_runtime_files
        ):
            relative = str(path.relative_to(args.output)).replace("\\", "/")
            manifest_entries.append(f"{file_sha256(path)}  {relative}")
        write_text_once(
            manifest_path, "\n".join(manifest_entries) + "\n"
        )
        print(
            "PASS_V4R1_FORMAL_POLICY_TASK_SHARD"
            if args.mode == "learned"
            else "PASS_V4R1_NOPOLICY_RUNNER_GATE_SHARD",
            flush=True,
        )
    except BaseException as exc:
        if not failure_path.exists():
            write_json_once(
                failure_path,
                {
                    "schema_version": 1,
                    "status": "FAIL_V4R1_TASK_SHARD_SEAL_TERMINAL",
                    "attempt_id": args.attempt_id,
                    "policy": args.policy,
                    "task": args.task,
                    "task_ordinal": args.task_ordinal,
                    "mode": args.mode,
                    "timestamp": datetime.now().astimezone().isoformat(),
                    "exception_type": type(exc).__name__,
                    "exception": str(exc),
                    "automatic_retry_allowed": False,
                },
            )
        raise


if __name__ == "__main__":
    main()
