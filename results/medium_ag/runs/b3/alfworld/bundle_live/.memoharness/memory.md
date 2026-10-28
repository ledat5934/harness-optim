# Rolling Memory

Updated after iteration 4.

- All 30 tasks in iteration 4 passed (100% win rate), confirming the phased exploration hierarchy (open surfaces -> appliances -> closed containers) and history_keep=45 configuration.
- Flipping tasks stabilized:
  - `pick_clean_then_place_in_recep-Apple-None-DiningTable-19`: Succeeded cleanly in 15 turns without search looping by checking open surfaces before appliances and maintaining direct navigation to sinkbasin.
  - `pick_heat_then_place_in_recep-Cup-None-Cabinet-15`: Succeeded cleanly in 8 turns; remembered to open closed target cabinet before placement.
- Key invariants:
  - Deliver items sequentially in two-object tasks.
  - Never repeat checks of visited receptacles.
