# MEDIUM run: results

1 seed; 5 evolution rounds; 50 train tasks x 3 rolls; 30 val tasks (B1 only; B2 promotes on gates, B3 selects on train runs, as in their references); fixed 100-task test subsets. Model `cx/gpt-6-luna` for agent, proposers and the BrowseComp-Plus judge. Infra-error episodes count as failures. McNemar: exact, two-sided, on tasks where exactly one of the two methods succeeded.

## alfworld

Test subset: 100 tasks (`benchmarks/alfworld/test100.json`).

| method | test episodes | success | 95% CI | vs H0 (win/loss) | McNemar p | tokens/ep | $/ep | $/success | infra errors | proposer $ | evolution episodes $ |
|---|---|---|---|---|---|---|---|---|---|---|---|
| h0 | 100 | 87.0% (87) | 79.0%–92.2% | – | – | 52,538 | 0.00000 | 0.00000 | 0 | 0.000 | 0.000 |
| b1 | 100 | 90.0% (90) | 82.6%–94.5% | +7 / −4 | 0.549 | 48,910 | 0.00000 | 0.00000 | 0 | 0.000 | 0.000 |
| b2 | 100 | 90.0% (90) | 82.6%–94.5% | +6 / −3 | 0.508 | 45,025 | 0.00000 | 0.00000 | 0 | 0.000 | 0.000 |
| b3 | 100 | 94.0% (94) | 87.5%–97.2% | +8 / −1 | 0.039 | 115,162 | 0.00000 | 0.00000 | 0 | 0.000 | 0.000 |

Success per task type:

| method | look at obj in light | pick and place simple | pick clean then place in recep | pick cool then place in recep | pick heat then place in recep | pick two obj and place |
|---|---|---|---|---|---|---|
| h0 | 13/13 | 17/18 | 21/23 | 15/16 | 11/17 | 10/13 |
| b1 | 13/13 | 17/18 | 19/23 | 16/16 | 12/17 | 13/13 |
| b2 | 13/13 | 17/18 | 20/23 | 16/16 | 13/17 | 11/13 |
| b3 | 13/13 | 18/18 | 21/23 | 16/16 | 13/17 | 13/13 |

Evolution (per round):

- H0 val: 80.0% (30 tasks)
- b1: r1: kept incumbent (val 73.3%); r2: new incumbent (val 80.0%); r3: kept incumbent (val 73.3%); r4: kept incumbent (val 80.0%); r5: kept incumbent (val 73.3%) -> final: /home/user/harness-optim/results/medium_luna/runs/b1/alfworld/candidates/r2
- b2: r1: no open proposal; r2: no open proposal; r3: no open proposal; r4: no open proposal; r5: no open proposal -> final: /home/user/harness-optim/h0
- b3 iteration 0 (H0, K rolls) train reward: 86.7%
- b3: r1: passed canary [canary: accepted by canary gate] -> train run of r1: 83.3%; r2: passed canary [canary: accepted by canary gate] -> train run of r2: 86.7%; r3: passed canary [canary: accepted by canary gate] -> train run of r3: 80.0%; r4: passed canary [canary: accepted by canary gate] -> train run of r4: 90.0%; r5: passed canary [canary: accepted by canary gate] -> train run of r5: 86.7% -> final: r4 (iteration 4, train 90.0%)

## appworld

Test subset: 99 tasks (`benchmarks/appworld/test100.json`).

| method | test episodes | success | 95% CI | vs H0 (win/loss) | McNemar p | tokens/ep | $/ep | $/success | infra errors | proposer $ | evolution episodes $ |
|---|---|---|---|---|---|---|---|---|---|---|---|
| h0 | 99 | 74.7% (74) | 65.4%–82.3% | – | – | 85,163 | 0.00000 | 0.00000 | 0 | 0.000 | 0.000 |
| b1 | 99 | 77.8% (77) | 68.6%–84.8% | +8 / −5 | 0.581 | 98,906 | 0.00000 | 0.00000 | 0 | 0.000 | 0.000 |
| b2 | 99 | 74.7% (74) | 65.4%–82.3% | +6 / −6 | 1.000 | 87,599 | 0.00000 | 0.00000 | 0 | 0.000 | 0.000 |
| b3 | 99 | 75.8% (75) | 66.5%–83.1% | +7 / −6 | 1.000 | 139,374 | 0.00000 | 0.00000 | 0 | 0.000 | 0.000 |

