from pathlib import Path

import numpy as np

import v5_analysis as v5


def test_contract_ordering():
    labels = np.asarray(["successful", "suboptimal", "failure"])
    expected = {
        "RW0_failure_only": [0.0, 0.0, 1.0],
        "RW1_half_suboptimal": [0.0, 0.5, 1.0],
        "RW2_non_success": [0.0, 1.0, 1.0],
    }
    for contract, mapping in v5.CONTRACTS.items():
        assert [mapping[str(label)] for label in labels] == expected[contract]


def test_adjusted_percentile_is_ordered():
    low, high = v5.adjusted_percentile_interval(
        np.arange(10_000, dtype=float), family_size=9
    )
    assert low < high


def test_write_once(tmp_path: Path):
    target = tmp_path / "result.json"
    v5.write_once_json(target, {"ok": True})
    try:
        v5.write_once_json(target, {"ok": False})
    except FileExistsError:
        pass
    else:
        raise AssertionError("write-once guard did not fail closed")

