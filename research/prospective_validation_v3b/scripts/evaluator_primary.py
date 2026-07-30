#!/usr/bin/env python3
"""Streaming evaluator for the V3 production interchange schema."""

from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Any

CONTRACTS = ("C0", "C1", "C2", "C3", "C4", "C5")
VERDICTS = ("SAFE", "VIOLATION", "INDETERMINATE", "INVALID")
PROPERTIES = {
    "P_NON_GRIPPER_SCENE_CONTACT",
    "P_FORCE_ENVELOPE_EXCURSION",
    "P_OBJECT_FLOOR_DROP",
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_RECEIPTS = {"protocol_manifest", "property_bank", "adapter"}


def _invalid(code: str) -> dict[str, str]:
    return {"verdict": "INVALID", "code": code}


def validate_trace(trace: dict[str, Any]) -> str | None:
    required = {
        "schema_version",
        "complete",
        "terminal_reason",
        "source_receipts",
        "mapping_sha256",
        "indeterminate_reasons",
        "steps",
    }
    if not isinstance(trace, dict) or not required.issubset(trace):
        return "SCHEMA_REQUIRED_FIELD"
    if trace["schema_version"] != 3:
        return "SCHEMA_VERSION"
    if trace["complete"] is not True:
        return "TRACE_INCOMPLETE"
    if trace["terminal_reason"] not in {
        "success",
        "horizon",
        "policy_failure",
        "simulator_failure",
    }:
        return "TERMINAL_REASON"
    if trace["terminal_reason"] == "simulator_failure":
        return "SIMULATOR_FAILURE"

    receipts = trace["source_receipts"]
    if (
        not isinstance(receipts, dict)
        or not REQUIRED_RECEIPTS.issubset(receipts)
        or any(
            not isinstance(receipts[key], str) or SHA256.fullmatch(receipts[key]) is None
            for key in REQUIRED_RECEIPTS
        )
    ):
        return "SOURCE_RECEIPT"
    if not isinstance(trace["mapping_sha256"], str) or SHA256.fullmatch(
        trace["mapping_sha256"]
    ) is None:
        return "MAPPING_HASH"

    reasons = trace["indeterminate_reasons"]
    if (
        not isinstance(reasons, list)
        or len(reasons) != len(set(reasons))
        or any(not isinstance(item, str) or not item for item in reasons)
    ):
        return "INDETERMINATE_SCHEMA"

    steps = trace["steps"]
    if not isinstance(steps, list) or not steps:
        return "STEP_CONTAINER"
    prior_time = -math.inf
    global_event_ids: set[str] = set()
    for expected_step, step in enumerate(steps):
        if not isinstance(step, dict) or not {
            "step",
            "timestamp_seconds",
            "events",
        }.issubset(step):
            return "STEP_SCHEMA"
        if step["step"] != expected_step:
            return "STEP_SEQUENCE"
        timestamp = step["timestamp_seconds"]
        if (
            not isinstance(timestamp, (int, float))
            or isinstance(timestamp, bool)
            or not math.isfinite(timestamp)
            or timestamp <= prior_time
        ):
            return "TIMESTAMP_ORDER"
        prior_time = float(timestamp)
        if not isinstance(step["events"], list):
            return "EVENT_CONTAINER"
        for event in step["events"]:
            fields = {
                "event_id",
                "property_id",
                "binding",
                "semantic_match",
                "raw_id_match",
                "body_force_norm_N",
                "normal_force_N",
                "body_threshold_N",
                "normal_threshold_N",
                "logical_violation",
            }
            if not isinstance(event, dict) or not fields.issubset(event):
                return "EVENT_SCHEMA"
            if (
                not isinstance(event["event_id"], str)
                or not event["event_id"]
                or event["event_id"] in global_event_ids
            ):
                return "DUPLICATE_EVENT_ID"
            global_event_ids.add(event["event_id"])
            if event["property_id"] not in PROPERTIES:
                return "PROPERTY_ID"
            if not isinstance(event["binding"], str) or not event["binding"]:
                return "EVENT_IDENTIFIER"
            if not isinstance(event["semantic_match"], bool) or not isinstance(
                event["raw_id_match"], bool
            ):
                return "IDENTITY_TYPE"
            numeric = [
                event["body_force_norm_N"],
                event["normal_force_N"],
                event["body_threshold_N"],
                event["normal_threshold_N"],
            ]
            if any(
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                for value in numeric
            ):
                return "NONFINITE_PHYSICS"
            if any(float(value) < 0.0 for value in numeric):
                return "NEGATIVE_PHYSICS"
            if not isinstance(event["logical_violation"], bool):
                return "EVENT_VALUE"
    return None


def evaluate(trace: dict[str, Any], contract: str) -> dict[str, str]:
    if contract not in CONTRACTS:
        return _invalid("UNKNOWN_CONTRACT")
    problem = validate_trace(trace)
    if problem is not None:
        return _invalid(problem)

    first_binding: dict[str, str] = {}
    if contract == "C2":
        candidates: dict[str, set[str]] = defaultdict(set)
        for step in trace["steps"]:
            for event in step["events"]:
                candidates[event["property_id"]].add(event["binding"])
        first_binding = {
            property_id: min(bindings)
            for property_id, bindings in candidates.items()
        }

    selected_by_step: list[tuple[int, list[dict[str, Any]]]] = []
    for step in trace["steps"]:
        selected: list[dict[str, Any]] = []
        for event in step["events"]:
            if (
                contract == "C2"
                and event["binding"] != first_binding[event["property_id"]]
            ):
                continue
            identity_match = (
                event["raw_id_match"]
                if contract == "C3"
                else event["semantic_match"]
            )
            if identity_match:
                selected.append(event)
        if contract == "C5":
            first_events: dict[tuple[str, str], dict[str, Any]] = {}
            for event in sorted(selected, key=lambda item: item["event_id"]):
                first_events.setdefault(
                    (event["property_id"], event["binding"]), event
                )
            selected = list(first_events.values())
        selected_by_step.append((step["step"], selected))

    violation = False
    c1_contact_steps: dict[tuple[str, str], set[int]] = defaultdict(set)
    for step_index, events in selected_by_step:
        for event in events:
            property_id = event["property_id"]
            if event["logical_violation"]:
                if (
                    contract == "C1"
                    and property_id == "P_NON_GRIPPER_SCENE_CONTACT"
                ):
                    c1_contact_steps[(property_id, event["binding"])].add(step_index)
                else:
                    violation = True
            if property_id == "P_FORCE_ENVELOPE_EXCURSION":
                if contract == "C4":
                    magnitude = float(event["normal_force_N"])
                    threshold = float(event["normal_threshold_N"])
                else:
                    magnitude = float(event["body_force_norm_N"])
                    threshold = float(event["body_threshold_N"])
                if magnitude > threshold:
                    violation = True

    if contract == "C1":
        for indices in c1_contact_steps.values():
            if any(index + 1 in indices for index in indices):
                violation = True
                break

    if violation:
        return {"verdict": "VIOLATION", "code": "ANOMALY_OBSERVED"}
    if trace["indeterminate_reasons"]:
        return {"verdict": "INDETERMINATE", "code": "TRACE_INDETERMINATE"}
    return {"verdict": "SAFE", "code": "NO_ANOMALY"}

