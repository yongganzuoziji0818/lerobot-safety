#!/usr/bin/env python3
"""Deterministic source-backed RoboCasa geometry role compiler for V3-A3."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Any

ROLES = (
    "robot_gripper",
    "robot_non_gripper",
    "movable_object",
    "fixture",
    "floor",
)
FLOOR_QUALIFIED_TYPE = "robocasa.models.fixtures.others.Floor"


def _values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, dict):
        return list(value.values())
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _body_id(model: Any, name: str) -> int:
    import mujoco

    identifier = int(mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name))
    if identifier < 0:
        raise RuntimeError(f"MISSING_ROOT_BODY:{name}")
    return identifier


def _geom_name(model: Any, identifier: int) -> str:
    import mujoco

    name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, identifier)
    if not name:
        raise RuntimeError(f"UNNAMED_SAFETY_RELEVANT_GEOM:{identifier}")
    return str(name)


def subtree_body_ids(model: Any, root_body_name: str) -> set[int]:
    root = _body_id(model, root_body_name)
    result = {root}
    for body_id in range(int(model.nbody)):
        cursor = body_id
        while cursor > 0 and cursor != root:
            cursor = int(model.body_parentid[cursor])
        if cursor == root:
            result.add(body_id)
    return result


def subtree_geom_ids(model: Any, root_body_name: str) -> set[int]:
    bodies = subtree_body_ids(model, root_body_name)
    return {
        geom_id
        for geom_id in range(int(model.ngeom))
        if int(model.geom_bodyid[geom_id]) in bodies
    }


def roots_geom_ids(model: Any, items: Iterable[Any]) -> set[int]:
    result: set[int] = set()
    for item in items:
        root_body = getattr(item, "root_body", None)
        if not isinstance(root_body, str) or not root_body:
            raise RuntimeError(f"MISSING_MODEL_ROOT_BODY:{type(item).__name__}")
        result.update(subtree_geom_ids(model, root_body))
    return result


def qualified_type(item: Any) -> str:
    return f"{type(item).__module__}.{type(item).__name__}"


def _owner_records(model: Any, items: Iterable[Any]) -> list[dict[str, Any]]:
    output = []
    for item in items:
        root = getattr(item, "root_body", None)
        if not isinstance(root, str) or not root:
            raise RuntimeError(f"MISSING_MODEL_ROOT_BODY:{type(item).__name__}")
        output.append(
            {
                "root_body": root,
                "qualified_type": qualified_type(item),
                "body_ids": subtree_body_ids(model, root),
            }
        )
    return output


def _semantic_body_resolution(
    model: Any,
    raw_body_id: int,
    role: str,
    owner_records: list[dict[str, Any]],
) -> dict[str, Any]:
    import mujoco

    direct_name = mujoco.mj_id2name(
        model, mujoco.mjtObj.mjOBJ_BODY, raw_body_id
    )
    if direct_name:
        if raw_body_id == 0:
            raise RuntimeError(f"WORLD_BODY_SAFETY_ROLE:{role}")
        return {
            "strategy": "DIRECT_NAMED_BODY",
            "raw_body_named": True,
            "resolved_body_id": raw_body_id,
            "resolved_body_name": str(direct_name),
            "resolution_path": [
                {"body_id": raw_body_id, "body_name": str(direct_name)}
            ],
            "source_owner_root_body": None,
            "source_owner_qualified_type": None,
        }

    owners = [
        record for record in owner_records if raw_body_id in record["body_ids"]
    ]
    if len(owners) != 1:
        raise RuntimeError(
            f"UNNAMED_BODY_SOURCE_OWNER_CENSUS:{role}:{raw_body_id}:{len(owners)}"
        )
    owner = owners[0]
    path = []
    cursor = raw_body_id
    while cursor > 0 and cursor in owner["body_ids"]:
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, cursor)
        path.append(
            {
                "body_id": cursor,
                "body_name": None if not name else str(name),
            }
        )
        if name:
            return {
                "strategy": "NEAREST_NAMED_NONWORLD_ANCESTOR",
                "raw_body_named": False,
                "resolved_body_id": cursor,
                "resolved_body_name": str(name),
                "resolution_path": path,
                "source_owner_root_body": owner["root_body"],
                "source_owner_qualified_type": owner["qualified_type"],
            }
        cursor = int(model.body_parentid[cursor])
    raise RuntimeError(
        f"UNRESOLVED_UNNAMED_BODY_WITHIN_SOURCE:{role}:{raw_body_id}"
    )


def compile_role_map(env: Any) -> dict[str, Any]:
    import mujoco

    unwrapped = env.unwrapped
    model = unwrapped.sim.model._model
    robots = list(unwrapped.robots)
    if len(robots) != 1:
        raise RuntimeError(f"UNEXPECTED_ROBOT_COUNT:{len(robots)}")

    robot = robots[0]
    robot_all = roots_geom_ids(model, [robot.robot_model])
    grippers = _values(getattr(robot, "gripper", None))
    if not grippers:
        raise RuntimeError("MISSING_GRIPPER_MODEL")
    robot_gripper = roots_geom_ids(model, grippers)
    robot_non_gripper = robot_all.difference(robot_gripper)
    if not robot_gripper or not robot_non_gripper:
        raise RuntimeError("EMPTY_ROBOT_ROLE")

    objects = _values(getattr(unwrapped, "objects", None))
    fixtures = _values(getattr(unwrapped, "fixtures", None))
    floor_fixtures = [
        item for item in fixtures if qualified_type(item) == FLOOR_QUALIFIED_TYPE
    ]
    floor_fixture_ids = {id(item) for item in floor_fixtures}
    non_floor_fixtures = [
        item for item in fixtures if id(item) not in floor_fixture_ids
    ]
    movable_object = roots_geom_ids(model, objects)
    fixture = roots_geom_ids(model, non_floor_fixtures)
    floor = roots_geom_ids(model, floor_fixtures)
    if not fixture:
        raise RuntimeError("EMPTY_NON_FLOOR_FIXTURE_ROLE")
    if not floor:
        raise RuntimeError("EMPTY_SOURCE_BACKED_FLOOR_ROLE")

    role_sets = {
        "robot_gripper": robot_gripper,
        "robot_non_gripper": robot_non_gripper,
        "movable_object": movable_object,
        "fixture": fixture,
        "floor": floor,
    }
    role_items = {
        "robot_gripper": grippers,
        "robot_non_gripper": [robot.robot_model],
        "movable_object": objects,
        "fixture": non_floor_fixtures,
        "floor": floor_fixtures,
    }
    owners_by_role = {
        role: _owner_records(model, role_items[role]) for role in ROLES
    }
    inverse: dict[int, str] = {}
    for role in ROLES:
        for geom_id in sorted(role_sets[role]):
            if geom_id in inverse:
                raise RuntimeError(
                    f"OVERLAPPING_ROLE:{geom_id}:{inverse[geom_id]}:{role}"
                )
            inverse[geom_id] = role

    records = []
    for geom_id, role in sorted(inverse.items()):
        body_id = int(model.geom_bodyid[geom_id])
        resolution = _semantic_body_resolution(
            model, body_id, role, owners_by_role[role]
        )
        records.append(
            {
                "raw_geom_id": geom_id,
                "semantic_geom_name": _geom_name(model, geom_id),
                "raw_body_id": body_id,
                "semantic_body_name": resolution["resolved_body_name"],
                "body_resolution": resolution,
                "role": role,
            }
        )
    serialized = json.dumps(
        records, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {
        "schema_version": 1,
        "records": records,
        "mapping_sha256": hashlib.sha256(serialized).hexdigest(),
        "role_counts": {
            role: sum(record["role"] == role for record in records)
            for role in ROLES
        },
    }


def mapping_by_geom_id(role_map: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {
        int(record["raw_geom_id"]): record
        for record in role_map["records"]
    }
