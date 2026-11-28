"""Effect of a component edit on saved H0 runs, by divergence-point branching (baselines/b4_diff.py).

Usage: RESULTS_SUFFIX=<h0 folder> python scripts/b4_diff_eval.py <bench> <edit> <phase> [K]
  <edit>   slot/name[:json config][+slot/name...] with variants from baselines/b4_variants/, or a harness root dir
  <phase>  train | val | test
  K        live branches per touched run (default 1); K=0: dry replay only (no model call), prints the map of
           what the edit touches
Env: B4_TAG names the output (results/<suffix>/<tag>_<bench>.jsonl); B4_RESUME=1 reuses finished branches.
"""
import json
import shutil
import sys
from pathlib import Path

from baselines import common as C

C.use_protocol(C.MEDIUM)
from baselines import b4_diff as D  # noqa: E402
from baselines import b4_repertoire as B  # noqa: E402
import llm as llm_mod  # noqa: E402

VARIANTS = Path(__file__).resolve().parents[1] / "baselines" / "b4_variants"


def make_root(ws: Path, spec: str) -> Path:
    if Path(spec).is_dir():
        return Path(spec)
    root = C.new_candidate(ws / "roots" / "".join(c if c.isalnum() else "_" for c in spec)[:80], C.H0_ROOT,
                           {"edit": spec})
    bundle = {}
    for part in spec.split("+"):
        ref, _, cfg = part.partition(":")
        slot, name = ref.split("/")
        shutil.copy2(VARIANTS / slot / f"{name}.py", root / "variants" / slot / f"{name}.py")
        bundle[slot] = {"name": name, "config": json.loads(cfg) if cfg else {}}
    (root / "bundle.json").write_text(json.dumps(bundle, indent=1))
    ok, glog = C.static_gate(root)
    if not ok:
        raise SystemExit("static gate failed:\n" + glog)
    return root


def main(bench: str, spec: str, phase: str, k: int) -> None:
    latest = {}
    for line in (C.OUT / f"h0_{bench}.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            latest[(r.get("phase"), r.get("roll", 1), r["task_id"])] = r
    srcs = [r for (ph, _, _), r in latest.items() if ph == phase and r.get("trajectory_path")
            and Path(r["trajectory_path"]).exists() and not r.get("error")]
    ws = C.RUNS / B.TAG / bench
    ws.mkdir(parents=True, exist_ok=True)
    out = C.OUT / f"{B.TAG}_{bench}.jsonl"
    root = make_root(ws, spec)
    split = C.protocol_tasks(bench, C.PROTOCOLS[C.MEDIUM["name"]])[phase][0]
    cache = C.RUNS / "diff_ref" / bench
    client = llm_mod.LLM()
    tag = f"{B.TAG}_{bench}_{phase}"
    label = {"method": "b4", "phase": f"{phase}_diff", "edit": spec}
    dry = D.run_diff(bench, split, srcs, root, C.H0_ROOT, client, tag, None, cache, dry=True)
    dmap = D.divergence_map(dry)
    print(f"MAP {bench} {phase} edit={spec}: {json.dumps(dmap)}", flush=True)
    res = {"edit": spec, "phase": phase, "map": dmap}
    if k > 0:
        touched = {x["fork_of"] for x in dry if x.get("branched")}
        hit = [s for s in srcs if s["trajectory_path"] in touched]
        recs = []
        for j in range(k):
            recs += D.run_diff(bench, split, hit, root, C.H0_ROOT, client, tag, out, cache, k=j, label=label)
        res.update(D.estimate(srcs, recs), k=k)
        print(f"RESULT {bench} {phase} edit={spec}: {json.dumps({x: res[x] for x in res if x != 'map'})}", flush=True)
    (ws / f"diff_eval_{phase}.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    if len(sys.argv) < 4:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else 1)
