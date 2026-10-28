# Rolling Memory

Updated after iteration 1.

- Read `./policy.json` first and use this file only for recent distilled lessons.
- Keep only recurring failures and verified repair heuristics here.

Recent distilled patterns:
- [D4] AppWorld agents consistently hit execution step limits within the react_loop due to inefficient exploratory probing, trial executions, and exhaustive linear querying of large result sets without batched filtering.
  Effect: Causes 100% failure rate across 12 evaluation episodes. Update D4 workflow to an agentic loop with upfront plan-and-solve budgeting, batch queries, and strict limits on exploratory calls.
  Evidence: b0a8eae_1, b0a8eae_2, b0a8eae_3
- [D4] AppWorld tasks fail due to step limit exhaustion under the standard ReAct loop. The agent consumes available turns on unconstrained exploratory probing, trial executions, and exhaustive queries over large datasets without completing the core task requirements.
  Effect: Causes 100% persistent failure across all 4 cases. Migrate D4 workflow from react_loop to plan_and_execute or two_stage_planner to structure multi-stage filtering and prevent turn exhaustion.
  Evidence: d0b1f43_3, b0a8eae_1, b0a8eae_2
- [D4] AppWorld tasks consistently hit step and turn limits during reactive execution. The standard react_loop workflow causes the agent to spend its entire turn budget on exploratory trial queries and unguided iteration over large result sets without completing the core task requirements.
  Effect: Causes 100% failure across all 4 benchmark cases (reward 0.0). Transition D4 workflow from react_loop to plan_and_solve or hierarchical_react, or adjust execution limits and query filtering constraints.
  Evidence: d0b1f43_3, b0a8eae_1, b0a8eae_2
- [D4] AppWorld tasks fail consistently under D4 due to turn limit exhaustion, caused by the naive react_loop getting trapped in exploratory probing, redundant trial executions, and unbatched iterative queries.
  Effect: All 3 cases score 0.0 across all attempts. Transition D4 workflow from 'react_loop' to 'plan_and_solve' or structured multi-action planning to eliminate turn budget waste.
  Evidence: d0b1f43_3, b0a8eae_1, b0a8eae_2
- [D4] Standard ReAct loop workflow exhausts execution turn limits during multi-step AppWorld tasks when querying and filtering data, leading to incomplete execution without reaching terminal goal state.
  Effect: Causes 0.0 reward across all 6 runs; switch D4 workflow to a plan-and-solve or hierarchical ReAct policy with step budgeting and query filtering.
  Evidence: d0b1f43_3, b0a8eae_1