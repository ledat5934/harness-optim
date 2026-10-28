# AppWorld Agent Execution Guide

## 1. Tool Discipline & Turn Budget (Priority D2 & D4)
- **Fast Finalization**: Complete tasks within minimal steps. Once all required mutations succeed or target data is retrieved, synthesize the answer and call finish immediately.
- **No Redundant Verification**: Never perform follow-up read queries or cross-app verification checks to confirm a successful mutation unless explicitly mandated by the user. Trust successful tool return values.
- **No Finish Probing**: Finish/completion tools end the session permanently. Never invoke finish for testing, schema discovery, or state inspection.
- **Bounded Targeted Search**: Query with specific parameters (name, phone, dates, IDs). If initial search yields no matches, attempt at most one alternative filter before selecting the next best path. Avoid exhaustive sequential pagination.

## 2. Multi-App Identity & Entity Resolution (Priority D1)
- Map cross-app identifiers directly (e.g. resolve contact name/email to account ID in one step) and use the first unambiguous match.
- Pass resolved internal IDs directly into transactional API calls.

## 3. Output Formatting & Answer Conformance (Priority D1 & D6)
- For informational queries, emit only the requested scalar or entity value without conversational boilerplate.
- For monetary or numeric outputs, provide raw digits without currency symbols or unit labels unless requested.
- For action tasks, complete all required mutations, then finish.

Bundle contract:
- Read `./policy.json` for authoritative D1-D6 summary before using playbook or memory notes.
- Treat `./.memoharness/playbook.md` as stable repo heuristics and `./.memoharness/memory.md` as rolling distilled notes.
