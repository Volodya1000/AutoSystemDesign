Added `scripts/generate_from_brd.py --document <document.md> --out-dir <new-directory>` to extract verified requirements and run C4, performance analysis, Sequence and API generation with one configuration. The output includes source evidence, an intermediate scenario and a machine-readable run report with stage warnings and performance-input provenance.

Source-backed read percentages such as `80%` are converted to fractional workload ratios after literal evidence validation, preserving the original citation.
