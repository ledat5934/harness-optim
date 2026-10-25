#!/bin/bash
# Usage (from Windows): wsl -d Ubuntu-HG -u root -- bash /mnt/e/KLTN/scripts/wsl_run.sh <hg|aw|bcp> <command...>
# Activates the per-benchmark venv and runs the command from the repo root.
venv=$1; shift
case $venv in hg) V=/root/hg-venv;; aw) V=/root/aw-venv;; bcp) V=/root/bcp-venv;; *) echo "venv?"; exit 2;; esac
. $V/bin/activate
export ALFWORLD_DATA=${ALFWORLD_DATA:-/root/.cache/alfworld}
export APPWORLD_ROOT=${APPWORLD_ROOT:-/root/appworld_root}
export JAVA_HOME=${JAVA_HOME:-/usr/lib/jvm/java-21-openjdk-amd64}
export PYTHONPATH=/mnt/e/KLTN
export PYTHONUNBUFFERED=1
cd /mnt/e/KLTN
exec "$@"
