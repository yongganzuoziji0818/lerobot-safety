# LeRobot Safety

Code-only public release for executable safety-measurement contracts,
prospective robot-policy evaluation in RoboCasa, and external validation with
independently collected physical SO-101 outcome data.

This repository accompanies the study:

> **Measurement-contract uncertainty in learning-enabled robot safety
> assessment: a prospective RoboCasa study with cross-benchmark evidence**

## Public scope

The repository contains only research code and the non-result configuration
needed to inspect the implementation:

- six executable measurement contracts and two independent evaluators;
- semantic-role compilation and trace adaptation;
- fixed-exposure policy/simulator process separation over authenticated
  loopback IPC;
- V4-Compact-R1 production, audit and sealing code;
- result-blind design-assurance simulation;
- frozen estimator and partial-identification implementation;
- result-independent unit and engineering tests;
- frozen task list, property bank, schemas and design configuration.
- the prospectively frozen V5 ArmnetBench protocol, estimator and
  result-independent tests for physical SO-101 outcome labels.
- the prospectively frozen V6 synthetic-oracle calibration, exact aggregate
  label-flip sensitivity code and result-independent validation tests;
- a deterministic reporting extension for contract-identified risk hulls,
  robust point ordering and accept/reject/defer decision regions.

It deliberately excludes:

- manuscript and submission files;
- aggregate or raw scientific results;
- trajectories, figures and reporting tables;
- remote receipts, authorizations and server snapshots;
- model weights and third-party source distributions;
- credentials, server addresses and submission-only personal information.

See `CODE_RELEASE_SCOPE.md` and `CODE_SOURCE_MANIFEST.sha256`.

## Layout

```text
research/
  prospective_validation_v3b/
    benchmark/       # frozen 50-task list and benchmark lock
    contracts/       # C0–C5 contract definitions
    property_bank/   # properties, applicability and trace schema
    scripts/         # evaluators, role compiler and trace adapter
  prospective_validation_v3b1/
    remote/          # authenticated loopback message framing
  prospective_validation_v4_compact/
    design/          # predecessor compact protocol
  prospective_validation_v4_compact_r1/
    analysis/        # frozen estimators and evidence-building code
    design/          # prospective V4R1 design
    production/      # initial production implementation
    production_e1/   # engineering-successor implementation
    simulation/      # result-blind design-assurance simulation
    tests*/          # result-independent and engineering tests
  prospective_validation_v5_realworld/
    design/          # source lock and prospective external-validation protocol
    analysis/        # three-contract estimator and paired-task bootstrap
    tests/           # result-independent V5 tests and test receipt
  prospective_validation_v6_nonhardware/
    synthetic/       # prospective known-truth calibration generator
    robustness/      # exact aggregate adversarial label-flip radii
    theory/          # finite measurement-contract formalization
    tests/           # result-independent V6 checks
  prospective_validation_v6_reporting_extension/
    theory/          # identified-risk and decision-region propositions
    decision/        # deterministic extraction and independent audit source
scripts/
  verify_code_release.py
  build_code_manifest.py
```

## Local code verification

Python 3.11 or newer is recommended.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-analysis.txt
python scripts/verify_code_release.py
python research/prospective_validation_v4_compact_r1/tests/test_analysis_v4r1.py
python -m pytest -q \
  research/prospective_validation_v5_realworld/tests/test_v5_analysis.py
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1`.

The V4 unit test uses a synthetic 7,200-row census. The V5 tests use only
synthetic in-memory labels and a temporary write-once file. Neither test reads
or reproduces study results.

## Full simulator execution

The frozen production scripts expect the repository at
`/workspace/lerobot-safety`. Full execution additionally requires compatible
RoboCasa/RoboSuite, OpenPI and GR00T environments, official benchmark assets,
policy weights, and a separately controlled execution receipt. These
third-party or governance-controlled components are not included.

The V5 analysis concerns released outcome labels from physical SO-101
rollouts. The code does not claim contact-force validation, injury prevention,
deployment reliability or architecture-level causality.

The V6 and reporting-extension sources add no robot execution. The synthetic
calibration is a known-truth software/statistical check, the label-flip radii
are aggregate worst-case sensitivities rather than estimates of labelling
error, and the decision bands are point-set identification results rather than
confidence intervals or deployment thresholds.

## Citation and license

Use `CITATION.cff` when citing the software. Original code is released under
the MIT License. Third-party dependencies retain their own licenses.
