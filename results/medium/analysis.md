# MEDIUM run: results

1 seed; 5 evolution rounds; 50 train tasks x 3 rolls; 30 val tasks; fixed 100-task test subsets. Model `inclusionai/ling-3.0-flash` for agent, proposers and the BrowseComp-Plus judge. Infra-error episodes count as failures. McNemar: exact, two-sided, on tasks where exactly one of the two methods succeeded.

## alfworld

Test subset: 100 tasks (`benchmarks/alfworld/test100.json`).

| method | test episodes | success | 95% CI | vs H0 (win/loss) | McNemar p | tokens/ep | $/ep | $/success | infra errors | proposer $ | evolution episodes $ |
|---|---|---|---|---|---|---|---|---|---|---|---|
| h0 | 100 | 73.0% (73) | 63.6%–80.7% | – | – | 62,608 | 0.00066 | 0.00091 | 0 | 0.000 | 0.130 |
| b1 | 100 | 86.0% (86) | 77.9%–91.5% | +18 / −5 | 0.011 | 51,392 | 0.00054 | 0.00063 | 0 | 0.050 | 0.146 |
| b2 | 100 | 70.0% (70) | 60.4%–78.1% | +11 / −14 | 0.690 | 67,054 | 0.00072 | 0.00104 | 0 | 0.071 | 0.057 |
| b3 | 100 | 81.0% (81) | 72.2%–87.5% | +18 / −10 | 0.185 | 52,457 | 0.00060 | 0.00074 | 0 | 0.043 | 0.101 |

Success per task type:

| method | look at obj in light | pick and place simple | pick clean then place in recep | pick cool then place in recep | pick heat then place in recep | pick two obj and place |
|---|---|---|---|---|---|---|
| h0 | 12/13 | 15/18 | 19/23 | 13/16 | 10/17 | 4/13 |
| b1 | 13/13 | 17/18 | 17/23 | 14/16 | 15/17 | 10/13 |
| b2 | 10/13 | 12/18 | 21/23 | 11/16 | 12/17 | 4/13 |
| b3 | 12/13 | 16/18 | 18/23 | 14/16 | 14/17 | 7/13 |

Run-to-run noise: a second run of a behaviourally identical harness (`results/medium/aborted_argvalue/b1_alfworld.jsonl`) on the same 100 tasks: 69.0% vs H0 73.0% (13 tasks flip to pass, 17 to fail).

Evolution (per round):

- H0 val: 46.7% (30 tasks)
- b1: r1: new incumbent (val 66.7%); r2: kept incumbent (val 56.7%); r3: kept incumbent (val 63.3%); r4: kept incumbent (val 56.7%); r5: new incumbent (val 70.0%) -> final: /home/user/harness-optim/results/medium/runs/b1/alfworld/candidates/r5
- b2: r1: no open proposal; r2: promoted (val 50.0%); r3: kept incumbent (val 46.7%); r4: no open proposal; r5: no open proposal -> final: /home/user/harness-optim/results/medium/runs/b2/alfworld/candidates/r2
- b3: r1: rejected by canary [canary: success rate dropped too much (-0.500) without reward gain]; r2: passed canary [canary: accepted by canary gate]; r3: passed canary [canary: accepted by canary gate]; r4: passed canary [canary: accepted by canary gate]; r5: passed canary [canary: accepted by canary gate] -> final: r5

## appworld

Test subset: 99 tasks (`benchmarks/appworld/test100.json`).

| method | test episodes | success | 95% CI | vs H0 (win/loss) | McNemar p | tokens/ep | $/ep | $/success | infra errors | proposer $ | evolution episodes $ |
|---|---|---|---|---|---|---|---|---|---|---|---|
| h0 | 99 | 6.1% (6) | 2.8%–12.6% | – | – | 185,585 | 0.00198 | 0.03261 | 0 | 0.000 | 0.405 |
| b1 | 0 | – | – | – | – | – | – | – | – | – | – |
| b2 | 99 | 4.0% (4) | 1.6%–9.9% | +0 / −2 | 0.500 | 182,579 | 0.00192 | 0.04759 | 0 | 0.054 | 0.128 |
| b3 | 57 | 7.0% (4) | 2.8%–16.7% | +2 / −1 | 1.000 | 159,687 | 0.00256 | 0.03641 | 0 | 0.029 | 0.417 |

