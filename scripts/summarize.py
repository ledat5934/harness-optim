"""Build results/summary.md from results/*.jsonl + results/spend.json. Numbers are computed, never typed in."""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
BENCHES = ["alfworld", "appworld", "browsecomp_plus"]
METHODS = ["h0", "b1", "b2", "b3"]
NAMES = {"h0": "H0 (seed, no evolution)", "b1": "B1 Meta-Harness-style", "b2": "B2 ModularRSI-style",
         "b3": "B3 MemoHarness-style"}


def load(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def latest(recs, key=lambda r: (r.get("phase"), r.get("roll", 1), r.get("run_tag"), r["task_id"])):
    d = {}
    for r in recs:
        d[key(r)] = r
    return list(d.values())


def agg(rs: list[dict]) -> dict:
    n = len(rs)
    if not n:
        return {}
    return {"n": n, "succ": sum(1 for r in rs if r["success"]), "steps": sum(r["steps"] for r in rs) / n,
            "tokens": sum(r["tokens"] for r in rs) / n, "cost": sum(r["cost"] for r in rs),
            "cost_ep": sum(r["cost"] for r in rs) / n, "errors": sum(1 for r in rs if r.get("error"))}


def main():
    spend = json.loads((RES / "spend.json").read_text())
    by_tag = spend.get("by_tag", {})
    runs = load(RES / "baseline_runs.jsonl")
    method_usd = defaultdict(float)
    for r in runs:
        method_usd[(r["method"], r["bench"])] = r["method_total_usd"]  # latest run wins
    lines = ["# Results summary", "",
             "> **SMOKE RUN, not statistically meaningful.** 3 test tasks per cell, 1 evolution round, 1 model "
             "(`inclusionai/ling-3.0-flash`). Differences between methods are within noise. BrowseComp-Plus is judged "
             "by our OpenRouter model, not Qwen3-32B, so it is not comparable with the public leaderboard.", "",
             "> **Which runs use the current H0** (hash `c7e35268c202`, `docs/open_problems.md` item 13): the ALFWorld "
             "rows were produced after the tool-parser fix. The AppWorld and BrowseComp-Plus rows were produced before "
             "it, so they must be re-run (`scripts/run_smoke.sh`, which spends LLM budget) before they are compared with "
             "the ALFWorld rows.", "",
             f"Total spend so far (persistent ledger `results/spend.json`): **${spend['total_usd']:.4f}** of $1.00, "
             f"{spend['calls']} LLM calls, {spend['prompt_tokens']:,} prompt + {spend['completion_tokens']:,} completion tokens.", "",
             "## Test results (frozen harness, held-out test tasks)", "",
             "| method | benchmark | test split | success | avg steps | avg tokens/episode | test cost (USD) | method total cost incl. evolution (USD) | errors |",
             "|---|---|---|---|---|---|---|---|---|"]
    per_episode = []
    for b in BENCHES:
        for m in METHODS:
            recs = latest(load(RES / f"{m}_{b}.jsonl"))
            test = [r for r in recs if r.get("phase") == "test"]
            a = agg(test)
            if not a:
                lines.append(f"| {NAMES[m]} | {b} | - | not run | | | | | |")
                continue
            tot = method_usd.get((m, b))
            lines.append(f"| {NAMES[m]} | {b} | {test[0]['split']} | {a['succ']}/{a['n']} ({a['succ'] / a['n']:.0%}) | "
                         f"{a['steps']:.1f} | {a['tokens']:,.0f} | {a['cost']:.4f} | "
                         f"{'%.4f' % tot if tot is not None else 'shared runs (see below)'} | {a['errors']} |")
    lines += ["", "## H0 shared runs (train rolls / val / test)", "",
              "| benchmark | phase | roll | success | avg steps | avg tokens | cost/episode (USD) | errors |", "|---|---|---|---|---|---|---|---|"]
    for b in BENCHES:
        recs = latest(load(RES / f"h0_{b}.jsonl"))
        groups = defaultdict(list)
        for r in recs:
            groups[(r.get("phase"), r.get("roll", 1))].append(r)
        for (ph, roll), rs in sorted(groups.items(), key=lambda x: (str(x[0][0]), x[0][1])):
            a = agg(rs)
            per_episode.append((b, a["cost_ep"], a["tokens"], a["n"]))
            lines.append(f"| {b} | {ph} | {roll} | {a['succ']}/{a['n']} | {a['steps']:.1f} | {a['tokens']:,.0f} | {a['cost_ep']:.5f} | {a['errors']} |")
    # all episodes (any method/phase) for cost-per-episode estimates
    allep = defaultdict(list)
    for f in RES.glob("*_*.jsonl"):
        if f.name.startswith(("h0_", "b1_", "b2_", "b3_")):
            for r in latest(load(f)):
                allep[r["benchmark"]].append(r)
    lines += ["", "## Measured cost per episode (all agent episodes, incl. judge for BrowseComp-Plus)", "",
              "| benchmark | episodes | mean cost/episode (USD) | mean tokens/episode | mean steps |", "|---|---|---|---|---|"]
    cpe = {}
    for b in BENCHES:
        a = agg(allep.get(b, []))
        if a:
            cpe[b] = a["cost_ep"]
            lines.append(f"| {b} | {a['n']} | {a['cost_ep']:.5f} | {a['tokens']:,.0f} | {a['steps']:.1f} |")
    lines += ["", "## Spend by call type (tag prefix)", "", "| tag prefix | calls | USD |", "|---|---|---|"]
    pref = defaultdict(lambda: [0, 0.0])
    for t, v in by_tag.items():
        k = t.split(":")[0] + (":" + t.split(":")[1] if t.startswith(("b1", "b2", "b3")) and ":" in t else "")
        pref[k][0] += v["calls"]
        pref[k][1] += v["usd"]
    for k, (c, u) in sorted(pref.items(), key=lambda x: -x[1][1]):
        lines.append(f"| {k} | {c} | {u:.5f} |")
    (RES / "cost_per_episode.json").write_text(json.dumps(cpe, indent=1))
    sys.path.insert(0, str(ROOT / "scripts"))
    import budget_estimate
    lines += ["", "## Real-run budget estimate (from the measured cost per episode above)", "",
              budget_estimate.main(), "",
              "Open problems, caveats and the wall-time estimate: `docs/open_problems.md`. Fidelity of each baseline: "
              "`docs/baseline_fidelity.md`."]
    (RES / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (RES / "cost_per_episode.json").write_text(json.dumps(cpe, indent=1))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
