# Rolling Memory

Updated after iteration 3.

- Read `./policy.json` first and use this file only for recent distilled lessons.
- Keep only recurring failures and verified repair heuristics here.

Recent distilled patterns:
- [D4] Execution turn exhaustion (hitting 40-call limit): Tasks fail when spending turns re-querying state to verify successful actions or performing exhaustive multi-app cross-checks before outputting.
  Fix: Trust successful tool execution status directly. Prohibit redundant post-action reads; finalize and call finish immediately upon completing required actions.
  Evidence: 6104387_1, 6104387_2, 6104387_3, afc0fce_2, d0b1f43_2
