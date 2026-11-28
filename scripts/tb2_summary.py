"""Summarise the small TB2 comparison (scripts/tb2_compete.sh): per task and per arm the reward, and per arm the
score, agent wall time, tokens and LLM calls. Harbor arms are read from results/tb2/jobs/<arm>__test__<task>,
H0 (and B4 when given) from the tb2small jsonl records. Only rewards and counts are printed, never task text.
Usage: python3 scripts/tb2_summary.py [--b4-tag TAG] [--md]"""
import argparse
import glob
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOBS = ROOT / "results/tb2/jobs"
ARMS = ["mh_kira", "mh_art", "mr_static", "mr_dyn"]


def _secs(span):
    if not span or not span.get("started_at") or not span.get("finished_at"):
        return None
    f = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))
    return (f(span["finished_at"]) - f(span["started_at"])).total_seconds()


def harbor_trial(arm, task):
    for f in glob.glob(str(JOBS / f"{arm}__test__{task}/**/result.json"), recursive=True):
        d = json.load(open(f))
        if "verifier_result" not in d and "agent_result" not in d:
            continue
        rew = ((d.get("verifier_result") or {}).get("rewards") or {}).get("reward")
        ar = d.get("agent_result") or {}
        md = ar.get("metadata") or {}
        return {"reward": None if rew is None else float(rew), "error": bool(d.get("exception_info")) and rew is None,
                "agent_s": _secs(d.get("agent_execution")), "in_tok": ar.get("n_input_tokens") or 0,
                "out_tok": ar.get("n_output_tokens") or 0, "calls": len(md.get("api_request_times_msec") or [])}
    return None


def jsonl_trials(path, run_tag_prefix):
    out = {}
    p = ROOT / path
    for line in (p.read_text().splitlines() if p.exists() else []):
        r = json.loads(line)
        if r.get("phase") != "test" or not str(r.get("run_tag", "")).startswith(run_tag_prefix):
            continue
        ex = r.get("extra") or {}
        out[r["task_id"]] = {"reward": 1.0 if r.get("success") else 0.0, "error": bool(r.get("error")),
                             "agent_s": (ex.get("eval_info") or {}).get("agent_wall_s"),
                             "in_tok": r.get("tokens") or 0, "out_tok": 0, "calls": ex.get("llm_calls") or 0}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--b4-tag", default="")
    ap.add_argument("--md", action="store_true")
    a = ap.parse_args()
    tasks = json.load(open(ROOT / "benchmarks/terminal_bench2/splits.json"))["test"]
    cols = {arm: {t: harbor_trial(arm, t) for t in tasks} for arm in ARMS}
    cols["h0"] = jsonl_trials("results/tb2small/h0_terminal_bench2.jsonl", "h0_terminal_bench2_test")
    if a.b4_tag:
        cols["b4"] = jsonl_trials("results/tb2small/b4_terminal_bench2.jsonl", a.b4_tag)
    names = list(cols)
    cell = lambda r: "." if r is None else ("E" if r["error"] else str(int(r["reward"] or 0)))
    sep = " | " if a.md else "  "
    print(sep.join(["task".ljust(32)] + [n.ljust(9) for n in names]))
    for t in tasks:
        print(sep.join([t.ljust(32)] + [cell(cols[n].get(t)).ljust(9) for n in names]))
    print()
    print(sep.join(["arm".ljust(10), "solved", "graded", "agent_min_mean", "in_tok_M", "out_tok_k", "llm_calls"]))
    for n in names:
        rs = [r for r in cols[n].values() if r and not r["error"]]
        secs = [r["agent_s"] for r in rs if r["agent_s"]]
        print(sep.join([n.ljust(10), str(sum(int(r["reward"] or 0) for r in rs)), str(len(rs)),
                        f"{(sum(secs) / len(secs) / 60) if secs else 0:.1f}",
                        f"{sum(r['in_tok'] for r in rs) / 1e6:.2f}", f"{sum(r['out_tok'] for r in rs) / 1e3:.1f}",
                        str(sum(r["calls"] for r in rs))]))


if __name__ == "__main__":
    main()
