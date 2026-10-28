# BrowseComp+ Execution Protocol

## 1. Output Formatting & Strict Canonical Extraction (D6, D1)
- The final answer must contain ONLY the isolated target entity, name, number, date, or requested phrase.
- STRICT PROHIBITION: Do NOT include explanatory sentences, narrative prefaces ("The answer is...", "Based on..."), disclaimers, multiple alternatives, or markdown formatting (`**...**`). Verbose narrative submissions cause truncation and immediate evaluation failure.
- Validate before submitting: Ensure the final string is a clean, single canonical entity.

## 2. Search Query Formulation & Page Inspection (D2)
- Formulate concise, keyword-dense queries (2-4 core nouns). Do NOT use restrictive quotation marks (`"..."`) or complex boolean clauses.
- If a search yields empty or irrelevant snippets, immediately strip non-essential modifiers and broaden terms.
- Do not keep searching once a candidate URL or title appears relevant: fetch and inspect the page content directly for concrete facts (names, dates, figures).

## 3. Turn Budget & Hard Convergence (D4)
- Hard step limit: tasks fail when step count exceeds 18.
- By step 10-12: locate the primary candidate source and inspect page text.
- By step 15: halt exploratory searching. If the exact answer is uncertain, select the single best grounded candidate found so far.
- Never loop past step 18 searching for perfection; submit the top grounded candidate immediately.

Bundle contract:
- Read `./policy.json` for authoritative D1-D6 configuration.
- Read `./.memoharness/playbook.md` for stable heuristics and `./.memoharness/memory.md` for rolling lessons.
