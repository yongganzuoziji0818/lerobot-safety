#!/usr/bin/env python3
"""Fail-closed audit of the write-once V4R1-E2 engineering-gate evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = (
    ROOT
    / "remote_receipts"
    / "l40s_20260729_v4r1_e2_gate001_terminal_success"
)
ATTEMPT = "V4R1-E2-OPENPI-PRESTEP-GATE-001"
MANIFEST = ROOT / "V4R1_E2_GATE001_TERMINAL_SUCCESS_EVIDENCE_MANIFEST.sha256"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_manifest(path: Path, base: Path) -> int:
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        target = base / relative
        assert target.is_file(), target
        assert sha256(target) == expected, target
        count += 1
    return count


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    assert verify_manifest(MANIFEST, ROOT) == 32
    assert (
        EVIDENCE
        / f"engineering_controller_{ATTEMPT}.exit_code.txt"
    ).read_text(encoding="utf-8").strip() == "0"

    launch = load_json(EVIDENCE / f"engineering_controller_{ATTEMPT}.launch_receipt.json")
    assert launch["status"] == "LAUNCHED_V4R1_E2_OPENPI_PRESTEP_GATE_001"
    assert launch["attempt_id"] == ATTEMPT
    assert launch["executor"] == "L40S_ONLY_SINGLE_EXECUTOR"
    assert launch["policies"] == ["pi0", "pi05"]
    assert launch["task_ordinal"] == 0
    assert launch["environment_seed"] == 42
    assert launch["environment_step_called"] is False
    assert launch["formal_scientific_trajectories"] == 0
    assert launch["formal_execution_allowed"] is False
    assert launch["automatic_retry_allowed"] is False

    for policy in ("pi0", "pi05"):
        child = EVIDENCE / ATTEMPT / policy
        assert verify_manifest(
            child / "ENGINEERING_GATE_MANIFEST.sha256", child
        ) == 12
        assert (child / "client.exit_code.txt").read_text().strip() == "0"
        assert (child / "server.exit_code.txt").read_text().strip() == "0"
        receipt = load_json(child / "engineering_gate_receipt.json")
        assert receipt["status"] == "PASS_V4R1_E1_OPENPI_PRESTEP_GATE"
        assert receipt["attempt_id"] == ATTEMPT
        assert receipt["policy"] == policy
        assert receipt["task"] == "CloseBlenderLid"
        assert receipt["task_ordinal"] == 0
        assert receipt["learned_policy_inference_calls"] == 1
        assert receipt["raw_action_ledger_frames"] == 1
        assert receipt["step_reconstruction_exact"] is True
        assert receipt["adapter_action_mutation"] is False
        assert receipt["environment_actions"] == 0
        assert receipt["environment_step_called"] is False
        assert receipt["formal_scientific_trajectories"] == 0
        assert receipt["formal_execution_allowed"] is False
        assert receipt["automatic_retry_allowed"] is False

    print("PASS_V4R1_E2_TERMINAL_EVIDENCE_AUDIT")


if __name__ == "__main__":
    main()
