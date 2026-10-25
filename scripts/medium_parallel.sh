#!/bin/bash
# MEDIUM protocol, one benchmark, process-parallel (same work as medium_chain.sh, shorter wall time):
#   stage 1: the 5 shared H0 phases (train rolls 1-3, val, test) as 5 processes
#   stage 2: B1, B2, B3 as 3 processes (they only read the shared H0 records)
# AppWorld must run sequentially inside one process, so separate processes are how it gets parallel.
#   bash scripts/medium_parallel.sh <alfworld|appworld|browsecomp_plus>      logs: results/medium/logs/<bench>_*.log
set -u
B=$1
case $B in alfworld) V=/root/hg-venv;; appworld) V=/root/aw-venv;; browsecomp_plus) V=/root/bcp-venv;; *) echo "bench?"; exit 2;; esac
R=$(cd "$(dirname "$0")/.." && pwd)
export ALFWORLD_DATA=${ALFWORLD_DATA:-/root/.cache/alfworld} APPWORLD_ROOT=${APPWORLD_ROOT:-/root/appworld_root}
export JAVA_HOME=${JAVA_HOME:-/usr/lib/jvm/java-21-openjdk-amd64} PYTHONPATH=$R PYTHONUNBUFFERED=1
L=$R/results/medium/logs; mkdir -p $L
cd $R
stage() {  # run each "name|args" in parallel, fail if any fails
  local pids=() names=() rc=0
  for job in "$@"; do
    n=${job%%|*}; a=${job#*|}
    "$V/bin/python" -W ignore $a > "$L/${B}_$n.log" 2>&1 & pids+=($!); names+=($n)
  done
  for i in "${!pids[@]}"; do
    wait ${pids[$i]} || { echo "FAILED ${names[$i]} (see $L/${B}_${names[$i]}.log)"; rc=1; }
  done
  return $rc
}
H="scripts/run_h0.py --protocol medium --bench $B --workers 4"
echo "== $(date +%T) H0 $B"
stage "h0_train1|$H --phase train --roll 1" "h0_train2|$H --phase train --roll 2" "h0_train3|$H --phase train --roll 3" \
      "h0_val|$H --phase val" "h0_test|$H --phase test" || exit 1
echo "== $(date +%T) baselines $B"
M="scripts/run_baselines.py --protocol medium --bench $B"
stage "b1|$M --method b1" "b2|$M --method b2" "b3|$M --method b3" || exit 1
echo "== $(date +%T) CHAIN_DONE $B"
