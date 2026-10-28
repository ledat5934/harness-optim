# Rolling Memory

Updated after iteration 3.

- Read `./policy.json` first and use this file only for recent distilled lessons.
- Keep only recurring failures and verified repair heuristics here.

Recent distilled patterns:
- [D6] Tool Termination: The agent must execute the finish tool call to submit the answer; placing answers in internal thoughts or emitting empty tool calls results in immediate failure (e.g. 775, 783). Format argument as pure canonical entity without narrative.
- [D4] Turn Exhaustion: Agents exhaust the 25-turn budget cycling through repetitive search queries without converging (e.g. 769, 770, 772, 773). Force termination with best grounded candidate by step 16.
- [D2] Search Stagnation: Keyword queries are frequently too narrow or repetitive (e.g. 787). Relax keywords into 2-4 noun phrases and inspect returned web pages directly rather than re-searching.
