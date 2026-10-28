# Rolling Memory

Updated after iteration 5.

- Read `./policy.json` first and use this file only for recent distilled lessons.
- Keep only recurring failures and verified repair heuristics here.

Recent distilled patterns:
- [D4] AppWorld tasks fail consistently under the standard ReAct loop because agents exhaust step and turn limits through exploratory probing and exhaustive querying across large result sets without structured execution or early batching.
  Effect: Eliminates premature step-out failures across all 3 cases; switch D4 workflow from react_loop to plan_and_solve or hierarchical execution to enforce multi-stage querying and pre-planned actions.
  Evidence: b0a8eae_1, b0a8eae_2, b0a8eae_3
- [D4] AppWorld tasks fail consistently under the standard react_loop workflow because agents hit step limits through trial probing and exhaustive, unguided querying before executing target actions.
  Effect: Causes complete task failure (0.00 reward) across all 3 cases. Switch D4 workflow to plan_and_solve or increase step limits while enforcing query filtering.
  Evidence: b0a8eae_1, b0a8eae_2, b0a8eae_3
- [D4] Agents in AppWorld exhaust turn limits within the standard ReAct loop due to unguided trial probing and sequential queries over large state spaces without structured planning.
  Effect: Causes 100% failure rate (reward 0.00) across all cases via step limit exhaustion. Transition D4 workflow from react_loop to plan_and_solve or introduce hierarchical planning.
  Evidence: b0a8eae_1, b0a8eae_2, b0a8eae_3
- [D4] Agents consistently exhaust turn limits in AppWorld tasks under the basic react_loop workflow due to excessive trial exploratory probing and unguided, exhaustive data retrieval without staged execution.
  Effect: Eliminates 100% failure rate across these tasks; switch D4 workflow from react_loop to plan_and_solve or hierarchical_react to impose structured planning and prevent step-limit exhaustion.
  Evidence: b0a8eae_1, b0a8eae_2, b0a8eae_3
- [D4] AppWorld agents consistently hit execution step limits within the react_loop due to inefficient exploratory probing, trial executions, and exhaustive linear querying of large result sets without batched filtering.
  Effect: Causes 100% failure rate across 12 evaluation episodes. Update D4 workflow to an agentic loop with upfront plan-and-solve budgeting, batch queries, and strict limits on exploratory calls.
  Evidence: b0a8eae_1, b0a8eae_2, b0a8eae_3