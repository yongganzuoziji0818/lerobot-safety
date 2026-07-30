# V5 ArmnetBench prospective external-validation protocol

Protocol ID: `CDSE-ARMNET-V5-RW-001`

Status: `PRE_RESULT_FREEZE_CANDIDATE`

## Research question

Does the central V4 conclusion transport to physical SO-101 rollouts: namely,
that absolute risk depends on the outcome-measurement contract while the
relative ordering of the same three policy architectures may be more stable?

V5 is an external validation, not a new simulator benchmark and not a direct
replication of the geometry/force/contact definitions C0--C5.

## Source lock

- Repository: `armnet/armnetbench_v01_robometer`
- Tag: `v1.0`
- Resolved Git commit: `a5030e049922bd89417b8aa79672c3e89e0bed6d`
- License: Apache-2.0
- Single-arm Parquet SHA-256:
  `0c249334caef8506ee4d15b5ea4d7b52ecc6afa7662010eadeff5d88d0dfc320`
- Bimanual Parquet SHA-256:
  `e147be28c0b6a06ffe54ff3f4bbe37135f749c545cbb26516d4702da3c0fd6b0`

The dataset card's public aggregate label marginals were visible during source
screening. No task-by-policy outcome table or policy-specific label
distribution was inspected before this protocol and its analysis code were
frozen.

## Units, inclusion and exclusions

- Scientific unit: one physical-robot episode, not one camera clip or frame.
- Task is the paired blocking/generalisation unit.
- Included tasks: all 12 released tasks.
- Included policies: `pi0`, `pi0.5`, and `grootn1.7`, the three architectures
  directly shared with V4R1.
- Included episodes: every labelled `v1.0` episode for those policies.
- Camera duplicates must agree exactly and are collapsed to one episode.
- Expected sample: 1,078 episodes in 36 task-policy cells. Thirty episodes are
  expected per cell except `eye_drops_to_shelf/pi0` and
  `transfer_cube/pi0.5`, which contain 29 because the source removed
  corrupted or unlabelled episodes.
- Teleoperation and the four non-overlapping policy families are excluded
  before outcomes are read.
- No episode replacement, imputation, outcome-dependent exclusion or
  rebalancing is permitted.

## Frozen outcome-contract family

The released labels are `successful`, `suboptimal`, and `failure`. Let
`lambda` denote the unobserved severity assigned to a suboptimal completion.

- `RW0_failure_only`: failure = 1; suboptimal = successful = 0.
- `RW1_half_suboptimal`: failure = 1; suboptimal = 0.5; successful = 0.
- `RW2_non_success`: failure = suboptimal = 1; successful = 0.

The partially identified policy risk is also reported for all
`lambda in [0,1]`. These are outcome-measurement contracts; they are not
physical contact-force contracts.

## Estimands

Primary policy risk is the equal-task macro-average of within-task episode
risk. Lower values are better.

Primary contrasts are all three signed policy-risk differences under all three
contracts (nine contrasts). Positive `A - B` means policy A has greater risk.
The prespecified policy order for contrast generation is:

1. `pi0`
2. `pi0.5`
3. `grootn1.7`

Secondary descriptive estimands are rollout-micro risks, embodiment-stratified
macro risks, leave-one-task-out point orders, common-lambda pairwise identified
ranges, and policy-specific-lambda pairwise identified ranges.

No V4 and V5 observations are pooled. Cross-benchmark comparison is limited to
whether the point-order pattern for the three shared architectures agrees.

## Uncertainty and multiplicity

- 50,000 two-stage paired bootstrap replicates.
- Random seed: `2026073001`.
- Each replicate samples the 12 tasks with replacement. Within every selected
  task, episodes are resampled with replacement separately inside each policy
  cell at its observed cell size.
- Nine primary pairwise contrasts use two-sided Bonferroni-adjusted percentile
  intervals with familywise alpha 0.05.
- Three `RW2 - RW0` within-policy contract widths use a separate two-sided
  Bonferroni-adjusted percentile family with alpha 0.05.
- Point-order robustness is descriptive and is true only if all three
  contracts have the identical strict order with no risk ties.
- Simultaneous separation is claimed only for a pair/contract whose adjusted
  interval excludes zero.

## Missingness and integrity

The two source-deleted episodes are treated as unavailable by design. No
missing-at-random claim is made. Results are conditional on the released,
labelled ArmnetBench corpus. Any label disagreement across the three camera
rows, unexpected vocabulary, source-hash mismatch, cell-count mismatch or
output-path pre-existence fails closed before analysis output is written.

## Execution and reporting

- L40S is the only scientific execution endpoint.
- The formal runner may write its final JSON exactly once.
- V5 does not use a GPU and must not interfere with another project's process.
- V4R1 evidence and analysis remain byte-identical.
- Regardless of direction, the complete V5 result is reported.
- Claims remain limited to released physical SO-101 benchmark rollouts; no
  deployment certification, injury prevention or hardware safety guarantee is
  implied.

