# Repo Playbook

Use `./policy.json` as the authoritative D1-D6 summary.

## Core AlfWorld Execution Rules
1. Multi-Stage Planning:
   - Identify task goal and execute strictly in order: locate item -> take item -> transform (clean/cool/heat/light) -> place in target receptacle.
2. Search Prioritization:
   - Search the most probable receptacles first by category (e.g. food -> fridge/countertop/diningtable).
   - If an item is not found, systematically search remaining locations without re-visiting already-cleared receptacles.
3. State Verification:
   - Inspect container contents after opening.
   - Verify inventory holds the item before navigating to appliances or final receptacle.
   - For `pick_two`, complete placement of the first item before searching for the second.
