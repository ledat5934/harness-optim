"""Run H0 on given TB2 tasks of one phase (tb2small protocol), appending to the protocol's h0 jsonl.
Used by scripts/tb2_compete.sh so H0 runs on each test task while its image is on disk.
  python scripts/tb2_h0_one.py --phase test --roll 1 <task> [task...]
"""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import llm as llm_mod
from baselines import common as C

ap = argparse.ArgumentParser()
ap.add_argument("--phase", default="test")
ap.add_argument("--roll", type=int, default=1)
ap.add_argument("tasks", nargs="+")
a = ap.parse_args()
cfg = C.PROTOCOLS["tb2small"]
C.use_protocol(cfg)
tasks = C.protocol_tasks("terminal_bench2", cfg)
split, ids = tasks[a.phase]
bad = [t for t in a.tasks if t not in ids]
assert not bad, f"not in {a.phase}: {bad}"
C.evaluate("terminal_bench2", split, a.tasks, C.H0_ROOT, llm_mod.LLM(),
           f"h0_terminal_bench2_{a.phase}_r{a.roll}", C.OUT / "h0_terminal_bench2.jsonl", workers=1,
           label={"method": "h0", "phase": a.phase, "roll": a.roll, "h0_hash": C.tree_hash(C.H0_ROOT)})
