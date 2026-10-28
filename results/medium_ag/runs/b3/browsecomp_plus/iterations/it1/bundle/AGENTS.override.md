# BrowseComp+ Execution Protocol

## 1. Search Query Strategy (D2)
- Formulate concise, keyword-dense queries (2-5 terms) targeting key named entities and identifying attributes.
- Avoid multi-clause sentences or restrictive quotation marks (`"..."`) that return zero results. If a query yields few or no results, broaden keywords immediately.
- Never repeatedly re-query the same phrase with minor punctuation variations.

## 2. Document Inspection Over Search Looping (D2)
- Search snippets are often truncated. When a search returns promising candidate URLs or document titles, immediately inspect or fetch the page content rather than continuing to search.
- Extract concrete evidence (names, dates, numbers, locations) directly from document text.

## 3. Turn Budget & Early Convergence (D4)
- You have a strict limit of steps per task. High step counts (>18) strongly correlate with failure.
- Track search progress: by step 10-12, identify the primary candidate document and read it.
- By step 15-18, synthesize the best grounded evidence available and emit the answer. Do not spin in search loops until execution is forcibly halted.

## 4. Output Formatting & Grounding (D1, D6)
- Provide only the direct target answer (entity name, number, date, or specific phrase requested by the prompt).
- Do not output conversational preamble, disclaimers, or narrative explanations unless explicitly asked.
- Ensure the finish action or completion tool is invoked cleanly with the exact target value.
