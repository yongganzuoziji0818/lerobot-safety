#!/usr/bin/env python3
"""RoboCasa-to-V3 production trace adapter."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from role_compiler import compile_role_map, mapping_by_geom_id

SCENE_ROLES = {"movable_object", "fixture", "floor"}


class TraceAdapterV3:
    def __init__(
        self,
        env: Any,
        task: str,
        property_bank: dict[str, Any],
        source_receipts: dict[str, str],
    ) -> None:
        self.env = env
        self.task = task
        self.bank = property_bank
        self.source_receipts = dict(source_receipts)
        self.role_map = compile_role_map(env)
        self.by_id = mapping_by_geom_id(self.role_map)
        self.steps: list[dict[str, Any]] = []
        self.indeterminate: set[str] = set()
        self.initial_floor_objects = self._floor_contact_objects()

        if task not in self.bank.get("tasks", {}):
            raise RuntimeError(f"TASK_NOT_IN_PROPERTY_BANK:{task}")
        self.task_bank = self.bank["tasks"][task]
        self.allowlist = set(self.task_bank["background_contact_allowlist"])
        self.thresholds = self.task_bank["force_thresholds"]
        for role, observed in self.role_map["role_counts"].items():
            expected = self.task_bank["role_count_ranges"].get(role)
            if expected is None or not (
                int(expected["minimum"]) <= int(observed) <= int(expected["maximum"])
            ):
                self.indeterminate.add(f"RUNTIME_ROLE_COUNT_DRIFT:{role}")

    def _floor_contact_objects(self) -> set[str]:
        data = self.env.unwrapped.sim.data._data
        found: set[str] = set()
        for index in range(int(data.ncon)):
            contact = data.contact[index]
            first = self.by_id.get(int(contact.geom1))
            second = self.by_id.get(int(contact.geom2))
            if first is None or second is None:
                continue
            if {first["role"], second["role"]} == {"movable_object", "floor"}:
                obj = first if first["role"] == "movable_object" else second
                found.add(obj["semantic_body_name"])
        return found

    def _forces(self, contact_index: int, robot_record: dict[str, Any]) -> tuple[float, float]:
        import mujoco

        model = self.env.unwrapped.sim.model._model
        data = self.env.unwrapped.sim.data._data
        body_wrench = np.asarray(
            data.cfrc_ext[int(robot_record["raw_body_id"])], dtype=np.float64
        )
        body_force = float(np.linalg.norm(body_wrench[3:6]))
        wrench = np.zeros(6, dtype=np.float64)
        mujoco.mj_contactForce(model, data, contact_index, wrench)
        normal_force = float(abs(wrench[0]))
        if (
            not math.isfinite(body_force)
            or not math.isfinite(normal_force)
            or body_force < 0.0
            or normal_force < 0.0
        ):
            raise RuntimeError("NONFINITE_OR_NEGATIVE_PRODUCTION_FORCE")
        return body_force, normal_force

    def capture_step(self, step_index: int, timestamp_seconds: float) -> None:
        if step_index != len(self.steps):
            raise RuntimeError(f"STEP_SEQUENCE:{step_index}:{len(self.steps)}")
        if self.steps and timestamp_seconds <= self.steps[-1]["timestamp_seconds"]:
            raise RuntimeError("TIMESTAMP_ORDER")
        model = self.env.unwrapped.sim.model._model
        data = self.env.unwrapped.sim.data._data
        events: list[dict[str, Any]] = []

        for contact_index in range(int(data.ncon)):
            contact = data.contact[contact_index]
            first_id, second_id = int(contact.geom1), int(contact.geom2)
            first, second = self.by_id.get(first_id), self.by_id.get(second_id)
            if first is None or second is None:
                known = first if first is not None else second
                if known is not None and known["role"] in {
                    "robot_non_gripper",
                    "movable_object",
                }:
                    self.indeterminate.add(
                        f"UNCLASSIFIED_RUNTIME_CONTACT:{first_id}:{second_id}"
                    )
                continue

            roles = {first["role"], second["role"]}
            if roles == {"movable_object", "floor"}:
                obj = first if first["role"] == "movable_object" else second
                floor = second if obj is first else first
                if obj["semantic_body_name"] not in self.initial_floor_objects:
                    binding = (
                        f"{obj['semantic_body_name']}||"
                        f"{floor['semantic_geom_name']}"
                    )
                    events.append(
                        self._event(
                            step_index,
                            contact_index,
                            "P_OBJECT_FLOOR_DROP",
                            binding,
                            first_id,
                            second_id,
                            0.0,
                            0.0,
                            0.0,
                            0.0,
                            True,
                        )
                    )

            if "robot_non_gripper" not in roles:
                continue
            robot_record = (
                first if first["role"] == "robot_non_gripper" else second
            )
            scene_record = second if robot_record is first else first
            if scene_record["role"] not in SCENE_ROLES:
                continue
            binding = (
                f"{robot_record['semantic_geom_name']}||"
                f"{scene_record['semantic_geom_name']}"
            )
            body_force, normal_force = self._forces(contact_index, robot_record)
            if binding not in self.allowlist:
                events.append(
                    self._event(
                        step_index,
                        contact_index,
                        "P_NON_GRIPPER_SCENE_CONTACT",
                        binding,
                        first_id,
                        second_id,
                        body_force,
                        normal_force,
                        0.0,
                        0.0,
                        True,
                    )
                )
            else:
                pair_thresholds = self.thresholds.get(binding)
                if pair_thresholds is None:
                    self.indeterminate.add(f"MISSING_RUNTIME_THRESHOLD:{binding}")
                    continue
                events.append(
                    self._event(
                        step_index,
                        contact_index,
                        "P_FORCE_ENVELOPE_EXCURSION",
                        binding,
                        first_id,
                        second_id,
                        body_force,
                        normal_force,
                        float(pair_thresholds["body_threshold_N"]),
                        float(pair_thresholds["normal_threshold_N"]),
                        False,
                    )
                )

        self.steps.append(
            {
                "step": step_index,
                "timestamp_seconds": float(timestamp_seconds),
                "events": sorted(events, key=lambda item: item["event_id"]),
            }
        )

    def _event(
        self,
        step_index: int,
        contact_index: int,
        property_id: str,
        binding: str,
        first_id: int,
        second_id: int,
        body_force: float,
        normal_force: float,
        body_threshold: float,
        normal_threshold: float,
        logical: bool,
    ) -> dict[str, Any]:
        raw_match = first_id in self.by_id and second_id in self.by_id
        return {
            "event_id": (
                f"s{step_index:08d}|{property_id}|{binding}|"
                f"c{contact_index:04d}"
            ),
            "property_id": property_id,
            "binding": binding,
            "semantic_match": True,
            "raw_id_match": raw_match,
            "body_force_norm_N": float(body_force),
            "normal_force_N": float(normal_force),
            "body_threshold_N": float(body_threshold),
            "normal_threshold_N": float(normal_threshold),
            "logical_violation": logical,
        }

    def finalize(self, terminal_reason: str) -> dict[str, Any]:
        return {
            "schema_version": 3,
            "complete": True,
            "terminal_reason": terminal_reason,
            "source_receipts": dict(self.source_receipts),
            "mapping_sha256": self.role_map["mapping_sha256"],
            "indeterminate_reasons": sorted(self.indeterminate),
            "steps": self.steps,
        }

