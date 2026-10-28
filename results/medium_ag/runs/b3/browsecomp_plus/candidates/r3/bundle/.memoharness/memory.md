# Rolling Memory

Updated after iteration 2.

- Read `./policy.json` first and use this file only for recent distilled lessons.
- Keep only recurring failures and verified repair heuristics here.

Recent distilled patterns:
- [D6] Agents repeatedly wrap the final answer in explanatory sentences, reasoning preambles ("The answer is..."), or markdown formatting. The benchmark evaluator performs strict canonical matching; any surrounding narrative causes immediate failure (e.g., 770, 772, 773, 775, 783, 784, 787, 793, 794). Submit ONLY the isolated entity.
- [D1/D2] On multi-hop questions, issuing full-question searches or boolean expressions returns zero snippets and exhausts turns (e.g., 802, 805). Decompose queries into 2-4 noun lookups for the intermediary entity first, then query the final target.
- [D4] Complex multi-hop trajectories require 20-24 steps to resolve (e.g., 786, 788, 791, 792, 797). Forcing early convergence at step 18 aborts viable paths. Spend steps 1-16 exploring and inspecting, synthesize by step 21, and submit cleanly at steps 22-23 before the 25-step cutoff.
