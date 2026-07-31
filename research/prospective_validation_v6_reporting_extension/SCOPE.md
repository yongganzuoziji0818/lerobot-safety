# V6 reporting extension: theory and decision consequences

## Status and purpose

This directory is an additive, post-result reporting extension. It strengthens
the mathematical account of measurement-contract uncertainty and derives the
threshold regions in which the already sealed point estimates would produce
contract-dependent decisions.

It is not a new robot experiment, a new statistical analysis, or a prospective
validation claim. The V4, V5 and V6 evidence, contracts, labels, thresholds,
seeds, bootstrap procedures, outputs and manifests remain unchanged.

## Bound inputs

- V4 aggregate analysis SHA-256:
  `7a6cc1c97baaacdc0185504ed813a2f431bd45a639e1d086789cd16973e50c5b`.
- V5 policy-contract reporting table SHA-256:
  `2f522de7173c181dad34ff7efd079821159bf915998670aad0c6126783d7c538`.
- V6 terminal manifest SHA-256:
  `858bda2ad7a6e652b717889f7d69a053bfd1e55a47369c4fcc26f0765b1bbcc6`.

## Permitted derivations

The executable derivation may only:

1. read the sealed policy-by-contract point estimates;
2. compute each policy's minimum, maximum and threshold ambiguity band;
3. compute paired-contract and arbitrary-contract point-order gaps;
4. serialize the results with the exact input hashes and claim boundary.

It may not resample, fit a model, alter a label, change a contract, select a
threshold, calculate a new confidence interval or pool domains.

## Claim boundary

The reported bands identify thresholds for which the selected executable
contract can change a decision based on the sealed point estimates. They are
not safety limits, calibrated acceptance criteria, confidence intervals,
injury probabilities or deployment recommendations. Point-set separation does
not replace the frozen simultaneous sampling intervals.