| method | TGC | SGC | mean fraction of unit tests passed | task_completed called |
|---|---|---|---|---|
| h0 | 6.1% | 6.1% (33 scenarios) | 50.1% | 54/99 |
| b2 | 4.0% | 0.0% (33 scenarios) | 49.4% | 53/99 |
| b3 | 7.0% | 0.0% (19 scenarios) | 51.5% | 32/57 |

Run-to-run noise: a second run of a behaviourally identical harness (`results/medium/aborted_unselected/b1_appworld.jsonl`) on the same 66 tasks: 4.5% vs H0 4.5% (0 tasks flip to pass, 0 to fail).

Evolution (per round):

- H0 val: 3.3% (30 tasks)
- b1: (no log.json, run stopped early) val per candidate: 
- b2: r1: kept incumbent (val 0.0%); r2: no variant passed the gates; r3: no variant passed the gates; r4: promoted (val 13.3%); r5: no variant passed the gates -> final: /home/user/harness-optim/results/medium/runs/b2/appworld/candidates/r4
- b3: (no log.json, run stopped early) val per candidate: r1: 3.3% (30), r2: 13.3% (30), r3: 16.7% (30), r4: 13.3% (30), r5: 6.7% (30)

## browsecomp_plus

Test subset: 100 tasks (`benchmarks/browsecomp_plus/test100.json`).

| method | test episodes | success | 95% CI | vs H0 (win/loss) | McNemar p | tokens/ep | $/ep | $/success | infra errors | proposer $ | evolution episodes $ |
|---|---|---|---|---|---|---|---|---|---|---|---|
| h0 | 100 | 17.0% (17) | 10.9%–25.5% | – | – | 526,451 | 0.00471 | 0.02771 | 0 | 0.000 | 0.828 |
| b1 | 0 | – | – | – | – | – | – | – | – | – | – |
| b2 | 100 | 15.0% (15) | 9.3%–23.3% | +3 / −5 | 0.727 | 496,825 | 0.00451 | 0.03010 | 0 | 0.075 | 0.446 |
| b3 | 100 | 18.0% (18) | 11.7%–26.7% | +7 / −6 | 1.000 | 391,958 | 0.00685 | 0.03806 | 0 | 0.048 | 1.109 |

| method | accuracy | mean search calls | mean get_document calls | no answer submitted |
|---|---|---|---|---|
| h0 | 17.0% | 22.1 | 0.4 | 13/100 |
| b2 | 15.0% | 21.4 | 0.4 | 9/100 |
| b3 | 18.0% | 21.6 | 0.5 | 15/100 |

Run-to-run noise: a second run of a behaviourally identical harness (`results/medium/aborted_unselected/b1_browsecomp_plus.jsonl`) on the same 100 tasks: 21.0% vs H0 17.0% (7 tasks flip to pass, 3 to fail).

Evolution (per round):

- H0 val: 13.3% (30 tasks)
- b1: (no log.json, run stopped early) val per candidate: 
- b2: r1: kept incumbent (val 3.3%); r2: promoted (val 16.7%); r3: kept incumbent (val 10.0%); r4: no open proposal; r5: no open proposal -> final: /home/user/harness-optim/results/medium/runs/b2/browsecomp_plus/candidates/r2
- b3: r1: passed canary [canary: accepted by canary gate]; r2: passed canary [canary: accepted by canary gate]; r3: passed canary [canary: accepted by canary gate]; r4: passed canary [canary: accepted by canary gate]; r5: passed canary [canary: accepted by canary gate] -> final: r5

Total spend of the MEDIUM run: $9.39 (spend.json total $9.96).
