# V5 prospective real-world external validation

Status: SOURCE_AND_SCHEMA_SCREENING_ONLY

## Purpose

V5 is a new, independent validation namespace intended to test whether the
paper's measurement-uncertainty conclusion and architecture-ordering evidence
transport to publicly released physical-robot rollouts. It does not replace,
modify, recompute or pool with V4R1.

## Immutable predecessor

The following V4R1 items remain immutable:

- 50 RoboCasa tasks, three policies, eight paired seeds and 900 steps;
- C0--C5 definitions, thresholds, estimands and analysis rules;
- all formal trajectories, success/failure evidence and manifests;
- `analysis_results/V4R1-A1-ANALYSIS-001.json`, SHA-256
  `7a6cc1c97baaacdc0185504ed813a2f431bd45a639e1d086789cd16973e50c5b`.

## Candidate external source

- Dataset: ArmnetBench v0.1 RoboMeter release
- Robot: physical SO-101 and bimanual SO-101
- Source: https://huggingface.co/datasets/armnet/armnetbench_v01_robometer
- Prospective source revision: tag `v1.0`
- Resolved tag commit:
  `a5030e049922bd89417b8aa79672c3e89e0bed6d`
- License reported by the source: Apache-2.0

The source reports 12 tasks, seven learned policy families, 2,518 core policy
rollouts and three-level human outcome labels. Source and schema inspection is
permitted before freeze; scientific outcome analysis is not.

## Claim boundary

Public real-robot data can materially reduce the simulation-only limitation,
but it cannot certify deployment safety or reproduce the simulator-specific
force/contact contracts. V5 will therefore use an observable outcome-contract
family defined solely from the released three-level labels. Its real-world
estimands will be reported separately from V4R1 and will not be described as
direct replication of C0--C5.

## Next gates

1. Verify the tagged source contents, episode identity, core/extra-run
   distinction, task-policy coverage, label vocabulary and licensing.
2. Freeze the inclusion set, outcome-contract mappings, estimands, simultaneous
   intervals, bootstrap/randomization seeds, missing-data rules and code hashes
   before computing any policy outcome.
3. Run exactly one frozen analysis attempt.

