# Repo Playbook

Use `./policy.json` as the authoritative D1-D6 summary.
Use this file for stable MemoHarness execution heuristics that should survive iteration-to-iteration.

Current priorities:
- Read `./policy.json` first, then use this playbook for stable execution heuristics.
- D1 strategy: strict_canonical_entity_extraction
- D2 strategy: broad_noun_queries_with_active_page_inspection
- D4 strategy: hard_step_cap_with_fallback_convergence
- D5 strategy: rolling_window_with_distilled_heuristics
- D6 strategy: strict_isolated_entity_no_narrative

Distilled emphasis:
- Primary failure mode in iteration 1 was D6 (9 cases): verbose prefaces and explanations submitted inside the answer field resulted in truncation. Enforce isolated target entity output.
- Secondary failure mode was D4 (4 cases): turn limit exhaustion. Enforce hard step cap and early convergence by step 15-18.
- Retrieval discipline on D2: avoid quotation marks and query cycling; inspect candidate pages directly.
