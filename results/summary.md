# Results summary

> **SMOKE RUN, not statistically meaningful.** 3 test tasks per cell, 1 evolution round, 1 model (`inclusionai/ling-3.0-flash`). Differences between methods are within noise. BrowseComp-Plus is judged by our OpenRouter model, not Qwen3-32B, so it is not comparable with the public leaderboard.

> **Which runs use the current H0** (hash `c7e35268c202`, `docs/open_problems.md` item 13): the ALFWorld rows were produced after the tool-parser fix. The AppWorld and BrowseComp-Plus rows were produced before it, so they must be re-run (`scripts/run_smoke.sh`, which spends LLM budget) before they are compared with the ALFWorld rows.

Total spend so far (persistent ledger `results/spend.json`): **$0.5626** of $1.00, 7839 LLM calls, 54,391,924 prompt + 1,481,620 completion tokens.

## Test results (frozen harness, held-out test tasks)

| method | benchmark | test split | success | avg steps | avg tokens/episode | test cost (USD) | method total cost incl. evolution (USD) | errors |
|---|---|---|---|---|---|---|---|---|
| H0 (seed, no evolution) | alfworld | unseen | 3/3 (100%) | 26.7 | 49,993 | 0.0019 | shared runs (see below) | 0 |
| B1 Meta-Harness-style | alfworld | - | not run | | | | | |
| B2 ModularRSI-style | alfworld | - | not run | | | | | |
| B3 MemoHarness-style | alfworld | - | not run | | | | | |
| H0 (seed, no evolution) | appworld | test_normal | 0/3 (0%) | 39.3 | 346,791 | 0.0123 | shared runs (see below) | 0 |
| B1 Meta-Harness-style | appworld | - | not run | | | | | |
| B2 ModularRSI-style | appworld | - | not run | | | | | |
| B3 MemoHarness-style | appworld | - | not run | | | | | |
| H0 (seed, no evolution) | browsecomp_plus | test | 1/3 (33%) | 19.3 | 428,654 | 0.0106 | shared runs (see below) | 0 |
| B1 Meta-Harness-style | browsecomp_plus | - | not run | | | | | |
| B2 ModularRSI-style | browsecomp_plus | - | not run | | | | | |
| B3 MemoHarness-style | browsecomp_plus | - | not run | | | | | |

## H0 shared runs (train rolls / val / test)

| benchmark | phase | roll | success | avg steps | avg tokens | cost/episode (USD) | errors |
|---|---|---|---|---|---|---|---|
| alfworld | test | 1 | 3/3 | 26.7 | 49,993 | 0.00065 | 0 |
| alfworld | train | 1 | 4/5 | 29.0 | 53,571 | 0.00047 | 0 |
| alfworld | train | 2 | 4/5 | 31.0 | 58,242 | 0.00053 | 0 |
| alfworld | train | 3 | 2/5 | 39.0 | 84,768 | 0.00103 | 0 |
| alfworld | val | 1 | 3/3 | 16.0 | 21,714 | 0.00020 | 0 |
| appworld | test | 1 | 0/3 | 39.3 | 346,791 | 0.00410 | 0 |
| appworld | train | 1 | 1/5 | 28.0 | 139,245 | 0.00128 | 0 |
| appworld | train | 2 | 1/5 | 29.0 | 159,550 | 0.00133 | 0 |
| appworld | val | 1 | 0/3 | 40.0 | 228,993 | 0.00271 | 0 |
| browsecomp_plus | test | 1 | 1/3 | 19.3 | 428,654 | 0.00352 | 0 |
| browsecomp_plus | train | 1 | 1/5 | 25.0 | 544,600 | 0.00442 | 0 |
| browsecomp_plus | train | 2 | 1/5 | 21.8 | 453,243 | 0.00398 | 0 |
| browsecomp_plus | val | 1 | 0/3 | 24.7 | 606,881 | 0.00550 | 0 |

## Measured cost per episode (all agent episodes, incl. judge for BrowseComp-Plus)

| benchmark | episodes | mean cost/episode (USD) | mean tokens/episode | mean steps |
|---|---|---|---|---|
| alfworld | 21 | 0.00061 | 57,049 | 29.7 |
| appworld | 16 | 0.00209 | 201,333 | 32.7 |
| browsecomp_plus | 16 | 0.00432 | 505,989 | 22.9 |

## Spend by call type (tag prefix)

| tag prefix | calls | USD |
|---|---|---|
| h | 7492 | 0.52536 |
| b1:propose | 15 | 0.01149 |
| b2:investigate | 60 | 0.00923 |
| b2:implement | 16 | 0.00499 |
| b3:adapt | 45 | 0.00254 |
| trivial | 73 | 0.00200 |
| b3:diagnose | 16 | 0.00197 |
| b3:distill | 23 | 0.00143 |
| judge | 41 | 0.00139 |
| b3:controller | 11 | 0.00091 |
| b2:review | 11 | 0.00071 |
| b2:composer | 20 | 0.00047 |
| smoke_tool | 8 | 0.00009 |
| probe_reasoning | 4 | 0.00003 |
| smoke_plain | 4 | 0.00001 |

## Real-run budget estimate (from the measured cost per episode above)

| benchmark | measured $/episode | shared H0 eps | per-method evolution eps | test eps (H0 + methods) | total eps (x seeds) | est. USD |
|---|---|---|---|---|---|---|
| alfworld | 0.00061 | 350 | 520 | 1370 | 11,400 | 6.91 |
| appworld | 0.00209 | 320 | 520 | 2925 | 15,975 | 33.42 |
| browsecomp_plus | 0.00432 | 350 | 520 | 3400 | 17,490 | 75.51 |
| **total** | | | | | | **115.84** |

Assumptions: {"methods": 4, "rounds": 10, "train_tasks": 100, "train_rolls": 3, "val_tasks": 50, "check_execs": 2, "seeds": 3}; test sizes {"alfworld": 274, "appworld": 585, "browsecomp_plus": 680}. Non-episode LLM overhead measured in the smoke run was $0.0338 in total for all methods/benchmarks (all rounds incl. superseded attempts), i.e. < 10% of episode cost; budget +10% for it and for per-task composer/adaptation calls: **≈ $127.42**.

Open problems, caveats and the wall-time estimate: `docs/open_problems.md`. Fidelity of each baseline: `docs/baseline_fidelity.md`.
