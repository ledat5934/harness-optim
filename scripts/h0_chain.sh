#!/bin/bash
# usage: h0_chain.sh <bench> <venv> <phase:roll> ...
B=$1; V=$2; shift 2
for pr in "$@"; do
  ph=${pr%%:*}; ro=${pr##*:}
  bash /mnt/e/KLTN/scripts/wsl_run.sh $V python -W ignore scripts/run_h0.py --bench $B --phase $ph --roll $ro 2>&1 | grep -E "SUMMARY|Traceback|Error|budget\]" | grep -v "WARNING"
done
echo CHAIN_DONE $B
