# Repo Playbook

Use `./policy.json` as the authoritative D1-D6 summary.
Use this file for stable MemoHarness execution heuristics that should survive iteration-to-iteration.

Current Priorities:
- D1/D6: Extract strictly the target value without conversational preamble, prefix, or explanation.
- D2: Inspect full document contents when search snippets lack necessary precision.
- D3: Maintain sufficient token headroom (3072) to prevent truncation of final calls.
- D4: Plan multi-constraint searches and finish before step 20 to avoid turn budget exhaustion.
- D5: Retain complete multi-hop conversation context across steps.
