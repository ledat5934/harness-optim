#!/usr/bin/env bash
# Run the ORIGINAL Meta-Harness TB2 solver (agents/baseline_kira.py) through Harbor.
# Infra-only deviations from scripts/run_eval.sh: env=docker (not runloop/modal),
# model routed to our gateway (OpenAI-compatible), job dir under results/tb2/jobs.
# Usage: tb2_metaharness.sh <job_name> <n_concurrent> <task> [task...]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MH="$ROOT/third_party/meta-harness/reference_examples/terminal_bench_2"
JOB="$1"; N="$2"; shift 2
set -a; . "$ROOT/.env"; set +a
. "$ROOT/scripts/tb2_infra.sh"
export OPENAI_API_KEY="$OPENROUTER_API_KEY" OPENAI_API_BASE="$OPENROUTER_BASE_URL" OPENAI_BASE_URL="$OPENROUTER_BASE_URL"
MODEL="${TB2_MODEL:-openai/cx/gpt-6-luna-low}"
AGENT="${TB2_AGENT:-agents.baseline_kira:AgentHarness}"
if [ -n "${TB2_HARBOR:-}" ]; then
  # Paper artifact: pinned to an older harbor (0.2.x) that has no --ve flag; persistent_env reaches the verifier there.
  INC=(); for t in "$@"; do INC+=(-t "$t"); done
  ARGS=(); skip=0; for a in "${TB2_INFRA_ARGS[@]}"; do
    if [ $skip = 1 ]; then skip=0; continue; fi
    if [ "$a" = "--ve" ]; then skip=1; continue; fi; ARGS+=("$a"); done
  cd "${TB2_PYPATH:-$MH}"; export PYTHONPATH="${TB2_PYPATH:-$MH}${PYTHONPATH:+:$PYTHONPATH}"
  exec "$TB2_HARBOR" run --agent-import-path "$AGENT" -d terminal-bench@2.0 -m "$MODEL" -e docker \
    -n "$N" --n-attempts 1 --ak temperature=0.7 -o "$ROOT/results/tb2/jobs" --job-name "$JOB" "${ARGS[@]}" "${INC[@]}" ${TB2_EXTRA:-}
fi
INC=(); for t in "$@"; do INC+=(-i "$t"); done
cd "$MH"; export PYTHONPATH="${TB2_PYPATH:+$TB2_PYPATH:}$MH${PYTHONPATH:+:$PYTHONPATH}"
exec uv run harbor run --agent "$AGENT" -d terminal-bench@2.0 -m "$MODEL" -e docker \
  -n "$N" --n-attempts 1 --ak temperature=0.7 -o "$ROOT/results/tb2/jobs" --job-name "$JOB" "${TB2_INFRA_ARGS[@]}" "${INC[@]}" ${TB2_EXTRA:-}
