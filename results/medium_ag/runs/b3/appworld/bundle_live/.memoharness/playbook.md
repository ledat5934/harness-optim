# Repo Playbook

Use `./policy.json` as the authoritative D1-D6 summary.
Use this file for stable MemoHarness execution heuristics that should survive iteration-to-iteration.

Current priorities:
- Read `./policy.json` first, then use this playbook for stable execution heuristics.
- D1 strategy: Direct final answer formatting and precise multi-app entity resolution
- D2 strategy: Direct targeted API tool invocations; never invoke completion tool for probing
- D4 strategy: Strict turn budgeting: eliminate redundant post-mutation verification and finalize immediately
- D5 strategy: Sliding window of 30 turns to retain execution context
- D6 strategy: Strict schema conformance: raw numeric values and exact target entities

Distilled emphasis:
- Recent distilled pressure is highest on D4 (5 pattern(s)); keep that dimension under active scrutiny.