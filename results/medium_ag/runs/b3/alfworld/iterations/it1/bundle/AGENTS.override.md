# AlfWorld Policy Guidelines

## Task Goal & Plan Deconstruction
- Identify the goal structure and execute stage by stage:
  - `pick_and_place`: find item -> take item -> go to target receptacle -> put item in/on target.
  - `pick_clean_then_place`: find item -> take item -> go to sinkbasin -> clean item with sinkbasin -> go to target receptacle -> put item.
  - `pick_cool_then_place`: find item -> take item -> go to fridge -> cool item with fridge -> go to target receptacle -> put item.
  - `pick_heat_then_place`: find item -> take item -> go to microwave -> heat item with microwave -> go to target receptacle -> put item.
  - `look_at_obj_in_light`: find item -> take item -> go to desklamp -> use desklamp.
  - `pick_two_obj_and_place`: execute pick and place for first object, then find, take, and place second object.

## Search Heuristics
- Check high-probability locations first instead of unguided cabinet-by-cabinet searching:
  - Food / Perishables (apple, egg, lettuce, bread): check fridge, countertop, diningtable, sinkbasin before closed cabinets or drawers.
  - Tableware / Cookware (cup, mug, bowl, kettle, knife): countertop, diningtable, sinkbasin, dishwasher, cabinets.
  - Bedroom / Office items (phone, book, creditcard, alarmclock, cd, pencil): desk, sidetable, coffeetable, bed, armchair, sofa.
  - Toiletries / Cleaning (cloth, sponge, soapbar, tissuebox): countertop, sinkbasin, toilet, shelf.
- Avoid search loops: remember inspected locations; do not re-open or re-examine empty receptacles.
- Open closed containers (fridge, microwave, cabinet, drawer, safe) before attempting to take items inside.
