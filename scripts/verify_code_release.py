#!/usr/bin/env python3
"""Read-only integrity and scope check for the code-only public release."""

from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_HASHES = {
    "research/prospective_validation_v3b/benchmark/task_set_target50.txt":
        "1885ab68a843e0264e3b998631bf4cdc6d2e4ec4a8810394ba7ae45305f9bbfc",
    "research/prospective_validation_v3b/contracts/contract_set_v3.csv":
        "1f8bd26eeefc1a1deccc3c3ba7efefba2538c867927541a95fd7c8bcfb13efbb",
    "research/prospective_validation_v3b/property_bank/PROPERTY_BANK_V3B.json":
        "9c50b271a3fb1451284df004e92f60fdb6ba7892092abee6a45cde919bfbfd95",
    "research/prospective_validation_v3b/scripts/evaluator_primary.py":
        "caac5c7a31514bf56504e7f9bcc8ac1cda14fcc92ea24423647c6deccdb0283b",
    "research/prospective_validation_v3b/scripts/evaluator_reference.py":
        "654609488172bc0015bdba8b060c4fb4eaf0665923a541b17f829d675423b46f",
    "research/prospective_validation_v3b/scripts/role_compiler.py":
        "cf42818423ae24737e9158092857c1391e909f91fc009654a1840aeea46df2cc",
    "research/prospective_validation_v3b/scripts/trace_adapter_v3.py":
        "e4300d026814ecadfa9620f132ff8e3c256a2d1b8b154d203a53d6160860c026",
    "research/prospective_validation_v3b1/remote/ipc_wire_v3b1.py":
        "e1659d3cf6e270369647c55a08fa8c71b2b9b66db0f41d963b20f1491a3bcfca",
    "research/prospective_validation_v4_compact_r1/design/V4R1_DESIGN_FREEZE.json":
        "1cdbe6300677f26146157e8a56c0639511b20300c430d2e60c6a96495baa032f",
    "research/prospective_validation_v4_compact_r1/analysis/analyze_formal_results_v4r1.py":
        "6d64cde5d55aa587df02aec183f289b0e9e271b46cdc2e8e32bb9ba7ace0cdae",
    "research/prospective_validation_v4_compact_r1/production_e1/formal_controller_v4r1.py":
        "6e9d8c5b265ba957bd52e1a9931e561fd4c486a37cc606e65980c7f757ef74d3",
    "research/prospective_validation_v4_compact_r1/production_e1/formal_policy_server_v4r1.py":
        "a322b5a7237ee8c8c5d8e8bd052c5a2efab8098bfb22bbf708c378d844d3532b",
    "research/prospective_validation_v4_compact_r1/production_e1/formal_rollout_client_v4r1.py":
        "4d754a0228087fcd3e2899f4e3a018177882fa647794cfb5406b5a25bf2aea81",
    "research/prospective_validation_v4_compact_r1/production_e1/production_common_v4r1.py":
        "ab6a25e11bc9d179923df27b1b8431a9c9b5bd7f1faa302620dbd564790e02c7",
}
FORBIDDEN_NAMES = {
    "analysis_results",
    "postresult_evidence",
    "remote_receipts",
    "submission_package",
    "paper",
    "governance",
}
FORBIDDEN_SUFFIXES = {".docx", ".pdf", ".png", ".tif", ".tiff", ".pt", ".pth"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    for relative, expected in EXPECTED_HASHES.items():
        path = ROOT / relative
        require(path.is_file(), f"MISSING:{relative}")
        require(sha256(path) == expected, f"HASH:{relative}")

    leaked = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if any(part in FORBIDDEN_NAMES for part in relative.parts):
            leaked.append(relative.as_posix())
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            leaked.append(relative.as_posix())
    require(not leaked, f"OUT_OF_SCOPE:{sorted(set(leaked))}")

    manifest = ROOT / "CODE_SOURCE_MANIFEST.sha256"
    if manifest.is_file():
        failures = []
        for line in manifest.read_text(encoding="utf-8").splitlines():
            expected, relative = line.split("  ", 1)
            target = ROOT / relative
            if not target.is_file() or sha256(target) != expected:
                failures.append(relative)
        require(not failures, f"CODE_MANIFEST:{failures}")

    print("PASS_LEROBOT_SAFETY_CODE_ONLY_RELEASE")
    print(f"frozen_core_hashes={len(EXPECTED_HASHES)}/{len(EXPECTED_HASHES)}")
    print("scientific_results_included=false")
    print("scientific_analysis_recomputed=false")


if __name__ == "__main__":
    main()
