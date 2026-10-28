# Repo Playbook

Use `./policy.json` as the authoritative D1-D6 summary.
Use this file for stable MemoHarness execution heuristics that should survive iteration-to-iteration.

Current priorities:
- Read `./policy.json` first, then use this playbook for stable execution heuristics.
- D1 strategy: decomposed_multi_hop_entity_extraction
- D2 strategy: broad_noun_queries_with_active_page_inspection
- D4 strategy: calibrated_25_step_budget_convergence
- D5 strategy: rolling_window_with_distilled_heuristics
- D6 strategy: strict_isolated_entity_no_narrative

Distilled emphasis:
- Recent distilled pressure is highest on D6 (entity cleanliness in finish argument).
- Search query decomposition on multi-hop questions (D1/D2) directly addresses regressions in flipping cases 802 and 805.
- Turn management (D4) is calibrated to the 25-step ceiling, permitting deep multi-hop resolution through step 21 while ensuring strict submission by step 23.
