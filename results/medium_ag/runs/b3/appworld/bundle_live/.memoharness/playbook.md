# AppWorld Execution Playbook

Use `./policy.json` as the authoritative D1-D6 configuration.

## Operational Directives
- **D4 Workflow (Budget Conservation)**:
  - Form an end-to-end action sequence before calling tools.
  - Avoid iterative sequential item inspection; use batch/filter parameters.
  - Execute mutations as soon as parameters are resolved to avoid turn timeouts.
- **D1 Instruction & Context**:
  - Carry account IDs and requester tokens consistently across multi-app workflows.
- **D6 Output Validation**:
  - Verify that scalar responses (currency amounts, counts) are pure numbers without formatting symbols unless requested.
