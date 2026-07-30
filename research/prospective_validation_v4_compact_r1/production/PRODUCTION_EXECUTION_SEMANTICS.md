# V4-Compact-R1 production execution semantics

- Sole executor: governed L40S host; 5090 remains cancelled.
- One parent process holds
  `/workspace/lerobot-safety/control/cdse_formal_single_executor.lock`.
- Formal attempt ID and output root are unique and write-once. Any failure is
  terminal; no automatic retry or seed replacement is allowed.
- Task order is the unchanged 50-task V3-B target list. Policy order is
  `pi0`, `pi05`, `groot`.
- Every policy-task shard recreates the unchanged RoboCasa task for each paired
  environment seed `42,43,44,45,46,47,48,49`.
- Every formal trajectory executes exactly 900 environment steps. First success
  is recorded descriptively but does not terminate the exposure.
- A non-success or success-associated Gymnasium termination/truncation before
  step 900 is a terminal simulator failure.
- GR00T and OpenPI inference remain separate from RoboCasa through loopback IPC.
  Raw actions are validated, recorded and passed without clipping, scaling,
  smoothing, replacement or repair. RoboSuite endogenous saturation remains
  diagnostic evidence only.
- The V3-B property bank, C0-C5 evaluators, trace adapter, role compiler,
  thresholds, models and weights are inherited without modification.
- Every trajectory produces a compressed trace, raw-action ledger and receipt.
  Both evaluators must agree for all six contracts and no contract may be
  `INVALID`.
- Complete formal census: 150 shards, 1,200 trajectories, 1,080,000
  environment steps and 7,200 trajectory-contract evaluations.
