# Rolling Memory

Updated after iteration 1.

- Read `./policy.json` first and use this file only for recent distilled lessons.
- Keep only recurring failures and verified repair heuristics here.

Recent distilled patterns:
- [D6] Agents emitted verbose conversational narrative prefaces or explanatory paragraphs inside answer submissions, truncating the target entity and eliminating reward across 9 cases (770, 772, 773, 775, 778, 783, 784, 787, 791).
  Repair: Strict prohibition of prefaces, explanations, and markdown wrappers. Output only the clean isolated canonical entity name, date, or number.
- [D4] Search loops cycling past turn 18 hit maximum turn limits without submitting an answer (794, 796, 797, 805).
  Repair: Hard step convergence cap. By step 15 halt search exploration; submit the best grounded candidate extracted so far before step 18.
- [D2] Queries with rigid phrasing or quotation marks yielded zero snippets, triggering repetitive query variants instead of reading candidate documents (769).
  Repair: Use 2-4 broad noun terms and immediately fetch candidate page text rather than spinning on query rewrites.
