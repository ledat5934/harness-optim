# Repo Playbook

Use `./policy.json` as the authoritative D1-D6 summary.
Use this file for stable MemoHarness execution heuristics that should survive iteration-to-iteration.

Current priorities:
- Read `./policy.json` first, then use this playbook for stable execution heuristics.
- D1 strategy: Explicit answer formatting and multi-app identity tracking
- D2 strategy: Direct targeted API tool invocations without exploratory trial calls
- D4 strategy: Step-budgeted execution: plan sequence upfront, batch queries, mutate early
- D5 strategy: Sliding window of 30 turns to retain execution context
- D6 strategy: Strict schema conformance: raw numeric values without currency symbols

Distilled emphasis:
- Recent distilled pressure is highest on D4 (5 pattern(s)); keep that dimension under active scrutiny.