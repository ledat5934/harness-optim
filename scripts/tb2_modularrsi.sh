#!/usr/bin/env bash
# Run the ORIGINAL ModularRSI evaluator (scripts/evaluate.sh, agent terminus-2-modular) on TB2.
# Only infra settings change: model routed to our gateway, docker env, output under results/tb2/jobs.
# Usage: tb2_modularrsi.sh <job_name> <composer: llm_dynamic|static> <n_concurrent> <task> [task...]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MR="$ROOT/third_party/ModularRSI"
JOB="$1"; COMP="$2"; N="$3"; shift 3
set -a; . "$ROOT/.env"; set +a
. "$ROOT/scripts/tb2_infra.sh"
export HARBOR_EVO_API_KEY="$OPENROUTER_API_KEY" API_BASE="$OPENROUTER_BASE_URL"
export MODEL="${TB2_MODEL:-openai/cx/gpt-6-luna-low}" ENVIRONMENT=docker COMPOSER_NAME="$COMP" N_CONCURRENT="$N"
export OUTPUT_DIR="$ROOT/results/tb2/jobs/$JOB"
# Build harbor's command exactly as evaluate.sh does (DRY_RUN), then append infra args and extra -i tasks.
export TASK_NAME="$1"; shift
DRY_RUN=true bash "$MR/scripts/evaluate.sh" | sed -n 's/^command: //p' > "$OUTPUT_DIR.cmd" 2>/dev/null || true
EXTRA=(); for t in "$@"; do EXTRA+=(-i "$t"); done
eval "set -- $(cat "$OUTPUT_DIR.cmd")"; rm -f "$OUTPUT_DIR.cmd"
export PATH="$MR/.venv/bin:$PATH" OPENAI_API_KEY="$HARBOR_EVO_API_KEY" HARBOR_MODEL_INFO='{"max_input_tokens":176000,"max_output_tokens":16000,"input_cost_per_token":0.0,"output_cost_per_token":0.0}'
exec "$@" "${TB2_INFRA_ARGS[@]}" "${EXTRA[@]}"
