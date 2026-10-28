# AlfWorld Policy Guidelines

## Action Execution Protocol
- Always execute actions via the native tool call API on every turn; never output action commands as raw text or markdown.
- Execute one admissible action per step matching the observed environment state.

## Task Execution Flow
- Locate target item -> take item -> transform if required (clean with sinkbasin, cool with fridge, heat with microwave, use desklamp) -> navigate to target receptacle -> put item in/on receptacle.
- For `pick_two_obj_and_place`, deliver the first item completely, then locate and deliver the second item.

## Phased Search Hierarchy
- Phase 1 (Open Surfaces): Check open surfaces first (diningtable, countertop, desk, table, bed, sofa). Everyday objects and produce are visible immediately without opening actions.
- Phase 2 (Appliances): Check category appliances (fridge for food/produce; microwave; sinkbasin).
- Phase 3 (Closed Storage): Check closed containers (cabinets, drawers, safe) only if the item was not found on open surfaces or appliances. Always open containers before taking or placing items.
- Spatial Memory: Note locations of transformation fixtures (sinkbasin, microwave, fridge) and target receptacles when first seen to navigate directly when needed.
- Avoid Search Cycles: Never re-examine receptacles that were already checked.

Bundle contract:
- Read `./policy.json` for the authoritative D1-D6 summary before using playbook or memory notes.
- Treat `./.memoharness/playbook.md` as stable repo heuristics and `./.memoharness/memory.md` as rolling distilled notes.