| method | TGC | SGC | mean fraction of unit tests passed | task_completed called |
|---|---|---|---|---|
| h0 | 74.7% | 63.6% (33 scenarios) | 89.2% | 99/99 |
| b1 | 77.8% | 66.7% (33 scenarios) | 90.5% | 99/99 |
| b2 | 74.7% | 57.6% (33 scenarios) | 89.4% | 99/99 |
| b3 | 75.8% | 63.6% (33 scenarios) | 88.1% | 99/99 |

Evolution (per round):

- H0 val: 70.0% (30 tasks)
- b1: r1: new incumbent (val 73.3%); r2: kept incumbent (val 70.0%); r3: kept incumbent (val 66.7%); r4: kept incumbent (val 70.0%); r5: kept incumbent (val 60.0%) -> final: /home/user/harness-optim/results/medium_luna/runs/b1/appworld/candidates/r1
- b2: r1: no open proposal; r2: no open proposal; r3: no open proposal; r4: no open proposal; r5: no open proposal -> final: /home/user/harness-optim/h0
- b3 iteration 0 (H0, K rolls) train reward: 71.1%
- b3: r1: passed canary [canary: accepted by canary gate] -> train run of r1: 66.7%; r2: passed canary [canary: accepted by canary gate] -> train run of r2: 83.3%; r3: passed canary [canary: accepted by canary gate] -> train run of r3: 70.0%; r4: rejected by canary [canary: reward delta -0.500 < threshold -0.340] -> train run of r3: 60.0%; r5: rejected by canary [canary: reward delta -0.500 < threshold -0.340] -> train run of r3: 80.0% -> final: r2 (iteration 2, train 83.3%)

## browsecomp_plus

Test subset: 100 tasks (`benchmarks/browsecomp_plus/test100.json`).

| method | test episodes | success | 95% CI | vs H0 (win/loss) | McNemar p | tokens/ep | $/ep | $/success | infra errors | proposer $ | evolution episodes $ |
|---|---|---|---|---|---|---|---|---|---|---|---|
| h0 | 100 | 24.0% (24) | 16.7%–33.2% | – | – | 24,339 | 0.00000 | 0.00000 | 0 | 0.000 | 0.000 |
| b1 | 100 | 28.0% (28) | 20.1%–37.5% | +10 / −6 | 0.454 | 48,806 | 0.00000 | 0.00000 | 0 | 0.000 | 0.000 |
| b2 | 100 | 23.0% (23) | 15.8%–32.2% | +8 / −9 | 1.000 | 23,369 | 0.00000 | 0.00000 | 0 | 0.000 | 0.000 |
| b3 | 100 | 21.0% (21) | 14.2%–30.0% | +7 / −10 | 0.629 | 39,316 | 0.00000 | 0.00000 | 0 | 0.000 | 0.000 |

| method | accuracy | mean search calls | mean get_document calls | no answer submitted |
|---|---|---|---|---|
| h0 | 24.0% | 4.1 | 0.4 | 0/100 |
| b1 | 28.0% | 5.5 | 0.4 | 0/100 |
| b2 | 23.0% | 4.1 | 0.3 | 0/100 |
| b3 | 21.0% | 4.4 | 0.3 | 0/100 |

Evolution (per round):

- H0 val: 13.3% (30 tasks)
- b1: r1: kept incumbent (val 6.7%); r2: new incumbent (val 26.7%); r3: new incumbent (val 30.0%); r4: kept incumbent (val 23.3%); r5: kept incumbent (val 13.3%) -> final: /home/user/harness-optim/results/medium_luna/runs/b1/browsecomp_plus/candidates/r3
- b2: r1: no open proposal; r2: no open proposal; r3: no open proposal; r4: no open proposal; r5: no open proposal -> final: /home/user/harness-optim/h0
- b3 iteration 0 (H0, K rolls) train reward: 13.3%
- b3: r1: passed canary [canary: accepted by canary gate] -> train run of r1: 20.0%; r2: passed canary [canary: accepted by canary gate] -> train run of r2: 26.7%; r3: passed canary [canary: accepted by canary gate] -> train run of r3: 13.3%; r4: passed canary [canary: accepted by canary gate] -> train run of r4: 13.3%; r5: passed canary [canary: accepted by canary gate] -> train run of r5: 13.3% -> final: r2 (iteration 2, train 26.7%)

Spend: $0 metered (every call went through a subscription gateway; cost columns are 0).
