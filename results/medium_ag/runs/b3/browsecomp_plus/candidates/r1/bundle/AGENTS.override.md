# Execution Guidelines for Browsecomp Plus

## 1. Output Format & Answer Extraction (D6 / D1)
- The final response must contain strictly the requested target entity, name, date, number, or exact phrase.
- Do NOT include conversational filler, preamble, post-hoc explanations, or justification (e.g., avoid "Based on the search...", "The answer is...", or narrative summaries).
- Directly output the minimal, exact value required by the question.

## 2. Search Strategy & Full Document Inspection (D2 / D4)
- Decompose complex or multi-constraint questions into discrete sub-goals before issuing queries.
- Do not rely solely on superficial search snippets. When a snippet mentions the relevant subject or document, inspect the full document or page to extract exact facts.
- Avoid repetitive query variations. If two consecutive searches yield no new information, immediately pivot keywords or search from the perspective of an alternative entity or constraint.

## 3. Turn Budget & Early Convergence (D4)
- Trajectories are bounded to 25 steps. Track step progression and converge early.
- Finalize information gathering by step 18 to avoid hard cutoffs.
- When an entity satisfies all known constraints, issue the final answer immediately instead of executing redundant verification queries.
