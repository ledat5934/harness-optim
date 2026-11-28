#!/usr/bin/env bash
# Small TB2 comparison: for each task of a split, run every arm in parallel while the task image is on disk,
# then free the image. Arms (original code, our gateway model):
#   mh_kira   Meta-Harness reference baseline agents/baseline_kira.py:AgentHarness
#   mh_art    Meta-Harness paper harness (meta-harness-tbench2-artifact agent.py:AgentHarness)
#   mr_static ModularRSI terminus-2-modular, composer=static (baseline bundle)
#   mr_dyn    ModularRSI terminus-2-modular, composer=llm_dynamic over generations/merged_active
#   h0        our H0 (benchmarks/terminal_bench2 adapter)
# Usage: tb2_compete.sh <split> [arm,arm,...]   (re-runnable: finished arm/task pairs are skipped)
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
SPLIT="${1:-test}"; ARMS="${2:-mh_kira,mh_art,mr_static,mr_dyn,h0}"
J="$ROOT/results/tb2/jobs"; LOGS="$ROOT/results/tb2/logs"; L="$J/_live_logs"; mkdir -p "$J" "$L" "$LOGS"  # live logs are gitignored; copied when a task ends
TASKS=$(python3 -c "import json;print(' '.join(json.load(open('benchmarks/terminal_bench2/splits.json'))['$SPLIT']))")
done_job() { find "$J/$1" -name result.json -maxdepth 2 2>/dev/null | while read -r f; do
  python3 -c "import json,sys;d=json.load(open('$f'));sys.exit(0 if d.get('finished_at') and d.get('n_total_trials') else 1)" && echo y; done | grep -q y; }
done_h0() { python3 - "$1" <<'PY'
import json,sys
from pathlib import Path
p=Path("results/tb2small/h0_terminal_bench2.jsonl")
ok=any((r:=json.loads(l))["task_id"]==sys.argv[1] and r.get("phase")=="test" and not r.get("error") for l in (p.read_text().splitlines() if p.exists() else []))
sys.exit(0 if ok else 1)
PY
}
# All harbor versions share ~/.cache/harbor/tasks/<hash>/<task>: concurrent first downloads of one task race
# (an arm then finds a half-written task dir). After the first harbor arm starts, wait until the task is cached.
cache_ok() { ls /root/.cache/harbor/tasks/*/"$1"/environment/Dockerfile > /dev/null 2>&1 && \
             ls /root/.cache/harbor/tasks/*/"$1"/tests/test.sh > /dev/null 2>&1; }
wait_cache() { for _ in $(seq 60); do cache_ok "$1" && { sleep 3; return; }; sleep 2; done; }
for t in $TASKS; do
  to=$(python3 -c "import tomllib;d=tomllib.load(open('data/tb2/terminal-bench/$t/task.toml','rb'));print(int(2*d['agent']['timeout_sec']+2*d['verifier']['timeout_sec']+1800))")
  echo "$(date -u +%H:%M:%S) task $t (timeout ${to}s)"
  pids=()
  for a in ${ARMS//,/ }; do
    job="${a}__${SPLIT}__$t"
    [[ "$a" != h0 && ${#pids[@]} -gt 0 ]] && ! cache_ok "$t" && wait_cache "$t"
    case $a in
      mh_kira) done_job "$job" || { timeout "$to" scripts/tb2_metaharness.sh "$job" 1 "$t" > "$L/$job.log" 2>&1 & pids+=($!); } ;;
      mh_art)  done_job "$job" || { TB2_PYPATH="$ROOT/third_party/mh-tb2-artifact" TB2_HARBOR="$ROOT/third_party/mh-tb2-artifact/.venv/bin/harbor" TB2_AGENT=agent:AgentHarness \
                 timeout "$to" scripts/tb2_metaharness.sh "$job" 1 "$t" > "$L/$job.log" 2>&1 & pids+=($!); } ;;
      mr_static) done_job "$job" || { timeout "$to" scripts/tb2_modularrsi.sh "$job" static 1 "$t" > "$L/$job.log" 2>&1 & pids+=($!); } ;;
      mr_dyn)  done_job "$job" || { timeout "$to" scripts/tb2_modularrsi.sh "$job" llm_dynamic 1 "$t" > "$L/$job.log" 2>&1 & pids+=($!); } ;;
      h0)      [[ "$SPLIT" == test ]] && { done_h0 "$t" || { timeout "$to" python3 scripts/tb2_h0_one.py --phase test --roll 1 "$t" \
                 > "$L/$job.log" 2>&1 & pids+=($!); }; } ;;
    esac
  done
  for p in "${pids[@]}"; do wait "$p"; done
  img=$(python3 -c "import tomllib;print(tomllib.load(open('data/tb2/terminal-bench/$t/task.toml','rb'))['environment']['docker_image'])")
  docker rmi "$img" > /dev/null 2>&1  # only this task's image; refused while another run still uses it
  cp -f "$L"/*__"${SPLIT}__$t".log "$LOGS"/ 2>/dev/null
  echo "$(date -u +%H:%M:%S) done $t; free $(df -h / | awk 'NR==2{print $4}')"
done
echo ALL_DONE
