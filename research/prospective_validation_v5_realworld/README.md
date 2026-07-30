# Prospective physical-episode validation

This directory contains the result-independent software for protocol
`CDSE-ARMNET-V5-RW-001`.

- `analysis/v5_analysis.py`: frozen analysis implementation.
- `design/`: pre-result scope and design contract.
- `tests/`: synthetic pre-freeze checks and receipt.
- `reporting/report_v5_results.py`: frozen extraction of journal-facing
  aggregate tables from a formal result JSON.
- `reporting/build_v5_figure.py`: frozen publication-figure generator.

The repository intentionally excludes ArmnetBench episode data, policy
weights, formal scientific results, author-private documents, credentials and
server addresses. The reporting scripts do not change or recompute the formal
analysis; they read a formal result JSON and produce presentation-layer files.

