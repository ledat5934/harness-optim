"""Re-run the test episodes of a finished baseline run that ended in an infrastructure error (record `error` set),
with the method's frozen final harness rebuilt from its saved workspace, and replace those records.

    python scripts/redo_test_errors.py --protocol medium --bench alfworld --method b1 [--dry-run]

B1: the selected candidate. B2: the final root (+ the LLM composer when it was promoted). B3: the selected iteration's
bundle and config with the frozen experience bank and test-time case adaptation, as in b3_memo.run. The run's
summary line in baseline_runs.jsonl is appended again with the corrected test score (latest line wins).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import llm as llm_mod  # noqa: E402
from baselines import common as C  # noqa: E402


def test_harness(method: str, bench: str, client) -> dict:
    ws = C.RUNS / method / bench
    fin = json.loads((ws / "final.json").read_text())
    if method == "b1":
        return {"root": Path(fin["final_root"])}
    if method == "b2":
        from baselines.b2_modular import llm_composer_factory
        return {"root": Path(fin["final_root"]),
                "composer": llm_composer_factory(client, bench, []) if fin["composer"] else None}
    from baselines import b3_memo as B3
    from baselines.vendor.memoharness.core.models import HarnessConfig
    ctl = B3.BundleController(bundle_root=ws / "bundle_live", client=client, bench=bench, workspace=ws)
    pkl = ws / "bank.pkl"
    bank = B3.BM25ExperienceBank.load(pkl) if pkl.exists() else B3.BM25ExperienceBank.from_snapshot(ws / "bank.json")
    bank.frozen = True
    it = fin["iteration"]
    root = ws / "iterations" / f"it{it}" / "bundle"
    root = root if it and root.is_dir() else None  # b3_memo.run: (run_dir / "bundle") if cur["bundle"] else None
    cfg = HarnessConfig(**fin["config"])
    return {"root": C.H0_ROOT,
            "composer": B3.adapt_composer(ctl, bank, root, cfg, bench, [], B3.TEST_TIME_CASE_ADAPTATION),
            "label_extra": {"harness": fin["global"]}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", required=True)
    ap.add_argument("--method", required=True, choices=["b1", "b2", "b3"])
    ap.add_argument("--protocol", default="medium", choices=sorted(C.PROTOCOLS))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    cfg = C.PROTOCOLS[args.protocol]
    C.use_protocol(cfg)
    out = C.OUT / f"{args.method}_{args.bench}.jsonl"
    tag = f"{args.method}_{args.bench}_test"
    recs = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]
    test = [r for r in recs if r.get("run_tag") == tag]
    bad = [r for r in test if r.get("error")]
    print(f"{out.name}: {len(test)} test records, {len(bad)} with errors")
    if not bad or args.dry_run:
        return
    split = bad[0]["split"]
    client = llm_mod.LLM()
    h = test_harness(args.method, args.bench, client)
    label = {"method": args.method, "phase": "test", **h.get("label_extra", {})}
    # drop the errored records first, so the file never holds two records for one test task
    bad_ids = {id(r) for r in bad}
    keep = [r for r in recs if id(r) not in bad_ids]
    out.write_text("".join(json.dumps(r, default=str) + "\n" for r in keep))
    C.evaluate(args.bench, split, [r["task_id"] for r in bad], h["root"], client, tag, out,
               composer=h.get("composer"), workers=cfg["workers"], label=label)
    test = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]
    test = [r for r in test if r.get("run_tag") == tag]
    succ = C.score(test)
    errs = sum(1 for r in test if r.get("error"))
    print(f"test after redo: n={len(test)} success={succ:.3f} errors={errs}")
    runs = C.OUT / "baseline_runs.jsonl"
    last = [json.loads(l) for l in runs.read_text().splitlines()
            if l.strip() and json.loads(l).get("bench") == args.bench and json.loads(l).get("method") == args.method][-1]
    C.append_jsonl(runs, {**last, "test_success": succ, "n_test": len(test), "redo_test_errors": len(bad)})


if __name__ == "__main__":
    main()
