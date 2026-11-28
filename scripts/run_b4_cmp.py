"""Run one B4 configuration on one benchmark, reusing an existing H0 (allow_stale), for the v3-vs-v4 comparison.
Env: RESULTS_SUFFIX (H0 folder, e.g. luna), B4_TAG, B4_LLM_MODES, B4_GRAPH, B4_RESUME as usual; B4_BRANCH=1 runs v6,
B4_COMP=1 runs v7 (component edits with behaviour hypotheses, baselines/b4_comp.py). B4_ROUNDS overrides the number of
rounds of the protocol (default: MEDIUM's 5). B4_PROTOCOL picks another protocol of baselines.common.PROTOCOLS
(default medium)."""
import sys

from baselines import common as C
from scripts.run_baselines import load_shared

bench = sys.argv[1]
import os

C.MEDIUM = C.PROTOCOLS[os.environ.get("B4_PROTOCOL", "medium")]
C.use_protocol(C.MEDIUM)
import importlib

from baselines import b4_repertoire as B
importlib.reload(B)
import llm as llm_mod

shared = load_shared(bench, C.MEDIUM, allow_stale=True)
print(f"shared H0 {bench}: train={len(shared['h0_train'])} val={len(shared['h0_val'])} "
      f"test={len(shared.get('h0_test') or [])}", flush=True)
if os.environ.get("B4_TEST_WAIT"):  # "<log file>:<marker>": the H0 test runs are still being produced elsewhere;
    import time                      # evolution starts now, the test records are read when the final test needs them

    class _LateTest(dict):
        def get(self, k, d=None):
            if k == "h0_test":
                f, mark = os.environ["B4_TEST_WAIT"].rsplit(":", 1)
                while not (os.path.exists(f) and mark in open(f, encoding="utf-8", errors="replace").read()):
                    time.sleep(120)
                return load_shared(bench, C.MEDIUM, allow_stale=True)["h0_test"]
            return super().get(k, d)
    shared = _LateTest(shared)
import os

if os.environ.get("B4_ROUNDS"):
    C.MEDIUM = {**C.MEDIUM, "rounds": int(os.environ["B4_ROUNDS"])}
    print(f"rounds: {C.MEDIUM['rounds']}", flush=True)
if os.environ.get("B4_COMP") == "1":  # v7: component edits, behaviour hypothesis tested before the outcome
    from baselines import b4_comp as M
    res = M.run(bench, shared, llm_mod.LLM(), cfg=C.MEDIUM)
    print(f"DONE {bench} tag done, test={res['log']['test']['success']} merged={res['log']['final']['merged']} "
          f"test_branch={res['log']['test_branch']}", flush=True)
elif os.environ.get("B4_BRANCH") == "1":  # v6: trigger-point branching (baselines/b4_branch.py)
    from baselines import b4_branch as V
    res = V.run(bench, shared, llm_mod.LLM(), cfg=C.MEDIUM)
    print(f"DONE {bench} tag done, test={res['log']['test']['success']} "
          f"test_branch={res['log']['test_branch']}", flush=True)
else:
    res = B.run(bench, shared, llm_mod.LLM(), cfg=C.MEDIUM)
    print(f"DONE {bench} tag done, test={res['log']['test']['success']}", flush=True)
