#!/bin/bash
# MEDIUM protocol, one benchmark: shared H0 (train rolls 1-3, val, test100), then B1, B2, B3.
#   bash scripts/medium_chain.sh <alfworld|appworld|browsecomp_plus>
# Venvs: /root/hg-venv (ALFWorld), /root/aw-venv (AppWorld), /root/bcp-venv (BrowseComp-Plus). Logs: results/medium/logs/.
set -u
B=$1
case $B in alfworld) V=/root/hg-venv;; appworld) V=/root/aw-venv;; browsecomp_plus) V=/root/bcp-venv;; *) echo "bench?"; exit 2;; esac
R=$(cd "$(dirname "$0")/.." && pwd)
export ALFWORLD_DATA=${ALFWORLD_DATA:-/root/.cache/alfworld} APPWORLD_ROOT=${APPWORLD_ROOT:-/root/appworld_root}
export JAVA_HOME=${JAVA_HOME:-/usr/lib/jvm/java-21-openjdk-amd64} PYTHONPATH=$R PYTHONUNBUFFERED=1
L=$R/results/medium/logs; mkdir -p $L
cd $R
run() { echo "== $(date +%T) $*"; "$V/bin/python" -W ignore "$@" >> "$L/$B.log" 2>&1; local rc=$?; tail -n 3 "$L/$B.log"; return $rc; }
for pr in train:1 train:2 train:3 val:1 test:1; do
  run scripts/run_h0.py --protocol medium --bench $B --phase ${pr%%:*} --roll ${pr##*:} || exit $?
done
for m in b1 b2 b3; do
  run scripts/run_baselines.py --protocol medium --bench $B --method $m || exit $?
done
echo CHAIN_DONE $B
