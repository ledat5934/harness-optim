# Repo Playbook

Use `./policy.json` as the authoritative D1-D6 summary.
Use this file for stable MemoHarness execution heuristics that should survive iteration-to-iteration.

Current priorities:
- Read `./policy.json` first, then use this playbook for stable execution heuristics.
- D1 strategy: phased exploration hierarchy and category-based search heuristics.
- D2 strategy: strict native tool call execution on every step with no raw text fallback.
- D3 strategy: deterministic greedy action selection (temperature 0.0).
- D4 strategy: phased exploration (open surfaces -> appliances -> closed storage) and stage execution (locate -> take -> transform -> place).
- D5 strategy: extended history window (45 turns) to retain exploration map and prevent search cycles.
- D6 strategy: action admissibility verification against observed environment state.
