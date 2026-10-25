#!/bin/bash
# usage: baseline_chain.sh <bench> <venv> <method> ...
B=$1; V=$2; shift 2
for m in "$@"; do
  bash /mnt/e/KLTN/scripts/wsl_run.sh $V python -W ignore scripts/run_baselines.py --bench $B --method $m 2>&1 \
    | grep -E "RESULT|Traceback|Error|error|budget\]|ok=" | grep -v WARNING
done
echo CHAIN_DONE $B
