# Rolling Memory

Updated after iteration 2.

- D2 Protocol Enforcement: In iteration 1, `pick_heat_then_place_in_recep-Cup-None-Cabinet-15` failed on step 1 because the model emitted raw conversational text instead of invoking the native tool call API. Enforcing explicit tool invocation per turn prevents zero-tool turn stalls.
- Container State on Placement: Placing items into closed receptacles (e.g. cabinets, safes, fridges) fails unless opened first. Always open closed receptacles prior to both retrieval and insertion.
