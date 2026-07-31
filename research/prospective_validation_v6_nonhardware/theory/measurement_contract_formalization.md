# Formalization of measurement-contract uncertainty

Let \(\Pi\) be a finite set of policies, \(\mathcal C\) a finite set of
admissible executable measurement contracts and \(X_\pi\) the trace generated
by policy \(\pi\) under a fixed exposure design. A contract
\(c\in\mathcal C\) maps a trace to a verdict \(Y_c(X_\pi)\in\{0,1,?\}\), where
`?` denotes an unresolved outcome. With determinate exposure denominator
\(n_{\pi c}\), the measured risk is \(r_\pi(c)\).

## Identified sets

The contract-identified risk set and width are

\[
\mathcal R_\pi(\mathcal C)=\{r_\pi(c):c\in\mathcal C\},\qquad
W_\pi=\max_c r_\pi(c)-\min_c r_\pi(c).
\]

If \(u_{\pi c}\) of \(N_{\pi c}\) verdicts are indeterminate and
\(v_{\pi c}\) are violations, the missing-verdict identified interval is

\[
I_\pi(c)=\left[\frac{v_{\pi c}}{N_{\pi c}},
\frac{v_{\pi c}+u_{\pi c}}{N_{\pi c}}\right].
\]

These two sets encode different unknowns: \(\mathcal R_\pi\) varies the
measurement model, whereas \(I_\pi(c)\) varies unresolved verdicts inside one
fixed model.

## Robust order

For lower-is-better risk, policy \(a\) robustly dominates \(b\) on
\(\mathcal C\) when

\[
M_{a\prec b}=\min_{c\in\mathcal C}\{r_b(c)-r_a(c)\}>0.
\]

The partial-identification analogue replaces point risks with intervals and
requires

\[
M^{PI}_{a\prec b}=\min_c\{\inf I_b(c)-\sup I_a(c)\}>0.
\]

The second condition is stronger: it preserves the order under every admissible
assignment of all unresolved verdicts.

## Proposition 1: monotonicity under contract-set expansion

If \(\mathcal C\subseteq\mathcal C'\), then
\(W_\pi(\mathcal C')\ge W_\pi(\mathcal C)\) and
\(M_{a\prec b}(\mathcal C')\le M_{a\prec b}(\mathcal C)\).

**Proof.** A maximum over a superset cannot decrease and a minimum over a
superset cannot increase. Therefore adding a defensible contract can widen a
cardinal identified set or remove a robust-order edge, but cannot create an edge
that was absent on the smaller set. \(\square\)

## Proposition 2: robust decision regions

For an acceptance threshold \(\tau\), the decision `accept if risk <= tau` is
contract-invariant for policy \(\pi\) if either
\(\max_c r_\pi(c)\le\tau\) or \(\min_c r_\pi(c)>\tau\). It is potentially
contract-dependent whenever
\(\min_c r_\pi(c)\le\tau<\max_c r_\pi(c)\).

**Proof.** In the first two cases all elements of the identified set lie on one
side of the threshold. In the third case the set contains risks on both sides
or at the boundary, so admissible contracts can yield different decisions.
\(\square\)

## Proposition 3: sampling separation is not order robustness

A finite-contract point margin \(M_{a\prec b}>0\) does not imply that a
simultaneous confidence interval for every paired contrast excludes zero.
Conversely, an interval excluding zero under one contract does not imply
\(M_{a\prec b}>0\) across all contracts.

**Justification.** The first statement compares a finite collection of point
estimates, while the interval also reflects sampling variability and
multiplicity. The second uses one contract only, whereas the minimum defining
\(M\) ranges over all contracts. Neither statement logically entails the other.

## Proposition 4: adversarial label radius

For a fixed outcome contract and task-macro contrast \(D_{ab}\), each candidate
single-episode relabel has a known signed contrast increment \(\delta_i\).
When \(D_{ab}>0\), the minimum number of relabels required to reach a tie is the
smallest \(k\) for which the sum of the \(k\) most negative admissible
increments is at most \(-D_{ab}\); the analogous rule uses the most positive
increments when \(D_{ab}<0\).

**Proof.** For any fixed cardinality, choosing the increments with greatest
magnitude in the required direction minimizes the resulting contrast. Hence no
other subset of the same size can cross the boundary earlier. \(\square\)

## Claim boundary

These propositions formalize finite-model sensitivity. They do not justify the
completeness of \(\mathcal C\), a probability distribution over contracts,
causal architecture effects, calibrated physical consequences or deployment
acceptance.

