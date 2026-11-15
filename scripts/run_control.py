"""Equal-cost control: the seed harness with a verifier that refuses every finish before `--min-step` steps
(baselines/controls/min_steps_finish.py). Resume-safe: tasks with a clean record are skipped.

  python scripts/run_control.py --bench browsecomp_plus --phase test --min-step 14 --protocol medium
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import llm as llm_mod  # noqa: E402
from baselines import common as C  # noqa: E402

SRC = Path(__file__).resolve().parents[1] / "baselines" / "controls" / "min_steps_finish.py"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", required=True)
    ap.add_argument("--phase", required=True, choices=["train", "val", "test"])
    ap.add_argument("--min-step", type=int, required=True)
    ap.add_argument("--limit", type=int, default=0, help="first N tasks of the phase only (calibration)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--protocol", default="medium", choices=sorted(C.PROTOCOLS))
    args = ap.parse_args()
    cfg = C.PROTOCOLS[args.protocol]
    C.use_protocol(cfg)
    name = f"ctrl_minsteps{args.min_step}"
    llm_mod.budget_banner(f"{name}[{args.bench}/{args.phase}]")
    split, ids = C.protocol_tasks(args.bench, cfg)[args.phase]
    ids = ids[:args.limit] if args.limit else ids
    root = C.RUNS / "controls" / args.bench / name
    if not root.exists():
        C.new_candidate(root, meta={"method": "control", "min_step": args.min_step})
        shutil.copy2(SRC, root / "variants" / "verifier" / SRC.name)
        (root / "bundle.json").write_text(json.dumps(
            {"verifier": {"name": "control_min_steps_finish", "config": {"min_step": args.min_step}}}, indent=1))
    out = C.OUT / f"{name}_{args.bench}.jsonl"
    done = set()
    for line in out.read_text(encoding="utf-8").splitlines() if out.exists() else []:
        r = json.loads(line)
        if r.get("phase") == args.phase and not r.get("error"):
            done.add(r["task_id"])
    todo = [t for t in ids if t not in done]
    print(f"{name} {args.bench} {args.phase}: split={split} n={len(ids)} todo={len(todo)}")
    C.evaluate(args.bench, split, todo, root, llm_mod.LLM(), f"{name}_{args.bench}_{args.phase}", out,
               workers=args.workers, label={"method": "control", "phase": args.phase, "min_step": args.min_step})
    recs = {}
    for line in out.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r.get("phase") == args.phase and r["task_id"] in ids and not r.get("error"):
            recs[r["task_id"]] = r
    n = max(1, len(recs))
    print(f"SUMMARY {name} {args.bench}/{args.phase}: success {sum(r['success'] for r in recs.values())}/{len(recs)} "
          f"of {len(ids)} avg_steps {sum(r['steps'] for r in recs.values()) / n:.1f} "
          f"avg_tokens {sum(r['tokens'] for r in recs.values()) // n}")


if __name__ == "__main__":
    main()
