# Decision theory for measurement-contract uncertainty

Let \(\Pi\) be a finite policy set, \(\mathcal C\) a finite set of admissible
executable measurement contracts and \(I_\pi(c)=[\ell_\pi(c),u_\pi(c)]\) the
identified risk interval for policy \(\pi\) under contract \(c\). A point
verdict is the special case \(\ell_\pi(c)=u_\pi(c)=r_\pi(c)\).

The contract-and-verdict identified hull is

\[
H_\pi(\mathcal C)=[L_\pi,U_\pi],\qquad
L_\pi=\min_{c\in\mathcal C}\ell_\pi(c),\quad
U_\pi=\max_{c\in\mathcal C}u_\pi(c).
\]

Its width \(W_\pi=U_\pi-L_\pi\) summarizes the range induced jointly by the
declared contract set and unresolved verdict assignments. When all verdicts
are determinate, this reduces to the finite-contract width used in the paper.

## Proposition 1: exact robust threshold decision

For the rule "accept policy \(\pi\) if risk is at most \(\tau\)", the only
decision justified uniformly over \(H_\pi\) is

\[
d^*(\pi;\tau)=
\begin{cases}
\text{accept}, & U_\pi\le \tau,\\
\text{reject}, & L_\pi>\tau,\\
\text{defer}, & L_\pi\le\tau<U_\pi.
\end{cases}
\]

**Proof.** If \(U_\pi\le\tau\), every admissible risk satisfies the acceptance
rule. If \(L_\pi>\tau\), none does. Otherwise the hull contains an admissible
value at or below the threshold and an admissible value above it, so neither a
uniform accept nor a uniform reject statement follows. \(\square\)

The threshold ambiguity set is therefore exactly
\(A_\pi=[L_\pi,U_\pi)\), whose length is \(W_\pi\). Contract width consequently
has a direct decision interpretation: it is the measure of the threshold range
over which a point decision can depend on the measurement contract.

## Proposition 2: monotonicity under assessor-set expansion

If \(\mathcal C\subseteq\mathcal C'\), then

\[
H_\pi(\mathcal C)\subseteq H_\pi(\mathcal C'),\qquad
A_\pi(\mathcal C)\subseteq A_\pi(\mathcal C'),\qquad
W_\pi(\mathcal C')\ge W_\pi(\mathcal C).
\]

**Proof.** Minimization over a superset cannot increase \(L_\pi\), and
maximization over a superset cannot decrease \(U_\pi\). The interval inclusion
and the width inequality follow. \(\square\)

Thus adding a defensible contract can turn a previously resolved threshold
decision into defer, but cannot make an unresolved decision robust without
removing contracts or adding information that narrows the identified
intervals.

## Proposition 3: two levels of robust policy ordering

For lower-is-better risk, define the paired-contract margin

\[
m^{\mathrm{paired}}_{a\prec b}
=\min_{c\in\mathcal C}\{\ell_b(c)-u_a(c)\}
\]

and the arbitrary-contract margin

\[
m^{\mathrm{arbitrary}}_{a\prec b}
=L_b-U_a.
\]

If \(m^{\mathrm{arbitrary}}_{a\prec b}>0\), policy \(a\) has lower identified
risk than \(b\) for every independent choice of contracts and unresolved
verdict assignments. If only
\(m^{\mathrm{paired}}_{a\prec b}>0\), the order is guaranteed when both
policies are scored under the same contract, but it need not survive different
contracts for the two policies.

**Proof.** The arbitrary-contract condition is equivalent to
\(U_a<L_b\), which separates the complete identified hulls. The paired
condition compares only the two intervals indexed by the same \(c\), so it is
weaker. Since the arbitrary comparison includes every same-contract pair,
\(m^{\mathrm{arbitrary}}\le m^{\mathrm{paired}}\). \(\square\)

## Proposition 4: robust-order graphs shrink under expansion

Construct a directed graph with edge \(a\to b\) whenever the selected robust
margin is positive. Expanding \(\mathcal C\) can remove an existing edge but
cannot create a new edge.

**Proof.** A paired margin is a minimum over contracts and therefore cannot
increase after set expansion. An arbitrary margin has a nonincreasing lower
endpoint for \(b\) and a nondecreasing upper endpoint for \(a\). Hence it also
cannot increase. \(\square\)

## Proposition 5: sampling separation is logically distinct

A positive robust point margin does not imply that a simultaneous confidence
interval for the corresponding contrast excludes zero. Conversely, an
interval excluding zero under one contract does not establish a positive
robust margin over all contracts.

**Justification.** The robust margin quantifies variation over a declared
measurement-model set at the observed point estimates. A confidence interval
also reflects the registered sampling process and multiplicity. The two
objects answer different questions and neither entails the other.

## Claim boundary

These results formalize decisions conditional on the declared risk quantity,
contract set and threshold rule. They do not justify the completeness of the
contract set, the numerical threshold, causal architecture effects, calibrated
physical consequences, acceptable risk or deployment certification.
