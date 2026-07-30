#!/usr/bin/env python3
"""Shared fail-closed utilities for V3-B2 production execution."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import struct
from pathlib import Path
from typing import Any, BinaryIO

import numpy as np

KEYS = (
    "action.end_effector_position",
    "action.end_effector_rotation",
    "action.gripper_close",
    "action.base_motion",
    "action.control_mode",
)
GROOT_SHAPES = {
    "action.end_effector_position": (16, 3),
    "action.end_effector_rotation": (16, 3),
    "action.gripper_close": (16, 1),
    "action.base_motion": (16, 4),
    "action.control_mode": (16, 1),
}
OPENPI_SLICES = {
    "action.end_effector_position": slice(0, 3),
    "action.end_effector_rotation": slice(3, 6),
    "action.gripper_close": slice(6, 7),
    "action.base_motion": slice(7, 11),
    "action.control_mode": slice(11, 12),
}
OBSERVATION_SHAPES = {
    "annotation.human.task_description": (),
    "state.base_position": (3,),
    "state.base_rotation": (4,),
    "state.end_effector_position_relative": (3,),
    "state.end_effector_rotation_relative": (4,),
    "state.gripper_qpos": (2,),
    "video.robot0_agentview_left": (256, 256, 3),
    "video.robot0_agentview_right": (256, 256, 3),
    "video.robot0_eye_in_hand": (256, 256, 3),
}
CONTINUOUS_KEYS = {
    "action.end_effector_position",
    "action.end_effector_rotation",
    "action.base_motion",
}
_LEDGER_MAGIC = b"V3B2RAW1"
_U64 = struct.Struct("!Q")


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def logical_array_sha256(arrays: dict[str, np.ndarray]) -> str:
    digest = hashlib.sha256()
    for key in sorted(arrays):
        value = np.ascontiguousarray(np.asarray(arrays[key]))
        digest.update(key.encode("utf-8"))
        digest.update(str(value.dtype).encode("ascii"))
        digest.update(canonical_json({"shape": list(value.shape)}))
        digest.update(value.tobytes(order="C"))
    return digest.hexdigest()


def write_json_once(path: Path, value: Any) -> None:
    if path.exists():
        raise RuntimeError(f"WRITE_ONCE_EXISTS:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".partial.{os.getpid()}")
    if temporary.exists():
        raise RuntimeError(f"PARTIAL_EXISTS:{temporary}")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def write_gzip_json_once(path: Path, value: Any) -> None:
    if path.exists():
        raise RuntimeError(f"WRITE_ONCE_EXISTS:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".partial.{os.getpid()}")
    if temporary.exists():
        raise RuntimeError(f"PARTIAL_EXISTS:{temporary}")
    with temporary.open("wb") as raw:
        with gzip.GzipFile(
            filename="", mode="wb", compresslevel=6, fileobj=raw, mtime=0
        ) as compressed:
            compressed.write(
                json.dumps(
                    value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
                ).encode("ascii")
            )
        raw.flush()
        os.fsync(raw.fileno())
    os.replace(temporary, path)


def raw_observation(observation: dict[str, Any]) -> dict[str, np.ndarray]:
    output = {
        key: np.asarray(value)
        for key, value in observation.items()
        if key.startswith(("video.", "state.", "annotation."))
    }
    if set(output) != set(OBSERVATION_SHAPES):
        raise RuntimeError(f"OBSERVATION_KEY_CENSUS:{sorted(output)}")
    for key, expected in OBSERVATION_SHAPES.items():
        value = output[key]
        if value.shape != expected:
            raise RuntimeError(
                f"OBSERVATION_SHAPE:{key}:{value.shape}:{expected}"
            )
        if key != "annotation.human.task_description" and not np.isfinite(
            value
        ).all():
            raise RuntimeError(f"OBSERVATION_NONFINITE:{key}")
    return output


def validate_groot_chunk(actions: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    if not isinstance(actions, dict) or set(actions) != set(KEYS):
        raise RuntimeError(f"GROOT_ACTION_KEY_CENSUS:{sorted(actions)}")
    output: dict[str, np.ndarray] = {}
    for key in KEYS:
        value = np.asarray(actions[key])
        if value.shape != GROOT_SHAPES[key]:
            raise RuntimeError(
                f"GROOT_ACTION_SHAPE:{key}:{value.shape}:{GROOT_SHAPES[key]}"
            )
        if not np.isfinite(value).all():
            raise RuntimeError(f"GROOT_ACTION_NONFINITE:{key}")
        output[key] = value
    return output


def validate_openpi_chunk(actions: Any) -> np.ndarray:
    value = np.asarray(actions)
    if value.ndim != 2 or value.shape[0] < 5 or value.shape[1] != 12:
        raise RuntimeError(f"OPENPI_ACTION_SHAPE:{value.shape}")
    if not np.isfinite(value).all():
        raise RuntimeError("OPENPI_ACTION_NONFINITE")
    return value


def groot_action_diagnostics(
    actions: dict[str, np.ndarray], action_space: Any
) -> dict[str, Any]:
    by_key: dict[str, Any] = {}
    box_total = 0
    continuous_total = 0
    binary_total = 0
    for key in KEYS:
        raw = np.asarray(actions[key])
        subspace = action_space.spaces[key]
        low = np.broadcast_to(np.asarray(subspace.low), raw.shape)
        high = np.broadcast_to(np.asarray(subspace.high), raw.shape)
        below = raw < low
        above = raw > high
        violation = below | above
        violation_count = int(np.count_nonzero(violation))
        box_total += violation_count
        if key in CONTINUOUS_KEYS:
            projected = np.clip(raw, low, high)
            continuous_total += violation_count
            projection_type = "robosuite_continuous_controller_input_clip"
        else:
            projected = np.where(raw < 0.5, -1.0, 1.0).astype(raw.dtype)
            binary_total += int(np.count_nonzero(projected != raw))
            projection_type = "robocasa_binary_threshold_mapping"
        first = None
        if violation_count:
            index = tuple(int(v) for v in np.argwhere(violation)[0])
            first = {
                "index": list(index),
                "raw_value": float(raw[index]),
                "low": float(low[index]),
                "high": float(high[index]),
                "direction": "below" if bool(below[index]) else "above",
            }
        by_key[key] = {
            "raw_dtype": str(raw.dtype),
            "raw_shape": list(raw.shape),
            "raw_min": float(raw.min()),
            "raw_max": float(raw.max()),
            "declared_box_violation_count": violation_count,
            "first_declared_box_violation": first,
            "source_projection_type": projection_type,
            "source_projection_change_count": int(
                np.count_nonzero(projected != raw)
            ),
            "max_source_projection_absolute_delta": float(
                np.max(np.abs(projected - raw))
            ),
        }
    return {
        "declared_box_violation_total": box_total,
        "robosuite_continuous_saturation_total": continuous_total,
        "robocasa_binary_mapping_change_total": binary_total,
        "source_defined_endogenous_mapping_total": continuous_total + binary_total,
        "by_key": by_key,
        "adapter_action_mutation": False,
    }


def openpi_action_diagnostics(
    actions: Any, action_space: Any
) -> dict[str, Any]:
    """Measure native OpenPI excursions without changing any action value."""

    array = validate_openpi_chunk(actions)
    by_key = {
        key: np.asarray(array[:, OPENPI_SLICES[key]])
        for key in KEYS
    }
    return groot_action_diagnostics(by_key, action_space)


def merge_action_diagnostics(total: dict[str, int], current: dict[str, Any]) -> None:
    for key in (
        "declared_box_violation_total",
        "robosuite_continuous_saturation_total",
        "robocasa_binary_mapping_change_total",
        "source_defined_endogenous_mapping_total",
    ):
        total[key] = int(total.get(key, 0)) + int(current[key])


def groot_step_actions(
    actions: dict[str, np.ndarray],
) -> list[dict[str, np.ndarray]]:
    validated = validate_groot_chunk(actions)
    return [
        {key: validated[key][index] for key in KEYS}
        for index in range(16)
    ]


def openpi_step_actions(
    actions: Any, action_space: Any
) -> list[dict[str, np.ndarray]]:
    array = validate_openpi_chunk(actions)
    output: list[dict[str, np.ndarray]] = []
    for row in array[:5]:
        action: dict[str, np.ndarray] = {}
        for key in KEYS:
            subspace = action_space.spaces[key]
            value = np.asarray(row[OPENPI_SLICES[key]])
            if value.shape != subspace.shape or not np.isfinite(value).all():
                raise RuntimeError(f"OPENPI_ACTION_VALUE:{key}:{value.shape}")
            action[key] = value
        output.append(action)
    return output


class RawActionLedger:
    """Append-only, parseable action ledger flushed before environment use."""

    def __init__(self, final_path: Path) -> None:
        if final_path.exists():
            raise RuntimeError(f"WRITE_ONCE_EXISTS:{final_path}")
        self.final_path = final_path
        self.partial_path = final_path.with_suffix(
            final_path.suffix + f".partial.{os.getpid()}"
        )
        if self.partial_path.exists():
            raise RuntimeError(f"PARTIAL_EXISTS:{self.partial_path}")
        final_path.parent.mkdir(parents=True, exist_ok=True)
        self.handle: BinaryIO = self.partial_path.open("xb")
        self.handle.write(_LEDGER_MAGIC)
        self.handle.flush()
        self.frames = 0
        self.closed = False

    def append(
        self,
        *,
        call_index: int,
        observation_sha256: str,
        actions: dict[str, np.ndarray],
        diagnostics: dict[str, Any] | None,
    ) -> str:
        if self.closed:
            raise RuntimeError("LEDGER_CLOSED")
        from ipc_wire_v3b1 import pack_arrays

        action_sha = logical_array_sha256(actions)
        payload = pack_arrays(actions)
        header = canonical_json(
            {
                "frame_index": self.frames,
                "call_index": call_index,
                "observation_logical_sha256": observation_sha256,
                "action_logical_sha256": action_sha,
                "diagnostics": diagnostics,
            }
        )
        self.handle.write(_U64.pack(len(header)))
        self.handle.write(header)
        self.handle.write(_U64.pack(len(payload)))
        self.handle.write(payload)
        self.handle.flush()
        self.frames += 1
        return action_sha

    def seal(self) -> None:
        if self.closed:
            raise RuntimeError("LEDGER_ALREADY_CLOSED")
        self.handle.flush()
        os.fsync(self.handle.fileno())
        self.handle.close()
        os.replace(self.partial_path, self.final_path)
        self.closed = True

    def abort(self) -> None:
        if not self.closed:
            self.handle.flush()
            os.fsync(self.handle.fileno())
            self.handle.close()
            self.closed = True


def audit_raw_action_ledger(path: Path) -> dict[str, Any]:
    """Parse every frame and verify the embedded logical action hashes."""
    from ipc_wire_v3b1 import unpack_arrays

    digest = hashlib.sha256()
    frames = 0
    sequence: list[dict[str, Any]] = []
    with path.open("rb") as handle:
        if handle.read(len(_LEDGER_MAGIC)) != _LEDGER_MAGIC:
            raise RuntimeError(f"LEDGER_MAGIC:{path}")
        while True:
            length_bytes = handle.read(_U64.size)
            if not length_bytes:
                break
            if len(length_bytes) != _U64.size:
                raise RuntimeError(f"LEDGER_HEADER_LENGTH_TRUNCATED:{path}")
            (header_length,) = _U64.unpack(length_bytes)
            header_bytes = handle.read(header_length)
            if len(header_bytes) != header_length:
                raise RuntimeError(f"LEDGER_HEADER_TRUNCATED:{path}")
            payload_length_bytes = handle.read(_U64.size)
            if len(payload_length_bytes) != _U64.size:
                raise RuntimeError(f"LEDGER_PAYLOAD_LENGTH_TRUNCATED:{path}")
            (payload_length,) = _U64.unpack(payload_length_bytes)
            payload = handle.read(payload_length)
            if len(payload) != payload_length:
                raise RuntimeError(f"LEDGER_PAYLOAD_TRUNCATED:{path}")
            header = json.loads(header_bytes.decode("ascii"))
            if header.get("frame_index") != frames:
                raise RuntimeError(f"LEDGER_FRAME_SEQUENCE:{path}:{frames}")
            arrays = unpack_arrays(payload)
            action_sha = logical_array_sha256(arrays)
            if header.get("action_logical_sha256") != action_sha:
                raise RuntimeError(f"LEDGER_ACTION_SHA256:{path}:{frames}")
            call_index = header.get("call_index")
            if not isinstance(call_index, int) or call_index < 0:
                raise RuntimeError(f"LEDGER_CALL_INDEX:{path}:{frames}")
            digest.update(call_index.to_bytes(8, "big"))
            digest.update(bytes.fromhex(action_sha))
            sequence.append(
                {
                    "call_index": call_index,
                    "action_logical_sha256": action_sha,
                }
            )
            frames += 1
    return {
        "frames": frames,
        "action_sequence_sha256": digest.hexdigest(),
        "file_sha256": file_sha256(path),
        "sequence": sequence,
    }
