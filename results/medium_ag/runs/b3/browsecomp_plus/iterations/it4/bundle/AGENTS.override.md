# BrowseComp+ Execution Protocol

## 1. Finish Tool Call & Entity Extraction (D6, D1)
- You MUST invoke the finish tool to submit the answer. Never end your turn by only writing the answer in reasoning/thought text or submitting an empty tool call.
- The finish argument must be ONLY the raw target entity, name, date, or number.
- Exclude all conversational prose, markdown bolding (`**`), introductory phrases ("The answer is..."), and explanations.

## 2. Search Strategy & Page Inspection (D2)
- Query formulation: Use 2-4 core descriptive nouns. Avoid exact-match quotes (`"..."`) or boolean syntax.
- Mandatory inspection: When search snippets show a relevant candidate, inspect the page content directly rather than issuing repeated searches.
- Stagnation recovery: If a query yields zero or unhelpful results, broaden search terms or try synonyms immediately instead of repeating minor variants.

## 3. Turn Budget & Forced Convergence (D4)
- Hard limit: The task terminates at turn 25. You must call finish by turn 16.
- If 2 consecutive searches yield no progress, stop searching and inspect existing results.
- By step 15, commit to the best grounded candidate observed and submit it via the finish tool. Never run out of turns.
