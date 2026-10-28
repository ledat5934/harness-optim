# Rolling Memory

Updated after iteration 0.

- Read `./policy.json` first and use this file only for recent distilled lessons.
- Keep only recurring failures and verified repair heuristics here.

## Distilled Lessons
- **[D4] Turn Exhaustion from Sequential Inspection**:
  - Evidence: `b0a8eae_1`, `b0a8eae_2`, `afc0fce_1`, `6104387_3`.
  - Fix: Eliminate exploratory probing and 1-by-1 item retrieval. Use filtered searches and immediately proceed to required state mutations.
- **[D6/D1] Scalar Answer Formatting**:
  - Evidence: `d0b1f43_1`, `76f2c72_3`.
  - Fix: Output raw numeric values without currency symbols (`$`) or prose wrappers unless explicitly requested.
