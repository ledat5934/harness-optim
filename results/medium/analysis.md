# MEDIUM run: results

1 seed; 5 evolution rounds; 50 train tasks x 3 rolls; 30 val tasks (B1 only; B2 promotes on gates, B3 selects on train runs, as in their references); fixed 100-task test subsets. Model `inclusionai/ling-3.0-flash` for agent, proposers and the BrowseComp-Plus judge. Infra-error episodes count as failures. McNemar: exact, two-sided, on tasks where exactly one of the two methods succeeded.

## alfworld

Test subset: 100 tasks (`benchmarks/alfworld/test100.json`).

| method | test episodes | success | 95% CI | vs H0 (win/loss) | McNemar p | tokens/ep | $/ep | $/success | infra errors | proposer $ | evolution episodes $ |
|---|---|---|---|---|---|---|---|---|---|---|---|
| h0 | 100 | 73.0% (73) | 63.6%–80.7% | – | – | 62,608 | 0.00066 | 0.00091 | 0 | 0.000 | 0.130 |
| b1 | 100 | 86.0% (86) | 77.9%–91.5% | +18 / −5 | 0.011 | 51,392 | 0.00054 | 0.00063 | 0 | 0.050 | 0.146 |
| b2 | 100 | 60.0% (60) | 50.2%–69.1% | +8 / −21 | 0.024 | 69,220 | 0.00081 | 0.00135 | 0 | 0.144 | 0.083 |
| b3 | 100 | 65.0% (65) | 55.3%–73.6% | +9 / −17 | 0.169 | 140,857 | 0.00111 | 0.00170 | 0 | 0.074 | 0.138 |

Success per task type:

| method | look at obj in light | pick and place simple | pick clean then place in recep | pick cool then place in recep | pick heat then place in recep | pick two obj and place |
|---|---|---|---|---|---|---|
| h0 | 12/13 | 15/18 | 19/23 | 13/16 | 10/17 | 4/13 |
| b1 | 13/13 | 17/18 | 17/23 | 14/16 | 15/17 | 10/13 |
| b2 | 11/13 | 12/18 | 16/23 | 7/16 | 9/17 | 5/13 |
| b3 | 12/13 | 13/18 | 13/23 | 11/16 | 12/17 | 4/13 |

Run-to-run noise: a second run of a behaviourally identical harness (`results/medium/aborted_argvalue/b1_alfworld.jsonl`) on the same 100 tasks: 69.0% vs H0 73.0% (13 tasks flip to pass, 17 to fail).

Evolution (per round):

- H0 val: 46.7% (30 tasks)
- b1: r1: new incumbent (val 66.7%); r2: kept incumbent (val 56.7%); r3: kept incumbent (val 63.3%); r4: kept incumbent (val 56.7%); r5: new incumbent (val 70.0%) -> final: /home/user/harness-optim/results/medium/runs/b1/alfworld/candidates/r5
- b2: r1: no open proposal; r2: promoted [['verifier', 'goal_satisfied']]; r3: no open proposal; r4: no variant passed the gates; r5: promoted [['context_mgmt', 'milestone_compressor']] -> final: /home/user/harness-optim/results/medium/runs/b2/alfworld/candidates/r5
- b3 iteration 0 (H0, K rolls) train reward: 65.6%
- b3: r1: passed canary [canary: accepted by canary gate] -> train run of r1: 76.7%; r2: rejected by canary [canary: reward delta -0.500 < threshold -0.340] -> train run of r1: 66.7%; r3: rejected by canary [canary: reward delta -0.500 < threshold -0.340] -> train run of r1: 73.3%; r4: passed canary [canary: accepted by canary gate] -> train run of r4: 83.3%; r5: passed canary [canary: accepted by canary gate] -> train run of r5: 73.3% -> final: r4 (iteration 4, train 83.3%)

## appworld

Test subset: 99 tasks (`benchmarks/appworld/test100.json`).

| method | test episodes | success | 95% CI | vs H0 (win/loss) | McNemar p | tokens/ep | $/ep | $/success | infra errors | proposer $ | evolution episodes $ |
|---|---|---|---|---|---|---|---|---|---|---|---|
| h0 | 99 | 6.1% (6) | 2.8%–12.6% | – | – | 185,585 | 0.00198 | 0.03261 | 0 | 0.000 | 0.405 |
| b1 | 99 | 6.1% (6) | 2.8%–12.6% | +2 / −2 | 1.000 | 185,322 | 0.00190 | 0.03129 | 1 | 0.064 | 0.185 |
| b2 | 99 | 2.0% (2) | 0.6%–7.1% | +0 / −4 | 0.125 | 218,083 | 0.00257 | 0.12715 | 0 | 0.182 | 0.280 |
| b3 | 99 | 8.1% (8) | 4.2%–15.1% | +2 / −0 | 0.500 | 274,895 | 0.00327 | 0.04051 | 0 | 0.098 | 0.393 |

