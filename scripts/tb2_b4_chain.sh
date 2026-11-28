#!/usr/bin/env bash
# Our pipeline on the small TB2 protocol (tb2small): H0 train x K rolls, H0 val x H0_VAL_ROLLS, then B4 v7 with the
# b4v7s settings (decisive-mistake clusters, learnable-first, regression sentinel). The H0 test runs come from
# scripts/tb2_compete.sh (arm h0), so every arm is graded on the same test tasks. Resume-safe (done markers).
# Usage: tb2_b4_chain.sh [workers]
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
W="${1:-2}"; O=results/tb2small; mkdir -p "$O/logs"
export PYTHONPATH="$ROOT" PYTHONUNBUFFERED=1
VR="${H0_VAL_ROLLS:-2}"
if [ ! -f "$O/logs/h0trainval.done" ]; then
  for pass in 1 2; do  # second pass only redoes infra errors
    for ro in 1 2; do python3 -W ignore scripts/run_h0.py --protocol tb2small --bench terminal_bench2 --workers "$W" \
      --phase train --roll "$ro" --redo-errors >> "$O/logs/h0_terminal_bench2.log" 2>&1; done
    for ro in $(seq 1 "$VR"); do python3 -W ignore scripts/run_h0.py --protocol tb2small --bench terminal_bench2 \
      --workers "$W" --phase val --roll "$ro" --redo-errors >> "$O/logs/h0_terminal_bench2.log" 2>&1; done
  done
  touch "$O/logs/h0trainval.done"; echo PHASE_DONE h0 train/val
fi
# B4 evolves on train/val now; its final test waits for the H0 test records of the compare driver
if [ ! -f "$O/logs/b4_terminal_bench2.done" ]; then
  B4_TEST_WAIT=results/tb2/compete_test.log:ALL_DONE B4_PROTOCOL=tb2small B4_COMP=1 B4_RESUME=1 B4_TAG="${B4_TAG:-b4tb2}" B4_SEED=0 B4_ROUNDS="${B4_ROUNDS:-2}" B4_LEARN=1 \
    B4_SENTINEL=1 B4_CLUSTER=1 H0_VAL_ROLLS="$VR" B4_K_VAL=2 \
    python3 -W ignore scripts/run_b4_cmp.py terminal_bench2 >> "$O/logs/b4_terminal_bench2.log" 2>&1 \
    && touch "$O/logs/b4_terminal_bench2.done" && echo PHASE_DONE b4
fi
echo CHAIN_DONE
