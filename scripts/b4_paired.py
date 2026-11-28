"""Paired test comparison of B4 runs against H0, split by whether a mechanism fired.

A gated mechanism (inject / reject_finish / annotate_obs) leaves an episode unchanged until it fires, so on test
tasks where nothing fired the run differs from H0 only by sampling noise. The fired / not-fired split shows how
much of a test gain the mechanisms can actually be credited with (the not-fired half is a noise estimate).

Usage: python scripts/b4_paired.py <results_dir> <bench> <tag> [<tag> ...]
e.g.   python scripts/b4_paired.py results/medium_luna5 browsecomp_plus b4v4c b4v5 b4v5s1
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path


def load(path: Path, phase: str = "test") -> dict[str, dict]:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            if r.get("phase") == phase and not r.get("error"):
                out[r["task_id"]] = r
    return out


def fired(rec: dict) -> bool | None:
    try:
        ev = json.loads(Path(rec["trajectory_path"]).read_text(encoding="utf-8")).get("events", [])
    except Exception:
        return None
    return any(e.get("type") == "mech" for e in ev)


def sign_p(w: int, l: int) -> float:
    n = w + l
    if not n:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(min(w, l) + 1)) / 2 ** n)


def wl(a: dict, b: dict, ids) -> tuple[int, int]:
    return (sum(a[t]["success"] and not b[t]["success"] for t in ids),
            sum(b[t]["success"] and not a[t]["success"] for t in ids))


def main(root: str, bench: str, tags: list[str]) -> None:
    d = Path(root)
    h0 = load(d / f"h0_{bench}.jsonl")
    print(f"H0 test: n={len(h0)} acc={sum(r['success'] for r in h0.values()) / max(1, len(h0)):.3f}")
    for tag in tags:
        run = load(d / f"{tag}_{bench}.jsonl")
        ids = sorted(set(run) & set(h0))
        f = {t for t in ids if fired(run[t])}
        nf = [t for t in ids if t not in f]
        w, l = wl(run, h0, ids)
        fw, fl = wl(run, h0, f)
        nw, nl = wl(run, h0, nf)
        acc = sum(run[t]["success"] for t in ids) / max(1, len(ids))
        print(f"{tag}: acc={acc:.3f} vs H0 {w}W/{l}L p={sign_p(w, l):.2f} | fired on {len(f)}: {fw}W/{fl}L "
              f"p={sign_p(fw, fl):.2f} | not fired {len(nf)}: {nw}W/{nl}L (noise)")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
