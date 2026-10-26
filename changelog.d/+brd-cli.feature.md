Added `scripts/generate_from_brd.py --document <document.md>` to extract verified requirements and run C4, performance analysis, Sequence and API generation with one configuration. The output directory defaults to `output/<document-stem>` and may be overridden. The output includes source evidence, an intermediate scenario and a typed machine-readable run report with stage warnings and performance-input provenance.

Source-backed read percentages such as `80%` are converted to fractional workload ratios after literal evidence validation, preserving the original citation.
