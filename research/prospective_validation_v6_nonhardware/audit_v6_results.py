#!/usr/bin/env python3
"""Read-only structural and binding audit for completed V6 outputs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    manifest = {}
    for line in (ROOT / "V6_NONHARDWARE_PREFREEZE_MANIFEST.sha256").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        manifest[name] = digest
    checks = {}
    for name, expected in manifest.items():
        checks[f"prefreeze:{name}"] = sha256(ROOT / name) == expected

    synthetic = json.loads((ROOT / "results" / "V6_SYNTHETIC_ORACLE_CALIBRATION_001.json").read_text(encoding="utf-8"))
    label = json.loads((ROOT / "results" / "V6_POSTHOC_LABEL_FLIP_RADIUS_001.json").read_text(encoding="utf-8"))
    checks["synthetic_status_pass"] = synthetic["status"] == "PASS"
    checks["synthetic_all_five_gates"] = len(synthetic["gates"]) == 5 and all(synthetic["gates"].values())
    checks["synthetic_script_binding"] = synthetic["script_sha256"] == manifest["synthetic/oracle_calibration.py"]
    checks["label_script_binding"] = label["script_sha256"] == manifest["robustness/label_flip_radius.py"]
    checks["label_source_binding"] = label["source_hashes"] == {
        "so101.parquet": "0c249334caef8506ee4d15b5ea4d7b52ecc6afa7662010eadeff5d88d0dfc320",
        "bimanual_so101.parquet": "e147be28c0b6a06ffe54ff3f4bbe37135f749c545cbb26516d4702da3c0fd6b0",
    }
    checks["label_census"] = label["episodes"] == 1078 and label["tasks"] == 12
    checks["three_pairwise_results"] = len(label["pairwise_results"]) == 3
    checks["positive_joint_strict_radii"] = all(
        item["all_contracts_simultaneous"]["minimum_extreme_flips_to_strict_reverse"] > 0
        for item in label["pairwise_results"].values()
    )
    output = {
        "schema_version": 1,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks_passed": sum(checks.values()),
        "checks_total": len(checks),
        "checks": checks,
        "synthetic_result_sha256": sha256(ROOT / "results" / "V6_SYNTHETIC_ORACLE_CALIBRATION_001.json"),
        "label_result_sha256": sha256(ROOT / "results" / "V6_POSTHOC_LABEL_FLIP_RADIUS_001.json"),
        "audit_scope": "read-only structure and frozen-source bindings; no empirical recomputation",
    }
    path = ROOT / "governance" / "V6_RESULT_AUDIT.json"
    if path.exists():
        raise RuntimeError(f"write-once output exists: {path}")
    path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": output["status"], "checks": f"{output['checks_passed']}/{output['checks_total']}"}))


if __name__ == "__main__":
    main()

