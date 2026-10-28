# BrowseComp+ Execution Protocol

## 1. Strict Canonical Entity Output (D6, D1)
- The final answer submitted to finish must contain ONLY the isolated target entity: a person's name, number, date, location, or requested term.
- ZERO conversational filler or reasoning: Never include preambles ("Based on...", "The answer is..."), disclaimers, markdown bolding (`**`), or explanatory sentences.
- If the target is an entity, return only that exact entity string (e.g., `Alice Smith`, `1994`, `Mount Everest`). Any explanatory prefix or narrative envelope causes immediate evaluation failure.

## 2. Multi-Hop Search & Document Inspection (D2, D1)
- Multi-hop decomposition: If a question asks about an entity defined by an intermediate fact (e.g., "spouse of the director of Film X"), do NOT search the entire question. Search for Film X's director first, then search for that director's spouse.
- Query format: Use 2-4 core nouns only. Prohibit boolean operators (AND, OR, NOT), quotation marks, and full conversational sentences.
- Active page inspection: Once a promising search result appears, fetch and inspect the page content immediately. Never endlessly loop search reformulations without reading page contents.

## 3. 25-Step Budget & Convergence (D4)
- Total environment limit is 25 steps.
- Steps 1-16: Formulate decomposed queries, follow links, and inspect source pages for factual verification.
- Steps 17-21: Synthesize intermediary facts. If the exact answer remains ambiguous, select the single most strongly grounded candidate entity found so far.
- Steps 22-23: Halt all browsing and submit the isolated candidate entity. Never allow the trajectory to exhaust turn 25 without submitting.

Bundle contract:
- Read `./policy.json` for authoritative D1-D6 configuration.
- Read `./.memoharness/playbook.md` for stable heuristics and `./.memoharness/memory.md` for rolling lessons.
