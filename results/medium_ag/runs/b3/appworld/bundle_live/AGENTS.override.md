# AppWorld Agent Execution Guide

## 1. Step Budget & Turn Economy (Priority D4)
- **Plan Upfront**: Formulate the full multi-step plan before invoking tools. Do not spend turns on open-ended exploratory calls or trial executions.
- **Direct Execution**: Avoid redundant documentation or schema checking queries. Call target APIs directly with expected parameters.
- **Targeted Querying**: When filtering transactions, emails, or messages, query using specific search filters rather than sequentially fetching and inspecting items one by one.
- **Early Mutation**: As soon as target IDs or values are identified, execute the required state changes (transfers, sends, updates) immediately.

## 2. Multi-App Identity & Context (Priority D1)
- Maintain consistent requester context and user account tokens across different app domains.
- Map entity references (names, phone numbers, account IDs) directly to their target app IDs before executing transactions.

## 3. Output Formatting & Answer Conformance (Priority D6)
- When a task requires answering a specific value (e.g., amount, balance, count):
  - Return the raw scalar value directly.
  - Do not prepend currency signs (e.g., use `45.50`, not `$45.50`) unless explicitly required.
  - Strip explanatory commentary or conversational filler.

Bundle contract:
- Read `./policy.json` for the authoritative D1-D6 summary before using playbook or memory notes.
- Treat `./.memoharness/playbook.md` as stable repo heuristics and `./.memoharness/memory.md` as rolling distilled notes.