| method | TGC | SGC | mean fraction of unit tests passed | task_completed called |
|---|---|---|---|---|
| h0 | 6.1% | 6.1% (33 scenarios) | 50.1% | 54/99 |
| b1 | 6.1% | 3.0% (33 scenarios) | 52.9% | 55/99 |
| b2 | 2.0% | 0.0% (33 scenarios) | 39.0% | 35/99 |
| b3 | 8.1% | 6.1% (33 scenarios) | 58.3% | 68/99 |

Run-to-run noise: a second run of a behaviourally identical harness (`results/medium/aborted_unselected/b1_appworld.jsonl`) on the same 66 tasks: 4.5% vs H0 4.5% (0 tasks flip to pass, 0 to fail).

Evolution (per round):

- H0 val: 3.3% (30 tasks)
- b1: r1: smoke crash; r2: new incumbent (val 6.7%); r3: new incumbent (val 10.0%); r4: rejected at validation; r5: new incumbent (val 13.3%) -> final: /home/user/harness-optim/results/medium/runs/b1/appworld/candidates/r5
- b2: r1: promoted [['verifier', 'complete_album_coverage']]; r2: no variant passed the gates; r3: execution check crashed [['agent_loop', 'token_propagating'], ['memory', 'persistent']]; r4: promoted [['agent_loop', 'repetition_breaker']]; r5: promoted [['agent_loop', 'repetition_breaker'], ['agent_loop', 'todo_error_aware']] -> final: /home/user/harness-optim/results/medium/runs/b2/appworld/candidates/r5
- b3 iteration 0 (H0, K rolls) train reward: 12.2%
- b3: r1: passed canary [canary: accepted by canary gate] -> train run of r1: 10.0%; r2: passed canary [canary: accepted by canary gate] -> train run of r2: 13.3%; r3: passed canary [canary: accepted by canary gate] -> train run of r3: 10.0%; r4: passed canary [canary: accepted by canary gate] -> train run of r4: 16.7%; r5: passed canary [canary: accepted by canary gate] -> train run of r5: 23.3% -> final: r5 (iteration 5, train 23.3%)

## browsecomp_plus

Test subset: 100 tasks (`benchmarks/browsecomp_plus/test100.json`).

| method | test episodes | success | 95% CI | vs H0 (win/loss) | McNemar p | tokens/ep | $/ep | $/success | infra errors | proposer $ | evolution episodes $ |
|---|---|---|---|---|---|---|---|---|---|---|---|
| h0 | 100 | 17.0% (17) | 10.9%–25.5% | – | – | 526,451 | 0.00471 | 0.02771 | 0 | 0.000 | 0.828 |
| b1 | 100 | 21.0% (21) | 14.2%–30.0% | +8 / −4 | 0.388 | 504,911 | 0.00437 | 0.02083 | 0 | 0.076 | 0.419 |
| b2 | 100 | 23.0% (23) | 15.8%–32.2% | +14 / −8 | 0.286 | 480,693 | 0.00482 | 0.02095 | 0 | 0.210 | 0.562 |
| b3 | 100 | 18.0% (18) | 11.7%–26.7% | +7 / −6 | 1.000 | 477,542 | 0.00699 | 0.03882 | 0 | 0.116 | 0.747 |

| method | accuracy | mean search calls | mean get_document calls | no answer submitted |
|---|---|---|---|---|
| h0 | 17.0% | 22.1 | 0.4 | 13/100 |
| b1 | 21.0% | 21.7 | 0.5 | 12/100 |
| b2 | 23.0% | 20.2 | 0.3 | 17/100 |
| b3 | 18.0% | 21.6 | 0.6 | 22/100 |

Run-to-run noise: a second run of a behaviourally identical harness (`results/medium/aborted_unselected/b1_browsecomp_plus.jsonl`) on the same 100 tasks: 21.0% vs H0 17.0% (7 tasks flip to pass, 3 to fail).

Evolution (per round):

- H0 val: 13.3% (30 tasks)
- b1: r1: kept incumbent (val 13.3%); r2: new incumbent (val 20.0%); r3: smoke crash; r4: proposer returned no candidate; r5: kept incumbent (val 16.7%) -> final: /home/user/harness-optim/results/medium/runs/b1/browsecomp_plus/candidates/r2
- b2: r1: no variant passed the gates; r2: promoted [['verifier', 'completeness']]; r3: promoted [['verifier', 'completeness']]; r4: execution check crashed [['agent_loop', 'planned_react']]; r5: promoted [['agent_loop', 'todo_plan']] -> final: /home/user/harness-optim/results/medium/runs/b2/browsecomp_plus/candidates/r5
- b3 iteration 0 (H0, K rolls) train reward: 11.1%
- b3: r1: passed canary [canary: accepted by canary gate] -> train run of r1: 20.0%; r2: passed canary [canary: accepted by canary gate] -> train run of r2: 26.7%; r3: passed canary [canary: accepted by canary gate] -> train run of r3: 20.0%; r4: passed canary [canary: accepted by canary gate] -> train run of r4: 20.0%; r5: passed canary [canary: accepted by canary gate] -> train run of r5: 16.7% -> final: r2 (iteration 2, train 26.7%)

Total spend of the MEDIUM run: $15.35 (spend.json total $15.92).
