# Rolling Memory

Updated after iteration 2 (30/30 tasks solved, 100% pass rate).

- Read `./policy.json` first and use this file only for recent distilled lessons.
- Both previously flipping tasks (`pick_clean_then_place_in_recep-Apple-None-DiningTable-19` and `pick_heat_then_place_in_recep-Cup-None-Cabinet-15`) passed consistently.
- Key factors for stability:
  1. Opening containers (cabinets, microwave, fridge) before taking or placing items prevents invalid receptacle interactions.
  2. The 45-turn history window prevents search cycles across multi-step transform-and-place tasks.
  3. Deterministic greedy tool calling (T=0.0) avoids hallucinated actions.
