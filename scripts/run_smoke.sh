#!/bin/bash
# HarnessGraph comparison harness: full SMOKE run (run inside WSL Ubuntu-HG, from the repo root).
#   bash scripts/run_smoke.sh            # everything
#   bash scripts/run_smoke.sh alfworld   # one benchmark
# From Windows: wsl -d Ubuntu-HG -u root -- bash /mnt/e/KLTN/scripts/run_smoke.sh alfworld
# Every python entry point prints the remaining budget first and exits(3) if < 20% of MAX_USD remains
# (persistent ledger: results/spend.json).
set -e
cd "$(dirname "$0")/.."
R="bash scripts/wsl_run.sh"
[ "${DRY_RUN:-0}" = "1" ] && R="echo bash scripts/wsl_run.sh"   # DRY_RUN=1: print the commands only
venv_of() { case $1 in alfworld) echo hg;; appworld) echo aw;; browsecomp_plus) echo bcp;; esac; }
BENCHES=${1:-"alfworld appworld browsecomp_plus"}

for B in $BENCHES; do
  V=$(venv_of $B)
  # --- shared H0 runs (same seed, same tasks; executed once, reused by every method) ---
  $R $V python scripts/run_h0.py --bench $B --phase train --roll 1   # Phase 3 smoke (5 tasks)
  $R $V python scripts/run_h0.py --bench $B --phase train --roll 2   # 2nd roll -> contrastive groups
  $R $V python scripts/run_h0.py --bench $B --phase val
  $R $V python scripts/run_h0.py --bench $B --phase test             # H0 row of the summary table
  # --- baselines (1 round, 2 check + 3 val executions each, frozen before 3 test executions) ---
  $R $V python scripts/run_baselines.py --bench $B --method b1       # Meta-Harness-style free-form
  $R $V python scripts/run_baselines.py --bench $B --method b2       # ModularRSI-style modular + composer
  $R $V python scripts/run_baselines.py --bench $B --method b3       # MemoHarness-style bank + adaptation
done
$R hg python scripts/summarize.py
