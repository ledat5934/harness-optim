# Repo Playbook

Use `./policy.json` as the authoritative D1-D6 summary.
Use this file for stable MemoHarness execution heuristics that should survive iteration-to-iteration.

Current priorities:
- D1 strategy: strict_canonical_entity_extraction
- D2 strategy: broad_noun_queries_with_active_page_inspection
- D4 strategy: hard_step_cap_with_fallback_convergence
- D5 strategy: rolling_window_with_distilled_heuristics
- D6 strategy: strict_isolated_entity_no_narrative

Execution guidelines:
1. Finish Call Mandatory: Always invoke the finish tool with the answer argument. Never leave the final answer in text or thoughts.
2. Pure Entity Strings: Strip markdown, labels, and sentences from the finish argument.
3. Inspect First: Inspect promising URLs rather than continuously issuing query variants.
4. Hard Convergence: Stop searching after 2 uninformative queries; call finish by step 16.
