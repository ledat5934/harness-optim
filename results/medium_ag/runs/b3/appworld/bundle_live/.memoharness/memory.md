# Rolling Memory

Updated after iteration 2.

- Read `./policy.json` first and use this file only for recent distilled lessons.
- Keep only recurring failures and verified repair heuristics here.

Recent distilled patterns:
- [D2] Misusing task completion / finish tool as an exploratory probe terminates the session prematurely. Completion tools must strictly be invoked only when all task requirements are satisfied (evidence: d0b1f43_2).
- [D4] Unbounded speculative querying loops when items are missing exhaust the execution budget. Bound query retries to at most one alternative filter before proceeding (evidence: afc0fce_2).
- [D4] Unbatched linear scanning across multi-app entities consumes excessive turns. Plan sequence upfront, filter specifically, and mutate target state as soon as IDs are known (evidence: b0a8eae_1, b0a8eae_2, b0a8eae_3, d0b1f43_3).
