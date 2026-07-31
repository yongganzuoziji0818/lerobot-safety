# V6 non-hardware evidence augmentation

## Purpose

V6 strengthens the RESS submission without new robot hardware. It is a separate
evidence layer and does not modify, recompute or replace any V4 or V5 artifact.

V6 has four components:

1. a formal account of measurement-contract uncertainty and robust ordering;
2. a prospective, known-ground-truth calibration of the statistical reporting
   chain on synthetic task populations;
3. a transparently post-hoc adversarial label-flip radius analysis of the
   already sealed V5 ArmnetBench source labels; and
4. a RESS-focused literature and claim-positioning audit.

The synthetic calibration is software/statistical validation only. The label
analysis is sensitivity analysis only. Neither is physical safety validation,
deployment certification, injury evidence or a substitute for author-run
hardware experiments.

## Immutable upstream evidence

- V4 formal simulation attempt and sealed analysis remain unchanged.
- V5 physical-episode analysis and its public-source bindings remain unchanged.
- The Zenodo DOI and already released archive are historical versioned evidence;
  V6 does not silently replace their contents.
- No frozen task, policy, seed, horizon, contract, threshold, bootstrap rule,
  manifest, hash or single-executor rule is changed.

## Evidence labels

- `PROSPECTIVE_SYNTHETIC_CALIBRATION`: frozen before its first execution.
- `POSTHOC_LABEL_ROBUSTNESS`: declared post hoc because V5 outcomes were known.
- `FORMAL_DERIVATION`: mathematical consequence of stated definitions.
- `PROTOCOL_ONLY`: blind human re-labelling plan; no human result is claimed.

