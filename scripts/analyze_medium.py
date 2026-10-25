"""Metrics of the MEDIUM run -> results/medium/analysis.md (numbers computed from results/medium/*.jsonl, never typed).

  python scripts/analyze_medium.py

Per benchmark and method (H0, B1, B2, B3), on the fixed test100 subset:
  success with a 95% Wilson interval; paired comparison with H0 on the same tasks (wins/losses, exact McNemar p);
  tokens, USD per episode, USD per success; infra-error episodes (counted as failures, listed separately);
  ALFWorld success per task type; AppWorld TGC, SGC and the mean fraction of unit tests passed;
  BrowseComp-Plus accuracy, mean search/get_document calls, no-answer rate.
Proposer cost per method = spend by tag b1:*/b2:*/b3:* minus the smoke run's (the committed results/spend.json);
evolution-episode cost = the method's non-test rollouts (H0's row: the shared train+val evidence).
Evolution trace per method from results/medium/runs/<method>/<bench>/log.json.
"""
from __future__ import annotations

import json
import math
import subprocess
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
M = ROOT / "results" / "medium"
BENCHES = ["alfworld", "appworld", "browsecomp_plus"]
METHODS = ["h0", "b1", "b2", "b3"]


def load(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def credit_error(r: dict) -> bool:
    """HTTP 402 (the API key ran out of credit): not an episode outcome, so the episode is left out."""
    return "HTTP 402" in (r.get("error") or "")


def test_recs(bench: str, method: str, path: Path | None = None) -> dict[str, dict]:
    recs = [r for r in load(path or M / f"{method}_{bench}.jsonl") if r.get("phase") == "test"]
    return {r["task_id"]: r for r in recs if not credit_error(r)}  # latest record per task


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if not n:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def mcnemar(b: int, c: int) -> float:
    """Exact two-sided McNemar p-value on the discordant pairs (b wins, c losses)."""
    n = b + c
    if not n:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def smoke_spend() -> dict:
    try:
        txt = subprocess.run(["git", "show", "dbc3b3b:results/spend.json"], cwd=ROOT, capture_output=True,
                             text=True, check=True).stdout
        return json.loads(txt)["by_tag"]
    except Exception:
        return {}


def search_cost(bench: str) -> dict[str, float]:
    now = json.loads((ROOT / "results" / "spend.json").read_text())["by_tag"]
    old = smoke_spend()
    out = defaultdict(float)
    for tag, v in now.items():
        parts = tag.split(":")
        if len(parts) >= 3 and parts[0] in ("b1", "b2", "b3") and parts[2] == bench:
            out[parts[0]] += v["usd"] - old.get(tag, {}).get("usd", 0.0)
    return dict(out)


def evo_cost(bench: str, method: str) -> float:
    """Episode cost of the search itself (smoke/canary/val rollouts; for H0 its train+val evidence, shared by all)."""
    return sum(r["cost"] for r in load(M / f"{method}_{bench}.jsonl") if r.get("phase") != "test")


def pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def bench_section(bench: str) -> list[str]:
    ids = json.loads((ROOT / "benchmarks" / bench / "test100.json").read_text())["ids"]
    data = {m: test_recs(bench, m) for m in METHODS}
    sc = search_cost(bench)
    L = [f"## {bench}", "", f"Test subset: {len(ids)} tasks (`benchmarks/{bench}/test100.json`).", "",
         "| method | test episodes | success | 95% CI | vs H0 (win/loss) | McNemar p | tokens/ep | $/ep | $/success | infra errors | proposer $ | evolution episodes $ |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    h0 = data["h0"]
    for m in METHODS:
        d = data[m]
        if not d:
            L.append(f"| {m} | 0 | – | – | – | – | – | – | – | – | – | – |")
            continue
        rs = [d[t] for t in ids if t in d]
        n, k = len(rs), sum(1 for r in rs if r["success"])
        lo, hi = wilson(k, n)
        tok = sum(r["tokens"] for r in rs) / n
        usd = sum(r["cost"] for r in rs)
        err = sum(1 for r in rs if r.get("error"))
        if m == "h0":
            vs, p = "–", "–"
        else:
            both = [t for t in ids if t in d and t in h0]
            w = sum(1 for t in both if d[t]["success"] and not h0[t]["success"])
            lo_ = sum(1 for t in both if h0[t]["success"] and not d[t]["success"])
            vs, p = f"+{w} / −{lo_}", f"{mcnemar(w, lo_):.3f}"
        L.append(f"| {m} | {n} | {pct(k / n)} ({k}) | {pct(lo)}–{pct(hi)} | {vs} | {p} | {tok:,.0f} | {usd / n:.5f} | "
                 f"{(usd / k if k else float('nan')):.5f} | {err} | {sc.get(m, 0.0):.3f} | {evo_cost(bench, m):.3f} |")
    L.append("")
    L += extra_metrics(bench, ids, data)
    L += h0_replicas(bench, ids, h0)
    L += evolution(bench)
    return L


# B1 runs whose final harness was behaviourally H0 (port bugs, see docs/baseline_fidelity.md): a second H0 sample
REPLICAS = {"alfworld": M / "aborted_argvalue" / "b1_alfworld.jsonl",
            "browsecomp_plus": M / "aborted_unselected" / "b1_browsecomp_plus.jsonl",
            "appworld": M / "aborted_unselected" / "b1_appworld.jsonl"}


def h0_replicas(bench: str, ids: list[str], h0: dict) -> list[str]:
    p = REPLICAS.get(bench)
    rep_ = test_recs(bench, "b1", p) if p and p.exists() else {}
    both = [t for t in ids if t in rep_ and t in h0]
    if not both:
        return []
    a = sum(h0[t]["success"] for t in both)
    b = sum(rep_[t]["success"] for t in both)
    w = sum(1 for t in both if rep_[t]["success"] and not h0[t]["success"])
    lo = sum(1 for t in both if h0[t]["success"] and not rep_[t]["success"])
    return [f"Run-to-run noise: a second run of a behaviourally identical harness (`{p.relative_to(ROOT)}`) on the same "
            f"{len(both)} tasks: {pct(b / len(both))} vs H0 {pct(a / len(both))} ({w} tasks flip to pass, {lo} to fail).", ""]


def extra_metrics(bench: str, ids: list[str], data: dict) -> list[str]:
    L = []
    if bench == "alfworld":
        types = sorted({t.split("-")[0] for t in ids})
        L += ["Success per task type:", "", "| method | " + " | ".join(t.replace("_", " ") for t in types) + " |",
              "|---|" + "---|" * len(types)]
        for m in METHODS:
            d = data[m]
            if not d:
                continue
            cells = []
            for ty in types:
                rs = [d[t] for t in ids if t in d and t.startswith(ty + "-")]
                cells.append(f"{sum(r['success'] for r in rs)}/{len(rs)}")
            L.append(f"| {m} | " + " | ".join(cells) + " |")
    elif bench == "appworld":
        L += ["| method | TGC | SGC | mean fraction of unit tests passed | task_completed called |", "|---|---|---|---|---|"]
        for m in METHODS:
            d = data[m]
            if not d:
                continue
            rs = [d[t] for t in ids if t in d]
            by = defaultdict(list)
            for r in rs:
                by[r["task_id"].rsplit("_", 1)[0]].append(r["success"])
            sgc = sum(1 for v in by.values() if len(v) == 3 and all(v)) / max(1, len(by))
            fr = [((r.get("extra") or {}).get("eval_info") or {}) for r in rs]
            frac = [e["passes"] / e["num_tests"] for e in fr if e.get("num_tests")]
            comp = sum(1 for e in fr if e.get("task_completed"))
            L.append(f"| {m} | {pct(sum(r['success'] for r in rs) / len(rs))} | {pct(sgc)} ({len(by)} scenarios) | "
                     f"{pct(sum(frac) / max(1, len(frac)))} | {comp}/{len(rs)} |")
    else:
        L += ["| method | accuracy | mean search calls | mean get_document calls | no answer submitted |", "|---|---|---|---|---|"]
        for m in METHODS:
            d = data[m]
            if not d:
                continue
            rs = [d[t] for t in ids if t in d]
            ev = [((r.get("extra") or {}).get("eval_info") or {}) for r in rs]
            tc = [e.get("tool_counts") or {} for e in ev]
            na = sum(1 for e in ev if e.get("status") == "no_answer")
            L.append(f"| {m} | {pct(sum(r['success'] for r in rs) / len(rs))} | "
                     f"{sum(c.get('search', 0) for c in tc) / len(rs):.1f} | {sum(c.get('get_document', 0) for c in tc) / len(rs):.1f} | "
                     f"{na}/{len(rs)} |")
    return L + [""]


def evolution(bench: str) -> list[str]:
    L = ["Evolution (per round):", ""]
    h0_val = [r for r in load(M / f"h0_{bench}.jsonl") if r.get("phase") == "val"]
    if h0_val:
        L.append(f"- H0 val: {pct(sum(r['success'] for r in h0_val) / len(h0_val))} ({len(h0_val)} tasks)")
    for m in ("b1", "b2", "b3"):
        p = M / "runs" / m / bench / "log.json"
        if not p.exists():  # run stopped before log.json: val scores per candidate from the records
            by = defaultdict(list)
            for r in load(M / f"{m}_{bench}.jsonl"):
                if r.get("phase") == "val" and not credit_error(r):
                    by[r.get("candidate") or r.get("round")].append(r["success"])
            L.append(f"- {m}: (no log.json, run stopped early) val per candidate: "
                     + ", ".join(f"{k}: {pct(sum(v) / len(v))} ({len(v)})" for k, v in by.items()))
            continue
        lg = json.loads(p.read_text())
        rounds = []
        for r in lg.get("rounds", []):
            s = f"r{r.get('round')}: {r.get('result', '?')}"
            if r.get("val") is not None:
                s += f" (val {pct(r['val'])})"
            if m == "b3" and isinstance(r.get("canary"), dict):
                s += f" [canary: {r['canary'].get('reason', '')}]"
            rounds.append(s)
        final = lg.get("final")
        if isinstance(final, dict):
            final = final.get("global", final)
        L.append(f"- {m}: " + "; ".join(rounds) + f" -> final: {final}")
    return L + [""]


def main():
    out = ["# MEDIUM run: results", "",
           "1 seed; 5 evolution rounds; 50 train tasks x 3 rolls; 30 val tasks; fixed 100-task test subsets. "
           "Model `inclusionai/ling-3.0-flash` for agent, proposers and the BrowseComp-Plus judge. "
           "Infra-error episodes count as failures. McNemar: exact, two-sided, on tasks where exactly one of the two "
           "methods succeeded.", ""]
    for b in BENCHES:
        out += bench_section(b)
    s = json.loads((ROOT / "results" / "spend.json").read_text())
    old = sum(v["usd"] for v in smoke_spend().values())
    out.append(f"Total spend of the MEDIUM run: ${s['total_usd'] - old:.2f} (spend.json total ${s['total_usd']:.2f}).")
    (M / "analysis.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
