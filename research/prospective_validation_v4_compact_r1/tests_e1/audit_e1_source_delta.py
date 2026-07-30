#!/usr/bin/env python3
"""Fail-closed source-delta audit for the isolated V4R1-E1 repair."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "production"
NEW = ROOT / "production_e1"


def tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def definitions(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    output = {}
    for node in tree(path).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            output[node.name] = ast.get_source_segment(text, node) or ""
    return output


def literal_assignments(path: Path) -> dict[str, object]:
    output = {}
    for node in tree(path).body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            try:
                output[node.targets[0].id] = ast.literal_eval(node.value)
            except (TypeError, ValueError):
                pass
    return output


def assignment_source(path: Path, name: str) -> str:
    text = path.read_text(encoding="utf-8")
    for node in tree(path).body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == name
        ):
            return ast.get_source_segment(text, node) or ""
    raise KeyError(name)


def main() -> None:
    common_old = definitions(OLD / "production_common_v4r1.py")
    common_new = definitions(NEW / "production_common_v4r1.py")
    for name in common_old:
        if name != "openpi_step_actions":
            assert common_new[name] == common_old[name], name
    assert "openpi_action_diagnostics" in common_new
    repaired_step = common_new["openpi_step_actions"]
    assert "action_space.contains" not in repaired_step
    assert "np.clip" not in repaired_step
    assert "np.where" not in repaired_step
    assert "dtype=subspace.dtype" not in repaired_step

    client_old = literal_assignments(OLD / "formal_rollout_client_v4r1.py")
    client_new = literal_assignments(NEW / "formal_rollout_client_v4r1.py")
    for name in (
        "MASTER_SEED",
        "PAIRED_ENVIRONMENT_SEEDS",
        "FORMAL_HORIZON",
        "POLICIES",
    ):
        assert client_new[name] == client_old[name], name
    assert client_new["MASTER_SEED"] == 42
    assert client_new["PAIRED_ENVIRONMENT_SEEDS"] == tuple(range(42, 50))
    assert client_new["FORMAL_HORIZON"] == 900
    assert client_new["POLICIES"] == ("pi0", "pi05", "groot")

    server_old = definitions(OLD / "formal_policy_server_v4r1.py")
    server_new = definitions(NEW / "formal_policy_server_v4r1.py")
    for name in (
        "prepare_openpi_observation",
        "load_openpi",
        "set_groot_action_seed",
        "load_groot",
        "infer",
    ):
        assert server_new[name] == server_old[name], name
    server_literals_old = literal_assignments(
        OLD / "formal_policy_server_v4r1.py"
    )
    server_literals_new = literal_assignments(
        NEW / "formal_policy_server_v4r1.py"
    )
    for name in ("MASTER_SEED", "POLICIES"):
        assert server_literals_new[name] == server_literals_old[name], name
    assert assignment_source(
        NEW / "formal_policy_server_v4r1.py", "OPENPI"
    ) == assignment_source(OLD / "formal_policy_server_v4r1.py", "OPENPI")
    assert assignment_source(
        NEW / "formal_policy_server_v4r1.py", "GROOT_CHECKPOINT"
    ) == assignment_source(
        OLD / "formal_policy_server_v4r1.py", "GROOT_CHECKPOINT"
    )

    controller_old = definitions(OLD / "formal_controller_v4r1.py")
    controller_new = definitions(NEW / "formal_controller_v4r1.py")
    for name in ("tasks", "run_checked", "audit_shard"):
        assert controller_new[name] == controller_old[name], name

    identical_files = (
        "audit_formal_run_v4r1.py",
        "audit_task_shard_v4r1.py",
        "PRODUCTION_EXECUTION_SEMANTICS.md",
    )
    for name in identical_files:
        assert (NEW / name).read_bytes() == (OLD / name).read_bytes(), name

    old_shard = (OLD / "run_task_shard_v4r1.sh").read_text(encoding="utf-8")
    new_shard = (NEW / "run_task_shard_v4r1.sh").read_text(encoding="utf-8")
    assert new_shard.replace("/production_e1", "/production") == old_shard

    seal_old = (
        OLD / "seal_task_shard_v4r1.py"
    ).read_text(encoding="utf-8")
    seal_new = (
        NEW / "seal_task_shard_v4r1.py"
    ).read_text(encoding="utf-8")
    assert seal_new.replace('"production_e1"', '"production"') == seal_old

    client_text = (NEW / "formal_rollout_client_v4r1.py").read_text(
        encoding="utf-8"
    )
    assert "openpi_action_diagnostics" in client_text
    assert "merge_action_diagnostics" in client_text
    assert "OPENPI_ACTION_OUTSIDE_FROZEN_GYMNASIUM_BOX" not in (
        NEW / "production_common_v4r1.py"
    ).read_text(encoding="utf-8")

    assert literal_assignments(
        NEW / "formal_rollout_client_v4r1.py"
    )["FORMAL_HORIZON"] == 900
    assert "planned_formal_scientific_trajectories" in (
        NEW / "formal_controller_v4r1.py"
    ).read_text(encoding="utf-8")
    assert "!= 1200" in (
        NEW / "formal_controller_v4r1.py"
    ).read_text(encoding="utf-8")
    assert "!= 8" in (
        NEW / "formal_controller_v4r1.py"
    ).read_text(encoding="utf-8")
    assert "!= 900" in (
        NEW / "formal_controller_v4r1.py"
    ).read_text(encoding="utf-8")

    print("PASS_V4R1_E1_SOURCE_DELTA_AUDIT")


if __name__ == "__main__":
    main()
