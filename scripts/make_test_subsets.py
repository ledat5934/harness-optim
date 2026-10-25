"""Fixed 100-task test subsets for the MEDIUM protocol -> benchmarks/<bench>/test100.json (ids only, committed).

  python scripts/make_test_subsets.py --bench alfworld          (run inside that benchmark's venv)

  alfworld         valid_unseen (134 games), stratified by the 6 task types, proportional allocation (largest
                   remainder), random games inside each type.
  appworld         test_normal, 33 whole scenarios (99 tasks) so SGC stays defined. Task ids are
                   <scenario>_<n>; only ids are read (task contents of test splits are never opened).
  browsecomp_plus  100 random queries of the held-out part (everything after the 80 dev80 queries).
Same SEED for every benchmark; the selection depends only on the sorted id lists, so it is reproducible.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SEED = 20261025
N = 100
APPWORLD_SCENARIOS = 33


def allocate(sizes: dict[str, int], n: int) -> dict[str, int]:
    """Proportional allocation of n over groups, largest remainder (ties by group name)."""
    total = sum(sizes.values())
    quota = {g: n * s / total for g, s in sizes.items()}
    out = {g: int(q) for g, q in quota.items()}
    for g in sorted(sizes, key=lambda g: (-(quota[g] - out[g]), g))[: n - sum(out.values())]:
        out[g] += 1
    return out


def alfworld(ids: list[str], rng: random.Random) -> tuple[list[str], dict]:
    by: dict[str, list[str]] = {}
    for t in sorted(ids):
        by.setdefault(t.split("-")[0], []).append(t)
    alloc = allocate({g: len(v) for g, v in by.items()}, N)
    pick = [t for g in sorted(by) for t in rng.sample(by[g], alloc[g])]
    return sorted(pick), {"per_type": {g: [len(by[g]), alloc[g]] for g in sorted(by)}}


def appworld(ids: list[str], rng: random.Random) -> tuple[list[str], dict]:
    by: dict[str, list[str]] = {}
    for t in sorted(ids):
        by.setdefault(t.rsplit("_", 1)[0], []).append(t)
    scen = rng.sample(sorted(by), APPWORLD_SCENARIOS)
    pick = sorted(t for s in scen for t in by[s])
    return pick, {"scenarios": sorted(scen), "n_scenarios_total": len(by)}


def browsecomp(ids: list[str], rng: random.Random) -> tuple[list[str], dict]:
    return sorted(rng.sample(sorted(ids), N)), {}


PLAN = {"alfworld": ("unseen", alfworld, "stratified by task type, proportional"),
        "appworld": ("test_normal", appworld, f"{APPWORLD_SCENARIOS} whole scenarios"),
        "browsecomp_plus": ("heldout", browsecomp, "simple random sample of the held-out queries")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", required=True, choices=sorted(PLAN))
    args = ap.parse_args()
    from baselines.common import adapter
    split, fn, method = PLAN[args.bench]
    ids = adapter(args.bench).list_tasks(split)
    pick, extra = fn(ids, random.Random(SEED))
    out = ROOT / "benchmarks" / args.bench / "test100.json"
    eval_split = "test" if args.bench == "browsecomp_plus" else split  # BCP episodes look ids up in the whole subset
    out.write_text(json.dumps({"bench": args.bench, "split": eval_split, "drawn_from": split, "pool_size": len(ids),
                               "seed": SEED, "method": method, **extra, "n": len(pick), "ids": pick}, indent=1) + "\n",
                   encoding="utf-8")
    print(f"{args.bench}: {len(pick)} of {len(ids)} ({method}) -> {out}")


if __name__ == "__main__":
    main()
