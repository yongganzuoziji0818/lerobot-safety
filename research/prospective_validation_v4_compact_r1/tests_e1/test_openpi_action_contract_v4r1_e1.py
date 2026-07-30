#!/usr/bin/env python3
"""Result-independent contract tests for the V4R1-E1 OpenPI repair."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "production_e1"))

from production_common_v4r1 import (  # noqa: E402
    KEYS,
    OPENPI_SLICES,
    openpi_action_diagnostics,
    openpi_step_actions,
)


class Box:
    def __init__(self, shape: tuple[int, ...]) -> None:
        self.shape = shape
        self.dtype = np.dtype("float32")
        self.low = np.full(shape, -1.0, dtype=np.float32)
        self.high = np.full(shape, 1.0, dtype=np.float32)


class DictSpace:
    def __init__(self) -> None:
        shapes = {
            "action.end_effector_position": (3,),
            "action.end_effector_rotation": (3,),
            "action.gripper_close": (1,),
            "action.base_motion": (4,),
            "action.control_mode": (1,),
        }
        self.spaces = {key: Box(shape) for key, shape in shapes.items()}

    def contains(self, action: dict[str, np.ndarray]) -> bool:
        return all(
            value.shape == self.spaces[key].shape
            and np.all(value >= self.spaces[key].low)
            and np.all(value <= self.spaces[key].high)
            for key, value in action.items()
        )


def independent_reference(
    actions: np.ndarray, space: DictSpace
) -> tuple[int, int, int]:
    box = 0
    continuous = 0
    binary = 0
    for key in KEYS:
        raw = actions[:, OPENPI_SLICES[key]]
        subspace = space.spaces[key]
        low = np.broadcast_to(subspace.low, raw.shape)
        high = np.broadcast_to(subspace.high, raw.shape)
        excursion = (raw < low) | (raw > high)
        count = int(np.count_nonzero(excursion))
        box += count
        if key in {
            "action.end_effector_position",
            "action.end_effector_rotation",
            "action.base_motion",
        }:
            continuous += count
        else:
            mapped = np.where(raw < 0.5, -1.0, 1.0).astype(raw.dtype)
            binary += int(np.count_nonzero(mapped != raw))
    return box, continuous, binary


def main() -> None:
    space = DictSpace()
    actions = np.zeros((5, 12), dtype=np.float32)
    actions[0, 7] = np.float32(1.25)
    frozen_copy = actions.copy()

    diagnostics = openpi_action_diagnostics(actions, space)
    steps = openpi_step_actions(actions, space)
    reference = independent_reference(actions, space)

    assert np.array_equal(actions, frozen_copy)
    assert len(steps) == 5
    assert tuple(steps[0]) == KEYS
    assert steps[0]["action.base_motion"][0] == np.float32(1.25)
    assert not space.contains(steps[0])
    assert diagnostics["declared_box_violation_total"] == reference[0] == 1
    assert diagnostics["robosuite_continuous_saturation_total"] == reference[1] == 1
    assert diagnostics["robocasa_binary_mapping_change_total"] == reference[2] == 10
    assert (
        diagnostics["source_defined_endogenous_mapping_total"]
        == reference[1] + reference[2]
        == 11
    )
    assert diagnostics["adapter_action_mutation"] is False
    first = diagnostics["by_key"]["action.base_motion"][
        "first_declared_box_violation"
    ]
    assert first == {
        "index": [0, 0],
        "raw_value": 1.25,
        "low": -1.0,
        "high": 1.0,
        "direction": "above",
    }

    original = (
        ROOT / "production" / "production_common_v4r1.py"
    ).read_text(encoding="utf-8")
    repaired = (
        ROOT / "production_e1" / "production_common_v4r1.py"
    ).read_text(encoding="utf-8")
    assert "OPENPI_ACTION_OUTSIDE_FROZEN_GYMNASIUM_BOX" in original
    assert "OPENPI_ACTION_OUTSIDE_FROZEN_GYMNASIUM_BOX" not in repaired

    print("PASS_V4R1_E1_OPENPI_ACTION_CONTRACT_TEST")


if __name__ == "__main__":
    main()
