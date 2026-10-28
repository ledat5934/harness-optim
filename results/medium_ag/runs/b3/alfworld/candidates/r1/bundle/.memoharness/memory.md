# Rolling Memory

Updated after iteration 1.

- Iteration 0 baseline: 149/150 tasks solved (99.3%).
- Identified failure mode in `pick_clean_then_place_in_recep-Apple-None-DiningTable-19`:
  - Step budget exhaustion during unguided exhaustive cabinet search for food items.
  - Prevention: prioritize primary containers (fridge, countertop, diningtable) for perishables before searching secondary storage.
  - Memory capacity: increased history_keep to 45 so long-horizon searches (30+ turns) do not lose track of visited containers and target locations.
