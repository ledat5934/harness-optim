"""Run baselines B1/B2/B3 on one benchmark under the common smoke protocol.

  python scripts/run_baselines.py --bench alfworld --method b1
Prerequisite: shared H0 runs in results/h0_<bench>.jsonl (scripts/run_h0.py): train roll 1 + roll 2, val, test.
All methods read the SAME shared H0 evidence (same seed, same tasks, executed once), get the same number of rounds
(SMOKE["rounds"]) and the same per-round execution budget (2 check executions on train + 3 validation
executions), and their final harness is frozen before the 3 test executions.

Debug mode (one sample per phase, everything logged, nothing written into the committed results):
  python scripts/run_baselines.py --bench alfworld --method b1 --debug
writes results/debug/<method>_<bench>_<time>/ (git-ignored):
  llm_full.jsonl   every LLM call: full request messages + reply (content, hidden reasoning, tool calls)
  transcript.md    the same, readable (scripts/show_debug.py), plus the outcome of each episode
  results/trajectories/<bench>/<run_tag>/   per-episode trajectories (git-ignored);  results/runs/<method>/<bench>/  the method workspace (log.json, candidates, router_ledger.json for b2)
--debug defaults to --n-check 1 --n-val 1 --n-test 1 --workers 1; the shared H0 train evidence stays complete
(it is already paid for). AppWorld test (test_normal) is never run in debug mode: its tasks must not be inspected.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import llm as llm_mod  # noqa: E402
from baselines import common as C  # noqa: E402


def load_shared(bench: str, cfg: dict = C.SMOKE, allow_stale: bool = False) -> dict:
    p = C.OUT / f"h0_{bench}.jsonl"
    recs = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    tasks = C.protocol_tasks(bench, C.PROTOCOLS[cfg["name"]])
    # smaller val/test (debug): prefixes of the protocol lists, so the shared H0 val records still match
    tasks["val"] = (tasks["val"][0], tasks["val"][1][: cfg["n_val"]])
    tasks["test"] = (tasks["test"][0], tasks["test"][1][: cfg["n_test"]])
    tr_ids = set(tasks["train"][1])
    # keep the latest record per (phase, roll, task) in case a run was repeated
    latest = {}
    for r in recs:
        latest[(r.get("phase"), r.get("roll", 1), r["task_id"])] = r
    h0_train = [r for (ph, _, tid), r in latest.items() if ph == "train" and tid in tr_ids]
    h0_val = [r for (ph, _, tid), r in latest.items() if ph == "val" and tid in set(tasks["val"][1])]
    cur = C.tree_hash(C.H0_ROOT)
    stale = [r["task_id"] for r in h0_train + h0_val if r.get("h0_hash") != cur]
    if stale and allow_stale:  # debug only: the evidence is just context for reading the method's behaviour
        print(f"[debug] WARNING: shared H0 records come from an older H0 (current hash {cur}); fine for debugging, "
              f"not for results. Re-run scripts/run_h0.py for a real run.")
    elif stale:  # the shared evidence must come from exactly the H0 the methods start from
        raise SystemExit(f"shared H0 records were produced by a different H0 (hash != {cur}): {stale[:3]}")
    if len(h0_val) != len(tasks["val"][1]) or not h0_train:
        raise SystemExit(f"shared H0 runs incomplete for {bench}: train={len(h0_train)} val={len(h0_val)}")
    rolls = Counter(r["task_id"] for r in h0_train)
    short = sorted(t for t in tr_ids if rolls[t] < cfg["k"])
    if short:  # the contrastive router needs K rolls of every train task
        raise SystemExit(f"shared H0 train evidence has < K={cfg['k']} rolls for {len(short)} tasks of {bench}; "
                         f"run scripts/run_h0.py --bench {bench} --phase train --roll N for the missing rolls")
    return {"tasks": tasks, "h0_train": h0_train, "h0_val": h0_val}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", required=True)
    ap.add_argument("--method", required=True, choices=["b1", "b2", "b3"])
    ap.add_argument("--debug", action="store_true", help="full LLM logging + verbose steps, output in results/debug/")
    for k in ("n_check", "n_val", "n_test", "workers"):
        ap.add_argument("--" + k.replace("_", "-"), type=int)
    ap.add_argument("--protocol", default="smoke", choices=sorted(C.PROTOCOLS))
    args = ap.parse_args()
    base_cfg = C.PROTOCOLS[args.protocol]
    C.use_protocol(base_cfg)
    cfg = dict(base_cfg)
    if args.debug:
        cfg.update(n_check=1, n_val=1, n_test=1, workers=1)
    for k in ("n_check", "n_val", "n_test", "workers"):
        if getattr(args, k) is not None:
            cfg[k] = getattr(args, k)
    dbg = None
    if args.debug:
        if args.bench == "appworld" and cfg["n_test"]:
            print("[debug] AppWorld test_normal is not run in debug mode (its tasks must not be inspected).")
            cfg["n_test"] = 0
        from benchmarks import common as bc
        dbg = C.ROOT / "results" / "debug" / f"{args.method}_{args.bench}_{time.strftime('%Y%m%d_%H%M%S')}"
        dbg.mkdir(parents=True)
        llm_mod.FULL_LOG, llm_mod.VERBOSE = dbg / "llm_full.jsonl", True
        bc.TRAJ_DIR, bc.VERBOSE = dbg / "trajectories", True
        C.OUT, C.RUNS = dbg, dbg / "runs"
        print(f"[debug] output -> {dbg}  cfg={cfg}")
    elif cfg != base_cfg:
        raise SystemExit("--n-*/--workers overrides need --debug (they would mix into the committed results)")
    llm_mod.budget_banner(f"run_baselines[{args.bench}/{args.method}]")
    shared = load_shared(args.bench, cfg, allow_stale=args.debug)
    print(f"shared H0: train records={len(shared['h0_train'])} (pass {sum(r['success'] for r in shared['h0_train'])}), "
          f"val={C.score(shared['h0_val']):.2f}")
    mod = {"b1": "baselines.b1_freeform", "b2": "baselines.b2_modular", "b3": "baselines.b3_memo"}[args.method]
    import importlib
    m = importlib.import_module(mod)
    t0 = time.time()
    spend0 = llm_mod.get_spend()["total_usd"]
    try:
        res = m.run(args.bench, shared, llm_mod.LLM(), cfg=cfg)
    finally:
        if dbg is not None:  # also after a crash: the transcript is what you debug with
            import show_debug
            print(f"[debug] transcript -> {show_debug.write(dbg)}")
    spent = llm_mod.get_spend()["total_usd"] - spend0
    summ = {"protocol": args.protocol, "bench": args.bench, "method": args.method, "test_success": res["log"]["test"]["success"],
            "n_test": res["log"]["test"]["n"], "method_total_usd": round(spent, 6), "wall_s": round(time.time() - t0, 1),
            "rounds": [{k: v for k, v in r.items() if k in ("round", "result", "val", "selected_slots", "accepted",
                                                            "canary", "hypothesis", "gate")} for r in res["log"]["rounds"]],
            "final": res["log"].get("final")}
    C.append_jsonl(C.OUT / "baseline_runs.jsonl", summ)
    print("RESULT", json.dumps(summ, default=str)[:2000])
    llm_mod.budget_banner("run_baselines(end)", exit_if_low=False)


if __name__ == "__main__":
    main()
