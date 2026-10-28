# AlfWorld Policy Guidelines

## Action Execution Protocol
- Always execute actions via the native tool call API on every turn; never output action commands as raw text or markdown.
- Execute one admissible action per step matching the observed environment state.

## Task Goal & Plan Deconstruction
- `pick_and_place`: find item -> take item -> go to receptacle -> put item in/on receptacle.
- `pick_clean_then_place`: find item -> take item -> go to sinkbasin -> clean item with sinkbasin -> go to receptacle -> put item in/on receptacle.
- `pick_cool_then_place`: find item -> take item -> go to fridge -> cool item with fridge -> go to receptacle -> put item in/on receptacle.
- `pick_heat_then_place`: find item -> take item -> go to microwave -> heat item with microwave -> go to receptacle -> put item in/on receptacle.
- `look_at_obj_in_light`: find item -> take item -> go to desklamp -> use desklamp.
- `pick_two_obj_and_place`: complete pick and place for first object, then repeat for second object.

## Search & Container Heuristics
- Check common receptacles first: food in fridge/table/counter; tableware/cups on counter/table/sink/cabinet; items on desk/bed/sofa.
- Avoid search cycles: do not re-check empty or already-inspected receptacles.
- Open closed containers (cabinet, fridge, microwave, drawer, safe) before taking items out or placing items in.

Bundle contract:
- Read `./policy.json` for the authoritative D1-D6 summary before using playbook or memory notes.
- Treat `./.memoharness/playbook.md` as stable repo heuristics and `./.memoharness/memory.md` as rolling distilled notes.
