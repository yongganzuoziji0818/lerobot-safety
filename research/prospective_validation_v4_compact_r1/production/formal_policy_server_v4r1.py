#!/usr/bin/env python3
"""Policy-side server for one V3-B2 policy-task shard."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import random
import socket
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path("/workspace/lerobot-safety")
V3B1_REMOTE = ROOT / "research" / "prospective_validation_v3b1" / "remote"
V4R1 = ROOT / "research" / "prospective_validation_v4_compact_r1"
PRODUCTION = V4R1 / "production"
sys.path.insert(0, str(V3B1_REMOTE))
sys.path.insert(0, str(PRODUCTION))

from ipc_wire_v3b1 import receive_message, send_message  # noqa: E402
from production_common_v4r1 import (  # noqa: E402
    file_sha256,
    logical_array_sha256,
    raw_observation,
    validate_groot_chunk,
    validate_openpi_chunk,
    write_json_once,
)

MASTER_SEED = 42
POLICIES = ("pi0", "pi05", "groot")
OPENPI = {
    "pi0": (
        "pi0_robocasa_pretrain_human300",
        ROOT
        / "data/prospective_validation_v2/checkpoints/pi0/"
        "pi0_robocasa_pretrain_human300/multitask_learning/75000",
    ),
    "pi05": (
        "pi05_pretrain_human300",
        ROOT
        / "data/prospective_validation_v2/checkpoints/pi05_pretrain_human300/"
        "multitask_learning/75000",
    ),
}
GROOT_CHECKPOINT = (
    ROOT
    / "data/prospective_validation_v2/checkpoints/gr00t_n1-5/"
    "multitask_learning/checkpoint-120000"
)
FREEZE_MANIFEST = V4R1 / "V4R1_PRODUCTION_FREEZE_MANIFEST.sha256"
FORMAL_RECEIPT = V4R1 / "governance" / "FORMAL_EXECUTION_RECEIPT.json"


def validate_formal_authorization(attempt_id: str) -> dict[str, Any]:
    if not FREEZE_MANIFEST.is_file() or not FORMAL_RECEIPT.is_file():
        raise RuntimeError("FORMAL_FREEZE_OR_RECEIPT_MISSING")
    receipt = json.loads(FORMAL_RECEIPT.read_text(encoding="utf-8"))
    if (
        receipt.get("status") != "AUTHORIZED_V4R1_FORMAL_EXECUTION"
        or receipt.get("formal_execution_allowed") is not True
        or receipt.get("formal_attempt_id") != attempt_id
        or receipt.get("production_freeze_manifest_sha256")
        != file_sha256(FREEZE_MANIFEST)
        or receipt.get("planned_formal_scientific_trajectories") != 1200
        or receipt.get("seeds_per_policy_task") != 8
        or receipt.get("environment_steps_per_trajectory") != 900
        or receipt.get("executor") != "L40S_ONLY_SINGLE_EXECUTOR"
    ):
        raise RuntimeError("INVALID_FORMAL_EXECUTION_RECEIPT")
    return receipt


def prepare_openpi_observation(observation: dict[str, np.ndarray]) -> dict[str, Any]:
    from openpi_client import image_tools

    images: dict[str, np.ndarray] = {}
    for source, target in (
        ("video.robot0_agentview_left", "observation/image"),
        ("video.robot0_eye_in_hand", "observation/wrist_image"),
        ("video.robot0_agentview_right", "observation/right_image"),
    ):
        images[target] = image_tools.convert_to_uint8(
            image_tools.resize_with_pad(
                np.ascontiguousarray(observation[source]), 224, 224
            )
        )
    state = np.concatenate(
        (
            observation["state.end_effector_position_relative"],
            observation["state.end_effector_rotation_relative"],
            observation["state.base_position"],
            observation["state.base_rotation"],
            observation["state.gripper_qpos"],
        )
    )
    return {
        **images,
        "observation/state": state,
        "prompt": str(
            observation["annotation.human.task_description"].reshape(-1)[0]
        ),
    }


def load_openpi(policy_name: str) -> Any:
    from openpi.policies import policy_config
    from openpi.training import config

    config_name, checkpoint = OPENPI[policy_name]
    train_config = config.get_config(config_name)
    inference_config = dataclasses.replace(
        train_config,
        data=dataclasses.replace(train_config.data, data_dirs=None),
    )
    np.random.seed(MASTER_SEED)
    return policy_config.create_trained_policy(inference_config, checkpoint)


def set_groot_action_seed(call_index: int) -> int:
    import torch

    seed = MASTER_SEED + call_index
    os.environ.setdefault("PYTHONHASHSEED", str(MASTER_SEED))
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.use_deterministic_algorithms(True, warn_only=True)
    return seed


def load_groot() -> Any:
    from gr00t.experiment.data_config import DATA_CONFIG_MAP
    from gr00t.model.policy import Gr00tPolicy

    data = DATA_CONFIG_MAP["panda_omron"]
    set_groot_action_seed(0)
    return Gr00tPolicy(
        model_path=str(GROOT_CHECKPOINT),
        modality_config=data.modality_config(),
        modality_transform=data.transform(),
        embodiment_tag="new_embodiment",
        denoising_steps=4,
    )


def infer(
    policy_name: str,
    mode: str,
    policy: Any,
    observation: dict[str, np.ndarray],
    call_index: int,
) -> tuple[dict[str, np.ndarray], int | None]:
    if policy_name in OPENPI:
        if mode == "zero":
            return {"actions": np.zeros((5, 12), dtype=np.float32)}, None
        result = policy.infer(prepare_openpi_observation(observation))
        return {"actions": validate_openpi_chunk(result["actions"])}, None
    if mode == "zero":
        return {
            key: np.zeros(shape, dtype=np.float32)
            for key, shape in {
                "action.end_effector_position": (16, 3),
                "action.end_effector_rotation": (16, 3),
                "action.gripper_close": (16, 1),
                "action.base_motion": (16, 4),
                "action.control_mode": (16, 1),
            }.items()
        }, MASTER_SEED + call_index
    seed = set_groot_action_seed(call_index)
    prepared = {
        key: np.expand_dims(np.asarray(value), axis=0)
        for key, value in observation.items()
    }
    return validate_groot_chunk(policy.get_action(prepared)), seed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", choices=POLICIES, required=True)
    parser.add_argument("--mode", choices=("zero", "learned"), required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--task-ordinal", type=int, required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    token_hex = os.environ.get("V4R1_IPC_TOKEN", "")
    if len(token_hex) != 64:
        raise RuntimeError("V4R1_IPC_TOKEN_REQUIRED")
    token = bytes.fromhex(token_hex)
    args.output.mkdir(parents=True, exist_ok=True)
    ready_path = args.output / "server_ready.json"
    receipt_path = args.output / "server_receipt.json"
    failure_path = args.output / "server_failure.json"
    for path in (ready_path, receipt_path, failure_path):
        if path.exists():
            raise RuntimeError(f"TERMINAL_SERVER_ARTIFACT_EXISTS:{path}")

    started = datetime.now().astimezone().isoformat()
    call_index = 0
    action_digest = hashlib.sha256()
    learned_calls = 0
    last_seed: int | None = None
    formal_receipt_sha256 = None
    try:
        if args.mode == "learned":
            validate_formal_authorization(args.attempt_id)
            formal_receipt_sha256 = file_sha256(FORMAL_RECEIPT)
            policy = (
                load_openpi(args.policy)
                if args.policy in OPENPI
                else load_groot()
            )
        else:
            policy = None

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", args.port))
            listener.listen(1)
            write_json_once(
                ready_path,
                {
                    "schema_version": 1,
                    "status": "READY",
                    "attempt_id": args.attempt_id,
                    "task": args.task,
                    "task_ordinal": args.task_ordinal,
                    "policy": args.policy,
                    "mode": args.mode,
                    "address": "127.0.0.1",
                    "port": args.port,
                    "pid": os.getpid(),
                    "policy_loaded": policy is not None,
                    "formal_execution_allowed": args.mode == "learned",
                    "timestamp": datetime.now().astimezone().isoformat(),
                },
            )
            connection, peer = listener.accept()
            with connection:
                connection.settimeout(600)
                if peer[0] != "127.0.0.1":
                    raise RuntimeError(f"NON_LOOPBACK_PEER:{peer[0]}")
                while True:
                    header, arrays = receive_message(connection, token)
                    if (
                        header.get("attempt_id") != args.attempt_id
                        or header.get("task") != args.task
                        or header.get("task_ordinal") != args.task_ordinal
                        or header.get("policy") != args.policy
                    ):
                        raise RuntimeError("IPC_REQUEST_IDENTITY")
                    if header.get("op") == "shutdown":
                        if arrays:
                            raise RuntimeError("SHUTDOWN_ARRAY_PAYLOAD")
                        if (
                            header.get("mode") != args.mode
                            or header.get("call_count") != call_index
                        ):
                            raise RuntimeError("SHUTDOWN_CALL_COUNT")
                        if (
                            header.get("action_sequence_sha256")
                            != action_digest.hexdigest()
                        ):
                            raise RuntimeError("SHUTDOWN_ACTION_SEQUENCE_SHA256")
                        send_message(
                            connection,
                            token,
                            {
                                "op": "shutdown_ack",
                                "attempt_id": args.attempt_id,
                                "task": args.task,
                                "task_ordinal": args.task_ordinal,
                                "policy": args.policy,
                                "mode": args.mode,
                                "call_count": call_index,
                                "action_sequence_sha256": action_digest.hexdigest(),
                            },
                        )
                        break
                    if (
                        header.get("op") != "infer"
                        or header.get("mode") != args.mode
                        or header.get("call_index") != call_index
                        or header.get("observation_logical_sha256")
                        != logical_array_sha256(arrays)
                    ):
                        raise RuntimeError("INFER_REQUEST_SEQUENCE_OR_HASH")
                    observation = raw_observation(arrays)
                    actions, last_seed = infer(
                        args.policy, args.mode, policy, observation, call_index
                    )
                    action_sha = logical_array_sha256(actions)
                    action_digest.update(call_index.to_bytes(8, "big"))
                    action_digest.update(bytes.fromhex(action_sha))
                    send_message(
                        connection,
                        token,
                        {
                            "op": "raw_actions",
                            "attempt_id": args.attempt_id,
                            "task": args.task,
                            "task_ordinal": args.task_ordinal,
                            "policy": args.policy,
                            "mode": args.mode,
                            "call_index": call_index,
                            "policy_seed": last_seed,
                            "observation_logical_sha256": logical_array_sha256(
                                observation
                            ),
                            "action_logical_sha256": action_sha,
                        },
                        actions,
                    )
                    call_index += 1
                    if args.mode == "learned":
                        learned_calls += 1

        write_json_once(
            receipt_path,
            {
                "schema_version": 1,
                "status": "PASS_V4R1_POLICY_TASK_SERVER",
                "attempt_id": args.attempt_id,
                "task": args.task,
                "task_ordinal": args.task_ordinal,
                "policy": args.policy,
                "mode": args.mode,
                "started_at": started,
                "finished_at": datetime.now().astimezone().isoformat(),
                "bind_address": "127.0.0.1",
                "port": args.port,
                "master_seed": MASTER_SEED,
                "policy_seed_rule": (
                    "upstream_openpi_default_jax_key_with_numpy_seed_42"
                    if args.policy in OPENPI
                    else "upstream_groot_per_action_seed_42_plus_call_index"
                ),
                "last_policy_seed": last_seed,
                "action_call_count": call_index,
                "action_sequence_sha256": action_digest.hexdigest(),
                "learned_policy_calls": learned_calls,
                "formal_execution_receipt_sha256": formal_receipt_sha256,
                "formal_scientific_trajectories": 0,
            },
        )
        print("PASS_V4R1_POLICY_TASK_SERVER", flush=True)
    except BaseException as exc:
        if not failure_path.exists():
            write_json_once(
                failure_path,
                {
                    "schema_version": 1,
                    "status": "FAIL_V4R1_POLICY_TASK_SERVER_TERMINAL",
                    "attempt_id": args.attempt_id,
                    "task": args.task,
                    "task_ordinal": args.task_ordinal,
                    "policy": args.policy,
                    "mode": args.mode,
                    "timestamp": datetime.now().astimezone().isoformat(),
                    "exception_type": type(exc).__name__,
                    "exception": str(exc),
                    "action_call_count": call_index,
                    "learned_policy_calls": learned_calls,
                    "formal_scientific_trajectories": 0,
                    "automatic_retry_allowed": False,
                },
            )
        raise


if __name__ == "__main__":
    main()
