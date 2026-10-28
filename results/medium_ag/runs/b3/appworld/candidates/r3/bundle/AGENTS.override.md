# AppWorld Agent Execution Guide

## 1. Tool Discipline & Session Safety (Priority D2 & D4)
- **No Finish Probing**: Never call completion or finish tools to inspect state or trigger tracebacks; completion tool calls permanently end the session. Invoke finish only when all operations and answers are complete.
- **Bound Search Loops**: Avoid speculative repeated querying. If initial search returns no matches, attempt at most one alternative filter or index before taking the next best action.
- **Targeted Querying**: Use specific search filters (sender, recipient, dates, account IDs) rather than paginating or inspecting broad collections sequentially.
- **Early Mutation**: Execute required state mutations (transfers, status updates, message sends) immediately once target entity identifiers are resolved.

## 2. Multi-App Identity & Entity Resolution (Priority D1)
- Maintain consistent requester context across app boundaries (e.g. mapping phone/email in contacts to payment or chat accounts).
- Map entity references directly to target internal IDs before invoking transactional APIs.

## 3. Output Formatting & Answer Conformance (Priority D1 & D6)
- For informational queries, output the exact scalar value or identifier without conversational phrasing.
- For monetary or numeric values, emit raw numeric digits without currency signs or unit suffixes unless requested.
- For action tasks, complete all required mutations, then finish.

Bundle contract:
- Read `./policy.json` for authoritative D1-D6 summary before using playbook or memory notes.
- Treat `./.memoharness/playbook.md` as stable repo heuristics and `./.memoharness/memory.md` as rolling distilled notes.
