"""Run H0 (default composition) on the protocol task lists of one benchmark.

  python scripts/run_h0.py --bench alfworld --phase train --roll 1
Phases: train (5 tasks; K rolls give the shared contrastive evidence), val (3), test (3).
Results -> results/h0_<bench>.jsonl (label: method=h0, phase, roll). These runs are shared by all baselines:
same seed, same tasks, executed once.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import llm as llm_mod  # noqa: E402
from baselines import common as C  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", required=True)
    ap.add_argument("--phase", required=True, choices=["train", "val", "test"])
    ap.add_argument("--roll", type=int, default=1)
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()
    llm_mod.budget_banner(f"run_h0[{args.bench}/{args.phase}/roll{args.roll}]")
    tasks = C.protocol_tasks(args.bench)
    (C.RUNS / "protocol").mkdir(parents=True, exist_ok=True)
    (C.RUNS / "protocol" / f"{args.bench}.json").write_text(json.dumps(tasks, indent=1))
    split, ids = tasks[args.phase]
    print(f"{args.bench} {args.phase}: split={split} n={len(ids)}")
    recs = C.evaluate(args.bench, split, ids, C.H0_ROOT, llm_mod.LLM(), f"h0_{args.bench}_{args.phase}_r{args.roll}",
                      C.ROOT / "results" / f"h0_{args.bench}.jsonl", workers=args.workers,
                      label={"method": "h0", "phase": args.phase, "roll": args.roll,
                             "h0_hash": C.tree_hash(C.H0_ROOT)})
    n = len(recs)
    print(f"SUMMARY h0 {args.bench}/{args.phase}/roll{args.roll}: success {sum(r['success'] for r in recs)}/{n} "
          f"avg_steps {sum(r['steps'] for r in recs) / n:.1f} tokens {sum(r['tokens'] for r in recs)} "
          f"cost ${sum(r['cost'] for r in recs):.6f} errors {sum(1 for r in recs if r['error'])}")
    llm_mod.budget_banner("run_h0(end)", exit_if_low=False)


if __name__ == "__main__":
    main()
