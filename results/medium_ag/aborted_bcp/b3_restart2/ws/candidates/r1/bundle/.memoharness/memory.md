# Rolling Memory

Updated after iteration 0.

- Read `./policy.json` first and use this file only for recent distilled lessons.
- Keep only recurring failures and verified repair heuristics here.

Recent distilled patterns:
- [D2] Query phrasing and document inspection: Exact quote queries (`"..."`) and multi-clause natural language questions frequently return 0 search hits. Unpack into 2-5 essential keywords. Once relevant URLs or snippets appear, inspect the document text directly instead of issuing successive search queries. Evidence: 793, 794, 796, 811, 815, 821, 822, 830, 833.
- [D4] Step limit exhaustion: Successful tasks converge in 5-17 calls; tasks hitting 24-25 calls reliably fail. If a search sequence does not find exact certainty by turn 15, synthesize the strongest grounded candidate and call finish. Evidence: 819, 821, 822, 830, 832, 836.
- [D1/D6] Direct entity output format: Verifiers score exact target answers. Narrative explanations or failure to complete via the expected finish action lead to 0 reward. Emit only the direct requested entity or phrase. Evidence: 809, 826.
