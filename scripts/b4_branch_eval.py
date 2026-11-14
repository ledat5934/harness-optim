"""Low-noise effect of a fixed mechanism set, by trigger-point branching of saved H0 runs (baselines/b4_branch.py).

Every saved H0 run of the phase is replayed with the mechanisms installed; it costs no model call until one of
them fires. Runs where nothing fires keep H0's outcome exactly; the others get K live continuations.

Usage: RESULTS_SUFFIX=<h0 folder> python scripts/b4_branch_eval.py <bench> <final.json | pool.json:ids> <phase> [K]
  <final.json>      a B4 run's final.json (its "set"), or pool.json:m1,m3 to pick mechanisms from a pool
  <phase>           train | val | test
Env: B4_TAG names the output (results/<suffix>/<tag>_<bench>.jsonl); B4_RESUME=1 reuses finished branches.
"""
import json
import sys
from pathlib import Path

from baselines import common as C

C.use_protocol(C.MEDIUM)
from baselines import b4_branch as V  # noqa: E402
from baselines import b4_repertoire as B  # noqa: E402
from baselines.hg import runtime as R  # noqa: E402
import llm as llm_mod  # noqa: E402


def main(bench: str, spec: str, phase: str, k: int) -> None:
    path, _, ids = spec.partition(":")
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    mechs = d.get("set") if isinstance(d, dict) else [m for m in d if m["id"] in ids.split(",")]
    mechs = [R.validate_mechanism({x: m[x] for x in ("id", "kind", "precondition", "text", "max_fires", "llm_check")
                                   if m.get(x) not in (None, "")}) for m in mechs]
    latest = {}
    for line in (C.OUT / f"h0_{bench}.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            latest[(r.get("phase"), r.get("roll", 1), r["task_id"])] = r
    srcs = [r for (ph, _, _), r in latest.items() if ph == phase and r.get("trajectory_path")
            and Path(r["trajectory_path"]).exists() and not r.get("error")]
    ws = C.RUNS / B.TAG / bench
    ws.mkdir(parents=True, exist_ok=True)
    out = C.OUT / f"{B.TAG}_{bench}.jsonl"
    root = B.make_root(ws, "eval_" + "_".join(m["id"] for m in mechs), mechs)
    V.K_TEST = k
    split = C.protocol_tasks(bench, C.PROTOCOLS[C.MEDIUM["name"]])[phase][0]
    res = V.branch_test(bench, split, srcs, mechs, root, llm_mod.LLM(), out, {"workers": 4})
    print(f"RESULT {bench} {phase} set={[m['id'] for m in mechs]}: {json.dumps(res)}", flush=True)
    (ws / f"branch_eval_{phase}.json").write_text(json.dumps({"mechs": mechs, "phase": phase, **res}, indent=1))


if __name__ == "__main__":
    if len(sys.argv) < 4:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else 3)
