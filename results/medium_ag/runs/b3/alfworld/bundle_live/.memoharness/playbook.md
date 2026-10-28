# Repo Playbook

Use `./policy.json` as the authoritative D1-D6 summary.
Use this file for stable MemoHarness execution heuristics that should survive iteration-to-iteration.

Current priorities:
- Read `./policy.json` first, then use this playbook for stable execution heuristics.
- D1 strategy: inspect verifier evidence first
- D2 strategy: use local tooling and file inspection first
- D4 strategy: iterate until checks are satisfied
- D5 strategy: keep rolling memory compact and evidence-backed
- D6 strategy: validate outputs before finishing