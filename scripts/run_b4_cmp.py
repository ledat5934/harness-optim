"""Run one B4 configuration on one benchmark, reusing an existing H0 (allow_stale), for the v3-vs-v4 comparison.
Env: RESULTS_SUFFIX (H0 folder, e.g. luna), B4_TAG, B4_LLM_MODES, B4_GRAPH, B4_RESUME as usual; B4_BRANCH=1 runs v6."""
import sys

from baselines import common as C
from scripts.run_baselines import load_shared

bench = sys.argv[1]
C.use_protocol(C.MEDIUM)
import importlib

from baselines import b4_repertoire as B
importlib.reload(B)
import llm as llm_mod

shared = load_shared(bench, C.MEDIUM, allow_stale=True)
print(f"shared H0 {bench}: train={len(shared['h0_train'])} val={len(shared['h0_val'])} "
      f"test={len(shared.get('h0_test') or [])}", flush=True)
import os

if os.environ.get("B4_BRANCH") == "1":  # v6: trigger-point branching (baselines/b4_branch.py)
    from baselines import b4_branch as V
    res = V.run(bench, shared, llm_mod.LLM(), cfg=C.MEDIUM)
    print(f"DONE {bench} tag done, test={res['log']['test']['success']} "
          f"test_branch={res['log']['test_branch']}", flush=True)
else:
    res = B.run(bench, shared, llm_mod.LLM(), cfg=C.MEDIUM)
    print(f"DONE {bench} tag done, test={res['log']['test']['success']}", flush=True)
