# Rolling Memory

Updated after iteration 5.

- Read `./policy.json` first and use this file only for recent distilled lessons.
- Keep only recurring failures and verified repair heuristics here.

Recent distilled patterns:
- [D4] AppWorld tasks risk turn limit exhaustion when agents perform unconstrained probing or redundant post-mutation verification.
  Resolution: Enforce fast finalization upon mutation success, zero post-action read checks, targeted search filters, and immediate finish calls.
  Evidence: 100% success rate across all evaluated flipping tasks in iteration 4 (28/28 solved).
