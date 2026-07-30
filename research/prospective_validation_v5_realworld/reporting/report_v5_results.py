"""Deterministically extract manuscript tables from a frozen V5 result JSON."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path


POLICIES = ("pi0", "pi0.5", "grootn1.7")
CONTRACTS = (
    "RW0_failure_only",
    "RW1_half_suboptimal",
    "RW2_non_success",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_once_text(path: Path, text: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())


def write_csv(path: Path, header: list[str], rows: list[list[object]]) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise SystemExit("REFUSE_EXISTING_V5_REPORTING_OUTPUT")
    args.output_dir.mkdir(parents=True)

    result = json.loads(args.result.read_text(encoding="utf-8"))
    points = result["primary_point_estimands"]
    risk_rows = []
    for contract in CONTRACTS:
        for policy in POLICIES:
            risk_rows.append(
                [
                    contract,
                    policy,
                    points[contract]["macro_task_equal_risk"][policy],
                    points[contract]["micro_episode_risk"][policy],
                ]
            )
    write_csv(
        args.output_dir / "V5_POLICY_CONTRACT_RISKS.csv",
        ["contract", "policy", "task_macro_risk", "episode_micro_risk"],
        risk_rows,
    )

    contrast_rows = []
    for key, item in result["bootstrap"]["pairwise_contrasts"].items():
        contract, contrast = key.split(":", 1)
        point = points[contract]["pairwise_macro_differences"][contrast]
        contrast_rows.append(
            [
                contract,
                contrast,
                point,
                item["simultaneous_95_low"],
                item["simultaneous_95_high"],
                item["excludes_zero"],
            ]
        )
    write_csv(
        args.output_dir / "V5_PAIRWISE_CONTRASTS.csv",
        [
            "contract",
            "contrast",
            "point_difference",
            "simultaneous_95_low",
            "simultaneous_95_high",
            "excludes_zero",
        ],
        contrast_rows,
    )

    identification = result["partial_identification"]
    identified_rows = [
        [
            policy,
            *identification["policy_risk_lambda_0_to_1"][policy],
        ]
        for policy in POLICIES
    ]
    write_csv(
        args.output_dir / "V5_PARTIAL_IDENTIFICATION.csv",
        ["policy", "risk_lambda_0", "risk_lambda_1"],
        identified_rows,
    )

    summary = {
        "schema_version": 1,
        "result_sha256": sha256(args.result),
        "sample": result["sample"],
        "ranking_summary": points["ranking_summary"],
        "contract_widths": result["bootstrap"]["contract_widths"],
        "common_lambda_pair_differences": identification[
            "pair_difference_common_lambda"
        ],
        "policy_specific_lambda_pair_differences": identification[
            "pair_difference_policy_specific_lambda"
        ],
        "leave_one_task_out": result["leave_one_task_out"],
        "scientific_values_recomputed": False,
        "scientific_values_modified": False,
    }
    write_once_text(
        args.output_dir / "V5_REPORTING_SUMMARY.json",
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
    )

    files = sorted(args.output_dir.glob("*"))
    manifest = "\n".join(
        f"{sha256(path)}  {path.name}" for path in files
    ) + "\n"
    write_once_text(args.output_dir / "V5_REPORTING_MANIFEST.sha256", manifest)
    print("PASS_V5_REPORTING_EXTRACTION")


if __name__ == "__main__":
    main()
