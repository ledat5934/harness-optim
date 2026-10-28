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
- Recent distilled pressure is highest on D6 (2 pattern(s)); keep that dimension under active scrutiny.
- Recent distilled pressure is highest on D2 (2 pattern(s)); keep that dimension under active scrutiny.
- Recent distilled pressure is highest on D4 (1 pattern(s)); keep that dimension under active scrutiny.