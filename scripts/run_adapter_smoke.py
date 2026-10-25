"""Run one benchmark adapter on N tasks with a given agent and append Results to results/<out>.jsonl.

  python scripts/run_adapter_smoke.py --bench alfworld --split train --n 3 --agent trivial
  python scripts/run_adapter_smoke.py --bench appworld --split dev --n 5 --agent h0
"""
from __future__ import annotations

import argparse
import dataclasses
import importlib
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import llm as llm_mod  # noqa: E402
from benchmarks.common import append_jsonl  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def make_agent(name: str, max_steps: int | None):
    if name == "trivial":
        from benchmarks.trivial_agent import TrivialAgent
        return TrivialAgent(max_steps=max_steps or 6)
    if name == "h0":
        from h0.compose import LazyHarness
        return LazyHarness()
    raise ValueError(name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", required=True, choices=["alfworld", "appworld", "browsecomp_plus"])
    ap.add_argument("--split", required=True)
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--agent", default="trivial")
    ap.add_argument("--max-steps", type=int, default=None)
    ap.add_argument("--workers", type=int, default=1, help="concurrent episodes (<=4)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--tag", default=None)
    args = ap.parse_args()
    if args.split.startswith("test") and args.bench == "appworld":
        raise SystemExit("AppWorld test splits are not allowed for smoke/dev runs.")
    llm_mod.budget_banner(f"run_adapter_smoke[{args.bench}/{args.agent}]")
    ad = importlib.import_module(f"benchmarks.{args.bench}.adapter")
    tasks = ad.list_tasks(args.split)
    print(f"{args.bench}/{args.split}: {len(tasks)} tasks available; running {args.n} from offset {args.offset}")
    tasks = tasks[args.offset: args.offset + args.n]
    tag = args.tag or f"{args.agent}_{time.strftime('%Y%m%d_%H%M%S')}"
    out = ROOT / "results" / (args.out or f"phase2_{args.agent}_{args.bench}.jsonl")
    client = llm_mod.LLM()

    def one(tid):
        agent = make_agent(args.agent, args.max_steps)
        t0 = time.time()
        r = ad.run_episode(tid, agent, client, split=args.split, run_tag=tag, max_steps=args.max_steps)
        rec = {**dataclasses.asdict(r), "split": args.split, "agent": args.agent, "run_tag": tag,
               "wall_s": round(time.time() - t0, 1)}
        append_jsonl(out, rec)
        print(f"  {tid[:70]:70s} success={r.success} steps={r.steps} tokens={r.tokens} cost=${r.cost:.6f} "
              f"err={r.error}", flush=True)
        return r

    if args.bench == "appworld" or args.workers <= 1:
        results = [one(t) for t in tasks]  # AppWorld: signal-based timeouts need the main thread
    else:
        with ThreadPoolExecutor(max_workers=min(4, args.workers)) as ex:
            results = list(ex.map(one, tasks))
    n = len(results)
    print(f"SUMMARY {args.bench}/{args.split}/{args.agent}: success {sum(r.success for r in results)}/{n}, "
          f"avg steps {sum(r.steps for r in results) / max(n, 1):.1f}, tokens {sum(r.tokens for r in results)}, "
          f"cost ${sum(r.cost for r in results):.6f}, errors {sum(1 for r in results if r.error)}")
    llm_mod.budget_banner("run_adapter_smoke(end)", exit_if_low=False)


if __name__ == "__main__":
    main()
