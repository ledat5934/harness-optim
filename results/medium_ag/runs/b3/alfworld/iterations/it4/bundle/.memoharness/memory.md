# Rolling Memory

Updated after iteration 3.

- Read `./policy.json` first and use this file only for recent distilled lessons.
- Lesson from iter 3 failure (`pick_clean_then_place_in_recep-Apple-None-DiningTable-19`):
  Sequential searching through closed storage (e.g. numerous kitchen cabinets and drawers) exhausts the 50-step environment budget. Food items and produce typically spawn on open surfaces (diningtable, countertop) or in primary appliances (fridge).
- Verified repair heuristic: Enforce 3-phase search (Phase 1: open surfaces; Phase 2: appliances; Phase 3: closed storage only if exhausted). Record observed transformation tools (sinkbasin, microwave, fridge) and target receptacles to eliminate redundant search steps.
