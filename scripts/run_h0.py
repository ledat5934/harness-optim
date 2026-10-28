"""Run H0 (default composition) on the protocol task lists of one benchmark.

  python scripts/run_h0.py --bench alfworld --phase train --roll 1
Phases: train (5 tasks; K rolls give the shared contrastive evidence), val (3), test (3).
--protocol medium: the MEDIUM task lists (50 train, 30 val, test100.json), results in results/medium/.
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
    ap.add_argument("--protocol", default="smoke", choices=sorted(C.PROTOCOLS))
    ap.add_argument("--redo-errors", action="store_true",
                    help="re-run only the tasks of this phase/roll with no record or whose latest record has an infra error")
    args = ap.parse_args()
    cfg = C.PROTOCOLS[args.protocol]
    C.use_protocol(cfg)
    llm_mod.budget_banner(f"run_h0[{args.protocol}:{args.bench}/{args.phase}/roll{args.roll}]")
    tasks = C.protocol_tasks(args.bench, cfg)
    (C.RUNS / "protocol").mkdir(parents=True, exist_ok=True)
    (C.RUNS / "protocol" / f"{args.bench}.json").write_text(json.dumps(tasks, indent=1))
    split, ids = tasks[args.phase]
    if args.redo_errors:
        p = C.OUT / f"h0_{args.bench}.jsonl"
        latest = {}
        for line in p.read_text(encoding="utf-8").splitlines() if p.exists() else []:
            r = json.loads(line)
            if r.get("phase") == args.phase and r.get("roll", 1) == args.roll:
                latest[r["task_id"]] = r
        ids = [t for t in ids if t not in latest or latest[t].get("error")]  # missing: run killed mid-phase
        if not ids:
            print(f"{args.bench} {args.phase} roll{args.roll}: no infra-error records to redo")
            return
    print(f"{args.bench} {args.phase}: split={split} n={len(ids)}")
    recs = C.evaluate(args.bench, split, ids, C.H0_ROOT, llm_mod.LLM(), f"h0_{args.bench}_{args.phase}_r{args.roll}",
                      C.OUT / f"h0_{args.bench}.jsonl", workers=args.workers,
                      label={"method": "h0", "phase": args.phase, "roll": args.roll,
                             "h0_hash": C.tree_hash(C.H0_ROOT)})
    n = len(recs)
    print(f"SUMMARY h0 {args.bench}/{args.phase}/roll{args.roll}: success {sum(r['success'] for r in recs)}/{n} "
          f"avg_steps {sum(r['steps'] for r in recs) / n:.1f} tokens {sum(r['tokens'] for r in recs)} "
          f"cost ${sum(r['cost'] for r in recs):.6f} errors {sum(1 for r in recs if r['error'])}")
    llm_mod.budget_banner("run_h0(end)", exit_if_low=False)


if __name__ == "__main__":
    main()
