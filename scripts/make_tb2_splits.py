"""Deterministic TB2 splits for our pipeline: seeded shuffle of all task dirs, no hand-picking.
  python scripts/make_tb2_splits.py --seed 0 --n-test 15 --n-val 10 --n-train 20
"""
import argparse, json, random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchmarks.terminal_bench2 import adapter as A

ap = argparse.ArgumentParser()
ap.add_argument("--seed", type=int, default=0)
ap.add_argument("--n-test", type=int, default=15)
ap.add_argument("--n-val", type=int, default=10)
ap.add_argument("--n-train", type=int, default=20)
ap.add_argument("--max-image-gb", type=float, default=1.0,
                help="infra filter: this sandbox has ~8 GB of disk, so tasks whose compressed image is larger are left out")
a = ap.parse_args()
sizes = json.loads(A.SPLITS_FILE.with_name("image_sizes.json").read_text())
ids = [t for t in A.list_tasks("all") if (sizes[t]["compressed_bytes"] or 0) <= a.max_image_gb * 1e9]
excluded = sorted(set(A.list_tasks("all")) - set(ids))
random.Random(a.seed).shuffle(ids)
out = {"seed": a.seed, "test": sorted(ids[:a.n_test]), "val": sorted(ids[a.n_test:a.n_test + a.n_val]),
       "train": sorted(ids[a.n_test + a.n_val:a.n_test + a.n_val + a.n_train])}
out["excluded_image_size"] = excluded
out["max_image_gb"] = a.max_image_gb
out["unused"] = sorted(set(ids) - set(out["test"]) - set(out["val"]) - set(out["train"]) - set(excluded))
A.SPLITS_FILE.write_text(json.dumps(out, indent=1))
print({k: len(v) for k, v in out.items() if isinstance(v, list)})
