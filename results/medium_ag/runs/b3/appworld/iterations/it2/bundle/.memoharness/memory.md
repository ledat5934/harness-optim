# Rolling Memory

Updated after iteration 1.

- Read `./policy.json` first and use this file only for recent distilled lessons.
- Keep only recurring failures and verified repair heuristics here.

Recent distilled patterns:
- [D1] Ambiguous instruction framing between informational queries and operational actions causes deliberation overhead and incorrect terminal submission format.
  Effect: Causes failure on final answer submission tasks (e.g., d0b1f43_3). Distinguish informational answers (exact scalar value or entity without conversational wrapper) from operational action tasks.
  Evidence: d0b1f43_3
- [D4] AppWorld agents hit execution step limits within reactive loops due to exploratory probing and unbatched linear item-by-item queries.
  Effect: Causes failure from turn exhaustion. Prevented by upfront sequence planning, targeted filter queries, and immediate mutation upon target resolution.
  Evidence: b0a8eae_1, b0a8eae_2, b0a8eae_3
