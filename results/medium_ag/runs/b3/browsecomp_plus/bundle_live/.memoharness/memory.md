# Rolling Memory

Updated after iteration 2.

- Read `./policy.json` first and use this file only for recent distilled lessons.
- Keep only recurring failures and verified repair heuristics here.

Recent distilled patterns:
- [D2] The search strategy relies on exhaustive keyword variations and narrow term reformulation rather than fetching and inspecting document contents. Agents loop through queries without reading retrieved page text, quickly depleting turn limits before uncovering necessary evidence and ultimately forcing ungrounded guesses at the horizon.
  Effect: Prevents search-loop budget exhaustion in 5 cases. Shift D2 retrieval_mode to forced_fetch_and_parse with explicit page extraction depth, capping search queries before mandatory inspection.
  Evidence: 769, 773, 784
- [D6] Agents consistently contaminate final answer calls with explanatory prose, preambles, and conversational narrative rather than pure entities. The current D6 configuration (direct_entity postprocessor with verifier_slot) fails to parse or strip extraneous commentary from the submission string, causing strict benchmark evaluators to reject otherwise grounded answers.
  Effect: Eliminates repeated zero-reward evaluations across 8 cases. Upgrade D6 postprocess to regex_entity_cleaner or llm_extractor, and configure the validator to enforce strict isolated token matching.
  Evidence: 770, 772, 773
- [D2] The retrieval workflow relies on overly rigid keyword queries and fails to systematically fetch and inspect candidate documents, leading to budget depletion before locating the necessary factual evidence.
  Effect: Agents exhaust step limits and submit ungrounded fallback guesses. Configure D2 with iterative query expansion and automatic snippet ranking, while increasing D4 step budgets for complex browse trajectories.
  Evidence: 769, 773, 784
- [D6] Across multiple browsecomp_plus cases, the agent repeatedly includes explanatory narratives, reasoning preambles, and conversational text within the final answer submission instead of submitting only the isolated entity, causing post-processing and verification validation checks to fail.
  Effect: Causes 0.0 reward across 8 cases due to strict string matching failures. Update D6 postprocess to an active entity-extraction parser (e.g., regex/schema extraction) and enforce strict single-token/entity verification.
  Evidence: 770, 772, 773
- [D4] Multi-hop browsing cases frequently exhaust turn budgets before resolving all intermediary facts, triggering premature termination under hard step limits and forcing unverified fallback submissions.
  Effect: Prevents step-exhaustion failures on 3 cases. Increase the maximum step limit in D4 and adjust the stop rule to prioritize evidence grounding over early budget convergence.
  Evidence: 769, 794, 796