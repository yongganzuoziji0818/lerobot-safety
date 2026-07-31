from pathlib import Path
import importlib.util


ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_oracle_scenarios_have_declared_truth_classes():
    module = load("oracle_calibration", ROOT / "synthetic" / "oracle_calibration.py")
    stable = module.truth_summary(module.oracle_probabilities("stable"))
    reversal = module.truth_summary(module.oracle_probabilities("reversal"))
    assert stable["identical_strict_order"] is True
    assert reversal["identical_strict_order"] is False


def test_scalar_crossing_is_minimal():
    module = load("label_flip_radius", ROOT / "robustness" / "label_flip_radius.py")
    tie, strict = module.crossing_counts(3.0, [-1.0, -1.0, -1.0, -1.0])
    assert tie == 3
    assert strict == 4


def test_joint_crossing_is_minimal():
    module = load("label_flip_radius_joint", ROOT / "robustness" / "label_flip_radius.py")
    tie, strict = module.joint_crossing([2.0, 3.0, 2.5], [-1.0, -1.0, -1.0, -1.0])
    assert tie == 3
    assert strict == 4
