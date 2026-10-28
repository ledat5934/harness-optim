# AppWorld Agent Execution Guide

## 1. Step Budget & Turn Economy (Priority D4)
- **Plan Upfront**: Formulate the multi-step plan before invoking tools. Avoid open-ended exploratory calls.
- **Direct Execution**: Call target APIs directly with expected parameters without redundant schema checks.
- **Targeted Querying**: Use specific search filters when querying messages, transactions, or contacts rather than fetching and inspecting items sequentially.
- **Early Mutation**: As soon as target IDs or values are identified, execute the required state changes immediately.

## 2. Multi-App Identity & Context (Priority D1)
- Maintain consistent requester context and user account identity across different app domains.
- Map entity references (names, phone numbers, account IDs) directly to their target app IDs before executing transactions.

## 3. Output Formatting & Answer Conformance (Priority D1 & D6)
- If the task asks a question or requests information:
  - Return the exact requested value or identifier directly without conversational filler.
  - For numeric amounts, output the raw scalar value without currency symbols unless explicitly requested.
- If the task requires performing an action, execute all necessary tool calls and finish cleanly.
