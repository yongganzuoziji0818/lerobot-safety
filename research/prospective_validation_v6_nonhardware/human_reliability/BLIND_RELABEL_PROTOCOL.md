# Blind re-labelling protocol (protocol only)

Status: `NOT_EXECUTED_NO_INDEPENDENT_HUMAN_RATERS`

If two independent raters become available, a deterministic SHA-256 ranking of
episode identifiers will select 120 episodes, stratified equally across the 12
tasks and as evenly as possible across the three policies. Before rating, policy
identity and the released `quality_label` will be hidden. Raters will assign
`successful`, `suboptimal`, `failure` or `unrateable` from the source episode
media using a written codebook and record one reason code.

The preregistered outputs will be raw agreement, quadratic-weighted Cohen's
kappa on the ordered three-level scale, category-specific agreement and a
four-way confusion table against the released label. Disagreements will not be
adjudicated for the primary reliability estimate. Any later adjudication will be
reported separately.

No rater data currently exist. This document must not be cited as completed
validation.

