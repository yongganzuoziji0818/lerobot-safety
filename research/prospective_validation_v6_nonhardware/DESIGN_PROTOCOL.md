# V6 non-hardware design protocol

Status before execution: `DESIGN_COMPLETE_NOT_YET_EXECUTED`

## 1. Prospective synthetic calibration

The calibration uses a known finite oracle population with three strata, 128
task types per stratum, three policies, six contracts and eight paired Bernoulli
replicates per sampled task. Each Monte Carlo data set samples 16 task types per
stratum with replacement. Common uniforms are used across contracts within a
task-policy-seed tuple so that contract comparisons remain paired.

Two scenarios are fixed:

- `stable`: cardinal risks differ across contracts, but the strict policy order
  is identical under all six contracts;
- `reversal`: at least one policy-pair order changes across contracts.

The oracle probabilities are deterministic functions coded in
`synthetic/oracle_calibration.py`. The true task-population means are obtained by
enumerating all 384 task types. Random seeds, repeats and gates are:

- generation seed: `2026080101`;
- bootstrap seed stream: derived only from the generation RNG;
- point/ranking Monte Carlo repeats: 500;
- simultaneous-coverage outer repeats: 200;
- stratified task bootstrap replicates per outer repeat: 1,000;
- maximum absolute mean bias across the 18 stable-scenario rates: 0.01;
- stable/reversal classification accuracy: at least 0.80 in each scenario;
- empirical simultaneous 95% coverage across all 18 rates: [0.90, 1.00].

The simultaneous interval uses the 95th percentile of the maximum absolute
centered task-bootstrap deviation, matching the V4 familywise construction at
the rate-family level. The calibration does not tune any V4/V5 estimator or
reanalyse empirical outcomes.

## 2. Post-hoc adversarial label-flip radius

The source is the same hash-bound V5 ArmnetBench episode table. The analysis
retains the 12-task equal-weight macro estimand and the three outcome contracts:
RW0=(0,0,1), RW1=(0,0.5,1), RW2=(0,1,1) for successful, suboptimal and failure.

For each of the three policy pairs and each contract, the script computes the
smallest number of individual episode labels that an adversary must change to
reach a tie and to produce a strict point-order reversal. A label may be changed
to either of the other two registered categories. Cell denominators and all
other labels remain fixed. The exact scalar solution sorts all admissible
single-episode changes by their signed effect on the task-macro contrast.

For simultaneous reversal under RW0-RW2, the exact search is restricted to
successful<->failure flips. These have identical signed effects under all three
contracts and weakly dominate any same-episode alternative in every contract.
The script verifies that enough such candidates exist; otherwise it fails
closed rather than reporting an approximate radius.

Outputs report absolute flip counts and fractions of all 1,078 episodes. No
probabilistic label-error model, inter-rater reliability or corrected empirical
risk is inferred.

## 3. Blind re-labelling protocol only

If independent human raters later become available, a random hash-selected
episode sample will be scored blind to policy and original quality label using a
predefined codebook. Until then, V6 reports this only as future validation. No
synthetic rater or language model is treated as a human reliability estimate.

## 4. Reporting rules

- All V6 results are additive supplementary evidence.
- The manuscript must retain the V4/V5 numerical results and limitations.
- Synthetic PASS means the reporting code recovers known oracle properties; it
  is not empirical confirmation of robot safety.
- Label-flip radii are robustness thresholds, not estimates of actual label
  error.
- Any failed gate is retained and reported; it is not silently rerun.

