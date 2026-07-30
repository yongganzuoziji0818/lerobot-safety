#!/usr/bin/env python3
"""Seal one result-free learned OpenPI pre-step engineering gate."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from production_common_v4r1 import (
    audit_raw_action_ledger,
    file_sha256,
    write_json_once,
)


def write_text_once(path: Path, text: str) -> None:
    if path.exists():
        raise RuntimeError(f"WRITE_ONCE_EXISTS:{path}")
    temporary = path.with_suffix(path.suffix + f".partial.{os.getpid()}")
    temporary.write_text(text, encoding="utf-8")
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", choices=("pi0", "pi05"), required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--task-ordinal", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    receipt_path = args.output / "engineering_gate_receipt.json"
    manifest_path = args.output / "ENGINEERING_GATE_MANIFEST.sha256"
    failure_path = args.output / "engineering_gate_seal_failure.json"
    for path in (receipt_path, manifest_path, failure_path):
        if path.exists():
            raise RuntimeError(f"TERMINAL_GATE_ARTIFACT_EXISTS:{path}")
    try:
        if list(args.output.rglob("*.partial*")):
            raise RuntimeError("PARTIAL_ENGINEERING_GATE_ARTIFACT")
        if list(args.output.rglob("*failure*.json")):
            raise RuntimeError("FAILURE_ENGINEERING_GATE_ARTIFACT")
        for name in ("client", "server"):
            code = (args.output / f"{name}.exit_code.txt").read_text(
                encoding="utf-8"
            ).strip()
            if code != "0":
                raise RuntimeError(f"NONZERO_{name.upper()}_EXIT:{code}")

        client = json.loads(
            (args.output / "engineering_client_receipt.json").read_text(
                encoding="utf-8"
            )
        )
        server = json.loads(
            (args.output / "server" / "server_receipt.json").read_text(
                encoding="utf-8"
            )
        )
        identity = {
            "attempt_id": args.attempt_id,
            "policy": args.policy,
            "task": args.task,
            "task_ordinal": args.task_ordinal,
        }
        if any(client.get(key) != value for key, value in identity.items()):
            raise RuntimeError("CLIENT_IDENTITY")
        if any(server.get(key) != value for key, value in identity.items()):
            raise RuntimeError("SERVER_IDENTITY")
        if (
            client.get("status") != "PASS_V4R1_E1_OPENPI_PRESTEP_CLIENT"
            or server.get("status") != "PASS_V4R1_POLICY_TASK_SERVER"
            or server.get("mode") != "engineering"
            or server.get("action_call_count") != 1
            or server.get("engineering_policy_calls") != 1
            or server.get("learned_policy_calls") != 0
            or server.get("formal_scientific_trajectories") != 0
            or client.get("environment_step_called") is not False
            or client.get("environment_actions") != 0
            or client.get("formal_scientific_trajectories") != 0
            or client.get("step_reconstruction_exact") is not True
            or client.get("adapter_action_mutation") is not False
        ):
            raise RuntimeError("ENGINEERING_GATE_CONTRACT")

        ledger_path = args.output / "raw_actions.ledger"
        ledger = audit_raw_action_ledger(ledger_path)
        if (
            ledger.get("frames") != 1
            or ledger["sequence"][0]["call_index"] != 0
            or ledger["sequence"][0]["action_logical_sha256"]
            != client.get("raw_action_logical_sha256")
            or server.get("action_sequence_sha256") is None
        ):
            raise RuntimeError("ENGINEERING_GATE_LEDGER")

        write_json_once(
            receipt_path,
            {
                "schema_version": 1,
                "status": "PASS_V4R1_E1_OPENPI_PRESTEP_GATE",
                "attempt_id": args.attempt_id,
                "policy": args.policy,
                "task": args.task,
                "task_ordinal": args.task_ordinal,
                "learned_policy_inference_calls": 1,
                "raw_action_ledger_frames": 1,
                "raw_action_logical_sha256": client[
                    "raw_action_logical_sha256"
                ],
                "action_diagnostics": client["action_diagnostics"],
                "step_reconstruction_exact": True,
                "adapter_action_mutation": False,
                "environment_step_called": False,
                "environment_actions": 0,
                "formal_scientific_trajectories": 0,
                "formal_execution_allowed": False,
                "automatic_retry_allowed": False,
                "timestamp": datetime.now().astimezone().isoformat(),
            },
        )
        entries = []
        for path in sorted(
            item
            for item in args.output.rglob("*")
            if item.is_file()
            and item not in {manifest_path, failure_path}
            and ".partial" not in item.name
        ):
            relative = str(path.relative_to(args.output)).replace("\\", "/")
            entries.append(f"{file_sha256(path)}  {relative}")
        write_text_once(manifest_path, "\n".join(entries) + "\n")
        print(
            "PASS_V4R1_E1_OPENPI_PRESTEP_GATE "
            f"policy={args.policy} entries={len(entries)}"
        )
    except BaseException as exc:
        if not failure_path.exists():
            write_json_once(
                failure_path,
                {
                    "schema_version": 1,
                    "status": "FAIL_V4R1_E1_OPENPI_PRESTEP_GATE_SEAL_TERMINAL",
                    "attempt_id": args.attempt_id,
                    "policy": args.policy,
                    "task": args.task,
                    "task_ordinal": args.task_ordinal,
                    "exception_type": type(exc).__name__,
                    "exception": str(exc),
                    "automatic_retry_allowed": False,
                    "timestamp": datetime.now().astimezone().isoformat(),
                },
            )
        raise


if __name__ == "__main__":
    main()
