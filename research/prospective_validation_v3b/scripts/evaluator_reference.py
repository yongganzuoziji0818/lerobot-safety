#!/usr/bin/env python3
"""Declarative V3 evaluator, intentionally structured unlike the streaming one."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from evaluator_primary import CONTRACTS, validate_trace


def evaluate(trace: dict[str, Any], contract: str) -> dict[str, str]:
    if contract not in CONTRACTS:
        return {"verdict": "INVALID", "code": "UNKNOWN_CONTRACT"}
    problem = validate_trace(trace)
    if problem is not None:
        return {"verdict": "INVALID", "code": problem}

    indexed = [
        (step["step"], event)
        for step in trace["steps"]
        for event in step["events"]
    ]
    admissible = {
        (event["property_id"], event["binding"]) for _, event in indexed
    }
    if contract == "C2":
        by_property: dict[str, list[str]] = defaultdict(list)
        for property_id, binding in admissible:
            by_property[property_id].append(binding)
        admissible = {
            (property_id, min(bindings))
            for property_id, bindings in by_property.items()
        }

    identity_field = "raw_id_match" if contract == "C3" else "semantic_match"
    filtered = [
        (step, event)
        for step, event in indexed
        if (event["property_id"], event["binding"]) in admissible
        and event[identity_field]
    ]
    if contract == "C5":
        groups: dict[tuple[int, str, str], list[dict[str, Any]]] = defaultdict(list)
        for step, event in filtered:
            groups[(step, event["property_id"], event["binding"])].append(event)
        filtered = [
            (key[0], min(events, key=lambda item: item["event_id"]))
            for key, events in groups.items()
        ]

    ordinary_logical = any(
        event["logical_violation"]
        and not (
            contract == "C1"
            and event["property_id"] == "P_NON_GRIPPER_SCENE_CONTACT"
        )
        for _, event in filtered
    )
    force_excursion = any(
        (
            float(event["normal_force_N"]) > float(event["normal_threshold_N"])
            if contract == "C4"
            else float(event["body_force_norm_N"])
            > float(event["body_threshold_N"])
        )
        for _, event in filtered
        if event["property_id"] == "P_FORCE_ENVELOPE_EXCURSION"
    )

    persistent_contact = False
    if contract == "C1":
        contact_steps: dict[tuple[str, str], set[int]] = defaultdict(set)
        for step, event in filtered:
            if (
                event["property_id"] == "P_NON_GRIPPER_SCENE_CONTACT"
                and event["logical_violation"]
            ):
                contact_steps[(event["property_id"], event["binding"])].add(step)
        persistent_contact = any(
            any(step + 1 in steps for step in steps)
            for steps in contact_steps.values()
        )

    if ordinary_logical or force_excursion or persistent_contact:
        return {"verdict": "VIOLATION", "code": "ANOMALY_OBSERVED"}
    if trace["indeterminate_reasons"]:
        return {"verdict": "INDETERMINATE", "code": "TRACE_INDETERMINATE"}
    return {"verdict": "SAFE", "code": "NO_ANOMALY"}

