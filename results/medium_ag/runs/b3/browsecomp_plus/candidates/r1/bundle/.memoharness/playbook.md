# Repo Playbook

Use `./policy.json` as the authoritative D1-D6 summary.
Use this file for stable MemoHarness execution heuristics that should survive iteration-to-iteration.

Current priorities:
- D1 strategy: enforce direct entity output without unprompted conversational explanation
- D2 strategy: keyword search followed by document inspection; avoid quote-restricted search loops
- D4 strategy: budget-aware convergence; synthesize by step 15-18 rather than exhausting step budget
- D5 strategy: keep rolling memory compact and evidence-backed
- D6 strategy: clean finish invocation with direct target value

Distilled emphasis:
- High priority on D2: document inspection prevents repetitive search loops.
- High priority on D4: step budget cap prevents timeouts on tasks that already located candidate documents.
