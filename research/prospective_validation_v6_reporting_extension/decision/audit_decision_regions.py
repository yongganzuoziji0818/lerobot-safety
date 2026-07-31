#!/usr/bin/env python3
"""Independent structural and arithmetic audit of the reporting extension."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


EXPECTED_RESULT_SHA256 = "2e1e2a71e4f59b51d33a64559c17ce3d245874b5c3e54b58099fef3c47a5942c"
EXPECTED_PREFREEZE_MANIFEST_SHA256 = "942a4c9485e5760ec6f6855835c505ed83749bbac42948eb4a775c905b867b7e"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    result_path = root / "results" / "DECISION_CONSEQUENCE_MAP.json"
    prefreeze_path = root / "REPORTING_EXTENSION_PREFREEZE_MANIFEST.sha256"
    assert sha256(result_path) == EXPECTED_RESULT_SHA256
    assert sha256(prefreeze_path) == EXPECTED_PREFREEZE_MANIFEST_SHA256

    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["status"] == "PASS_DETERMINISTIC_POSTHOC_REPORTING_EXTENSION"
    assert payload["no_resampling_or_model_fitting"] is True
    assert payload["no_domain_pooling"] is True
    assert len(payload["domains"]) == 2

    for domain in payload["domains"]:
        assert len(domain["decision_regions"]) == 3
        assert len(domain["adjacent_order_edges"]) == 2
        for row in domain["decision_regions"]:
            lower, upper = row["threshold_ambiguity_band"]
            assert lower == row["minimum_point_risk"]
            assert upper == row["maximum_point_risk"]
            assert abs((upper - lower) - row["band_width"]) < 1e-15
            assert row["band_left_closed_right_open"] is True
        for edge in domain["adjacent_order_edges"]:
            assert edge["point_order_robust_paired_contract"] is True
            assert edge["point_order_robust_arbitrary_contract"] is True
            assert edge["paired_contract_minimum_gap"] > 0
            assert edge["arbitrary_contract_minimum_gap"] > 0
            assert edge["sampling_separation_not_inferred"] is True

    print("PASS_REPORTING_EXTENSION_INDEPENDENT_AUDIT")


if __name__ == "__main__":
    main()
