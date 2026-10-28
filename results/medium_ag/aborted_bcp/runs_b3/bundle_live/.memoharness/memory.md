# Rolling Memory

Updated after iteration 1.

- Read `./policy.json` first and use this file only for recent distilled lessons.
- Keep only recurring failures and verified repair heuristics here.

Distilled Patterns:
- [D6/D1] Conversational wrappers and narrative justifications fail evaluators that match exact entities (cases 811, 815, 821, 822, 826). The final response must be the bare answer entity or phrase only.
- [D4/D2] Repetitive querying and reliance on search snippets causes turn exhaustion at step 25 (cases 793, 794, 796, 797, 802, 833). Decompose constraints, inspect full page texts directly, and converge by step 18-20.
- [D3] Case 809 suffered generation truncation under 2048 max tokens. Increased D3.max_tokens to 3072 to ensure clean finish tool execution.
