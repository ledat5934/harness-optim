"""B4 v6: trigger-point branching. Mechanisms are evaluated by forking saved runs at the step where they fire.

A gated mechanism (`precondition -> action`) leaves an episode untouched until its precondition first holds. So the
effect of a candidate on a run that already exists can be measured without running the episode again:

  1. replay: the saved run is re-executed with the candidate installed. The agent's saved responses are served back
     in order (no model call, `BranchLLM`); the environment is stepped for real, so its state is rebuilt exactly.
  2. branch: at the first step where the candidate fires, the run goes live: from there on the model is called.
  3. pair: the continuation is compared with what the saved run did from the same state (its recorded outcome).

Runs are sampled without looking at their outcome, so the recorded outcome is an unbiased sample of the "no
mechanism" arm from the fork state: the control arm costs nothing. The two arms share the whole prefix, so the
paired difference carries only the noise of the suffix. A run in which the candidate never fires is the saved run
(difference exactly 0), where a full re-run would add sampling noise as large as the effects being measured
(docs/luna_results.md section 12: three runs of the same harness scored 18%, 23% and 27%).

The same estimator is used at every stage:
  - screening: forks of the current harness's train runs where the precondition is predicted to fire (two stages);
  - confirmation: forks of its val runs (held-out tasks), K branches each;
  - after a merge: the new harness's train/val runs are the old runs with the fired ones replaced by a branch;
  - test: `test_branch` = H0's test runs with the fired ones replaced by the mean of K branches. A standard full
    re-run of the final harness is still reported as `test`, for comparison with B1-B3.
Proposer, failure modes, lint and replay pre-check are those of b4_repertoire (v4/v5).
Env: B4_N_FORK (24), B4_K_VAL (2), B4_K_TEST (3), B4_ALPHA (0.15), plus the b4_repertoire ones (B4_TAG, B4_SEED, ...).
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import os
import random
import shutil
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

from baselines import b4_modes as G
from baselines import b4_repertoire as B
from baselines import common as C
from baselines.hg import runtime as R

N_FORK = int(os.environ.get("B4_N_FORK", "24"))     # forks per screening stage (two stages at most)
K_VAL = int(os.environ.get("B4_K_VAL", "2"))        # branches per fired val run
K_TEST = int(os.environ.get("B4_K_TEST", "3"))      # branches per fired test run
ALPHA = float(os.environ.get("B4_ALPHA", "0.15"))   # one-sided sign test level for admission after screening
MARGIN = 2                                          # wins - losses needed at screening and at confirmation


# ---------------------------------------------------------------- replay client
class BranchLLM:
    """Serves the agent responses of a saved run until a branch mechanism fires (or `live_at` responses were
    served), then forwards to the real client. Judge, report and tier-2 check calls are always forwarded."""

    def __init__(self, real, events: list[dict], branch_ids=(), live_at: int | None = None):
        self.real = real
        self.saved = [e for e in events if e.get("type") == "llm" and "check" not in e]
        self.checks: dict[str, list[bool]] = defaultdict(list)
        for e in events:
            if e.get("type") == "mech_check" and "yes" in e:
                self.checks[e["id"]].append(bool(e["yes"]))
        self.branch_ids, self.live_at = set(branch_ids), live_at
        self.i, self.live, self.fork_call, self.fired = 0, False, None, False

    def _go_live(self) -> None:
        if not self.live:
            self.live, self.fork_call = True, self.i

    def on_fire(self, mech_id: str) -> None:  # called by HookedLoop when a mechanism fires
        if mech_id in self.branch_ids:
            self.fired = True
            self._go_live()

    def saved_check(self, mech_id: str):  # recorded tier-2 verdict of a mechanism that was already in the harness
        if self.live or mech_id in self.branch_ids or not self.checks[mech_id]:
            return None
        return self.checks[mech_id].pop(0)

    def chat(self, msgs, tools=None, tag: str = "", **kw):
        agent = str(tag).startswith("h:") and not str(tag).endswith(":check")
        if agent and not self.live:
            if self.i < len(self.saved) and (self.live_at is None or self.i < self.live_at):
                e = self.saved[self.i]
                self.i += 1
                return SimpleNamespace(content=e.get("content") or "", tool_calls=e.get("tool_calls") or [],
                                       message={}, prompt_tokens=0, completion_tokens=0, cost=0.0, latency_s=0.0,
                                       raw={})
            self._go_live()  # the saved run has no response for this call: continue with the model
        return self.real.chat(msgs, tools=tools, tag=tag, **kw)

    def __getattr__(self, k):
        return getattr(self.real, k)


def load_events(path: str) -> list[dict]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")).get("events", [])
    except Exception:
        return []


def _fid(path: str) -> str:
    return hashlib.sha1(str(path).encode()).hexdigest()[:8]


def run_forks(bench: str, split: str, srcs: list[dict], root: Path, client, tag: str, out: Path, branch_ids,
              k: int = 0, workers: int = 4, label: dict | None = None) -> list[dict]:
    """One branch (index k) of every saved run in `srcs` ({task_id, success, trajectory_path}) under the harness at
    `root`. Returns one record per source, with `branched` (a branch mechanism fired), `src`, `src_success`."""
    ad = C.adapter(bench)
    done = {}
    if B.RESUME and out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("fork_of") and str(rec.get("run_tag", "")).startswith(tag + "_k") and not rec.get("error"):
                done[rec["run_tag"]] = rec

    def one(src):
        run_tag = f"{tag}_k{k}_{_fid(src['trajectory_path'])}"
        if run_tag in done:
            return done[run_tag]
        bl = BranchLLM(client, load_events(src["trajectory_path"]), branch_ids)
        h = C.LazyHarness(root)
        t0 = time.time()
        res = ad.run_episode(src["task_id"], h, bl, split=split, run_tag=run_tag)
        rec = {**dataclasses.asdict(res), "split": split, "run_tag": run_tag, "root": str(root),
               "wall_s": round(time.time() - t0, 1), "model": getattr(client, "model", None), **(label or {}),
               "fork_of": src["trajectory_path"], "src_success": bool(src["success"]), "k": k,
               "branched": bool(bl.fired), "fork_call": bl.fork_call, "replayed": bl.i}
        if not bl.live and not rec.get("error"):  # nothing changed: this is the saved run (the judge is not re-asked)
            rec["success"] = bool(src["success"])
        C.append_jsonl(out, rec)
        print(f"    [{run_tag}] {src['task_id'][:40]:40s} ok={rec['success']} was={src['success']} "
              f"branched={rec['branched']} at={bl.fork_call} tok={res.tokens} err={(res.error or '')[:60]}", flush=True)
        return rec

    if bench == "appworld" or workers <= 1:
        return [one(s) for s in srcs]
    with ThreadPoolExecutor(max_workers=min(4, workers)) as ex:
        return list(ex.map(one, srcs))


# ---------------------------------------------------------------- estimator
def sign_p(w: int, l: int) -> float:
    """One-sided sign test: P(at least w wins out of w + l discordant pairs) under no effect."""
    n = w + l
    return 1.0 if n == 0 else sum(math.comb(n, i) for i in range(w, n + 1)) / 2 ** n


def tally(recs: list[dict]) -> dict:
    """Paired outcome of branches against the saved runs they fork. Only branched runs carry information."""
    b = [x for x in recs if x.get("branched") and not x.get("error")]
    w = sum(1 for x in b if x["success"] and not x["src_success"])
    l = sum(1 for x in b if x["src_success"] and not x["success"])
    return {"W": w, "L": l, "n": len(b), "ran": len(recs), "p": round(sign_p(w, l), 4),
            "errors": sum(1 for x in recs if x.get("error")),
            "tokens": sum(x.get("tokens") or 0 for x in recs)}


def predicted(mechs: list[dict], recs: list[dict], fin) -> list[dict]:
    """Saved runs on which at least one of the mechanisms is predicted to fire (tier 1, offline replay)."""
    codes = [(R.compile_pre(m["precondition"]), m["kind"]) for m in mechs]
    return [x for x in recs if x.get("trajectory_path") and Path(x["trajectory_path"]).exists()
            and any(R.replay_fires(c, x["trajectory_path"], kind, fin) for c, kind in codes)]


def branch_screen(bench, split, cand: dict, base: list[dict], cur: list[dict], ws: Path, client, out: Path, cfg: dict,
                  rng: random.Random, r: int, fin) -> dict:
    """Screening of one candidate on top of the current set: forks of the current harness's train runs."""
    pool = predicted([cand], cur, fin)
    cover = len(pool) / max(1, len(cur))
    if not pool:
        return {"status": "rejected", "reason": "predicted to fire on no saved run", "evidence": {"coverage": 0.0}}
    root = B.make_root(ws, f"r{r}_{cand['id']}", list(base) + [cand])
    ok, glog = C.static_gate(root)
    if not ok:
        return {"status": "rejected", "reason": "static gate: " + glog[-200:]}
    rng.shuffle(pool)
    tag = f"{B.TAG}_{bench}_r{r}_{cand['id']}"
    label = {"method": "b4", "phase": "screen", "round": r, "cand": cand["id"], "base": [m["id"] for m in base]}
    recs, stage = [], 0
    for stage in (1, 2):
        lo = (stage - 1) * N_FORK
        if lo < len(pool):
            srcs, k = pool[lo:lo + N_FORK], 0
        else:  # fewer fork points than the budget: a second branch of the same forks
            srcs, k = pool[:N_FORK], 1
        recs += run_forks(bench, split, srcs, root, client, tag, out, {cand["id"]}, k, cfg["workers"], label)
        t = tally(recs)
        if stage == 1 and t["W"] <= t["L"]:
            break
    t = tally(recs)
    rate = (t["W"] - t["L"]) / max(1, t["n"])
    ev = {**t, "stages": stage, "coverage": round(cover, 3), "pred": len(pool), "dT": round(rate, 3),
          "dS": round(-t["L"] / max(1, t["n"]), 3), "fired": t["n"],
          # expected change of the success rate over all train runs: P(fires) x effect when it fires
          "gain": round(cover * (t["n"] / max(1, t["ran"])) * rate, 4)}
    res = {"evidence": ev, "_recs": recs, "_root": root}
    if t["n"] == 0:
        return {**res, "status": "rejected", "reason": "never fired (no credit)"}
    if t["W"] - t["L"] < MARGIN or t["p"] > ALPHA:
        return {**res, "status": "rejected",
                "reason": f"no reliable gain at the fork points ({t['W']}W/{t['L']}L of {t['n']}, p={t['p']})"}
    return {**res, "status": "admitted"}


def advance(bench, split, recs: list[dict], new: list[dict], root: Path, client, tag: str, out: Path, cfg: dict,
            fin, have: dict | None = None, label: dict | None = None) -> list[dict]:
    """Runs of the harness after a merge: a saved run where no new mechanism fires IS a run of the new harness; the
    others are replaced by one branch (`have`: branches already run under this exact set, by source path)."""
    have = have or {}
    fired = {x["trajectory_path"] for x in predicted(new, recs, fin)}
    todo = [x for x in recs if x["trajectory_path"] in fired and x["trajectory_path"] not in have]
    got = {x["fork_of"]: x for x in run_forks(bench, split, todo, root, client, tag, out, {m["id"] for m in new}, 0,
                                              cfg["workers"], label)} if todo else {}
    out_recs = []
    for x in recs:
        b = have.get(x["trajectory_path"]) or got.get(x["trajectory_path"])
        out_recs.append(b if b and not b.get("error") and b.get("trajectory_path") else x)
    return out_recs


def branch_test(bench, split, h0_test: list[dict], mechs: list[dict], root: Path, client, out: Path, cfg: dict) -> dict:
    """Low-noise test estimate: every H0 test run is replayed under the final set (exact firing, no model call until
    a mechanism fires); a run where nothing fires keeps H0's outcome, the others get the mean of K_TEST branches."""
    srcs = [x for x in h0_test if x.get("trajectory_path") and Path(x["trajectory_path"]).exists()]
    base = sum(1 for x in srcs if x["success"]) / max(1, len(srcs))
    if not mechs or not srcs:
        return {"h0": round(base, 4), "est": round(base, 4), "gain": 0.0, "n": len(srcs), "fired": 0}
    ids, tag = {m["id"] for m in mechs}, f"{B.TAG}_{bench}_{split}fork_" + "_".join(sorted(m["id"] for m in mechs))
    label = {"method": "b4", "phase": "test_branch"}
    first = run_forks(bench, split, srcs, root, client, tag, out, ids, 0, cfg["workers"], label)
    hit = [s for s, x in zip(srcs, first) if x.get("branched")]
    by = defaultdict(list)
    for x in first:
        by[x["fork_of"]].append(x)
    for k in range(1, K_TEST):
        for x in run_forks(bench, split, hit, root, client, tag, out, ids, k, cfg["workers"], label):
            by[x["fork_of"]].append(x)
    est, tw, tl, allb = 0.0, 0, 0, []
    for s in srcs:
        b = [x for x in by[s["trajectory_path"]] if x.get("branched") and not x.get("error")]
        m = sum(1 for x in b if x["success"]) / len(b) if b else float(bool(s["success"]))
        est += m
        tw += m > float(bool(s["success"]))
        tl += m < float(bool(s["success"]))
        allb += b
    t = tally(allb)
    return {"h0": round(base, 4), "est": round(est / len(srcs), 4), "gain": round(est / len(srcs) - base, 4),
            "n": len(srcs), "fired": len(hit), "k": K_TEST, "task_wins": tw, "task_losses": tl,
            "task_p": round(sign_p(tw, tl), 4), "branch": {k: t[k] for k in ("W", "L", "n", "p")}}


# ---------------------------------------------------------------- main loop
def run(bench: str, shared: dict, client, cfg: dict = C.SMOKE) -> dict:
    ws = C.RUNS / B.TAG / bench
    if ws.exists() and not B.RESUME:
        shutil.rmtree(ws)
    ws.mkdir(parents=True, exist_ok=True)
    out = C.OUT / f"{B.TAG}_{bench}.jsonl"
    if out.exists() and not B.RESUME:
        out.unlink()
    client = B._Replay(client, ws / "llm_cache.jsonl")
    tasks = shared["tasks"]
    tr_split, val_split = tasks["train"][0], tasks["val"][0]
    rng = random.Random(B.SEED)
    fin = B.FINISH.get(bench)

    def usable(recs):
        return [x for x in recs if x.get("trajectory_path") and Path(x["trajectory_path"]).exists()]
    cur, curv = usable(shared["h0_train"]), usable(shared["h0_val"])
    if len(cur) < len(shared["h0_train"]) or len(curv) < len(shared["h0_val"]):
        raise SystemExit("B4 v6 forks the saved H0 runs: every H0 train/val record needs its trajectory file")
    sigs, instructions, tools = {}, [], set()
    for rec in cur + curv:
        sigs[rec["trajectory_path"]] = R.trajectory_signals(rec["trajectory_path"], fin)
        for e in load_events(rec["trajectory_path"]):
            if e["type"] == "task":
                instructions.append(str(e.get("instruction") or ""))
            elif e["type"] == "step":
                tools.add(e.get("tool"))
    linter = B.Linter(instructions, sorted({x["task_id"] for x in cur}) + list(tasks["val"][1]), {t for t in tools if t})
    prof0 = B.profile([sigs[x["trajectory_path"]] for x in cur])
    (ws / "profile.json").write_text(json.dumps({"model": client.model, "harness": "h0", "profile": prof0}, indent=1))

    pool: list[dict] = []
    incumbent: list[dict] = []
    inc_root = C.H0_ROOT
    log = {"version": "v6-branch", "rounds": [], "profile_h0": prof0,
           "params": {"n_fork": N_FORK, "k_val": K_VAL, "k_test": K_TEST, "alpha": ALPHA, "margin": MARGIN}}
    registry: dict = {}
    frozen: set[str] = set()
    mode_tries: Counter = Counter()
    stall = 0
    for r in range(1, cfg["rounds"] + 1):
        C.budget_check(f"b4[{bench}] round {r}")
        rd = {"round": r, "train": round(C.score(cur), 4), "val": round(C.score(curv), 4)}
        fails = [x for x in cur if not x["success"]]
        modes = Counter(m for x in fails for m in B.failure_modes(sigs.get(x["trajectory_path"], {})) if m not in frozen)
        reps = B.reports(client, cur, sigs, rng, bench)
        rd["calibration"] = B.calibration(reps)
        mt, mode_info = {}, None
        if B.LLM_MODES:
            labelled = [{"task_id": x["task_id"], "label": str(h.get("failure_label") or h.get("why") or "")[:120],
                         "why": str(h.get("why") or "")[:200], "cause": h.get("cause"), "rule_modes": x["modes"]}
                        for x in reps if not x["success"] for h in [x.get("hindsight") or {}] if h.get("cause")]
            registry = G.discover_modes(client, bench, labelled, registry, linter.tools, B._ask_json)
            mt = G.mode_tasks(registry, fails, sigs)
            mode_info = G.mode_counts(registry, mt, frozen) or None
        dig = list(fails)
        rng.shuffle(dig)
        digests = [C.summarize_trajectory(x["trajectory_path"], max_events=24, max_chars=300, task_chars=400)
                   for x in dig[:5]]
        prof = B.profile([sigs[x["trajectory_path"]] for x in cur])
        d, _ = B.propose(client, bench, prof, modes, reps, digests, pool, linter.tools, r, ws, frozen, mode_info,
                         G.graph_view(G.build_graph(pool, registry)))
        rd["failure_mode"] = d.get("failure_mode")
        rd["analysis"] = str(d.get("analysis", ""))[:500]
        by_task = defaultdict(list)
        for x in cur:
            by_task[x["task_id"]].append(1.0 if x["success"] else 0.0)
        p_base = {t: sum(v) / len(v) for t, v in by_task.items()}
        admitted, extra = [], {}
        for branch in ("structural", "guidance"):
            cid = f"m{len(pool) + 1}"
            spec = d.get(branch)
            entry = {"id": cid, "round": r, "branch": branch, "failure_mode": d.get("failure_mode"), "status": "",
                     "kind": "", "precondition": "", "text": ""}
            try:
                m = R.validate_mechanism({**(spec or {}), "id": cid, **({} if B.LLM_CHECK else {"llm_check": ""})})
                if (branch == "guidance") != (m["kind"] == "guidance"):
                    raise ValueError(f"branch {branch} got kind {m['kind']}")
                entry.update(m)
                if d.get("failure_mode") in frozen:
                    raise ValueError(f"failure mode {d.get('failure_mode')} is frozen")
                why = linter.check(m)
                if why:
                    raise ValueError("generalization gate: " + why)
                if m["kind"] != "guidance":
                    m, pc = B.precheck_revise(client, bench, m, d.get("failure_mode"), mt, fails, cur, sigs, p_base,
                                              linter, fin, r, ws)
                    entry.update(m, precheck=pc)
                    if pc["pred_fail"] == 0:
                        raise ValueError(f"precheck: predicted to fire on 0 of {pc['n_fail']} targeted failed runs")
            except Exception as e:
                entry.update(status="rejected", reason=str(e)[:200], kind=(spec or {}).get("kind", ""),
                             precondition=str((spec or {}).get("precondition", "")),
                             text=str((spec or {}).get("text", "")))
                pool.append(entry)
                continue
            res = branch_screen(bench, tr_split, entry, incumbent, cur, ws, client, out, cfg, rng, r, fin)
            extra[cid] = {"recs": res.pop("_recs", []), "root": res.pop("_root", None)}
            entry.update(res)
            pool.append(entry)
            if entry["status"] == "admitted":
                admitted.append(entry)
        rd["candidates"] = [{k: c.get(k) for k in ("id", "branch", "kind", "status", "reason", "evidence")}
                            for c in pool if c["round"] == r]
        # confirmation on held-out tasks: forks of the current harness's val runs, K_VAL branches each
        merged = False
        if admitted:
            trials = [admitted] + ([[max(admitted, key=lambda c: c["evidence"]["gain"])]] if len(admitted) == 2 else [])
            for tset in trials:
                mechs = incumbent + tset
                name = f"r{r}_set{len(mechs)}_" + "_".join(c["id"] for c in tset)
                root = extra[tset[0]["id"]]["root"] if len(tset) == 1 else B.make_root(ws, name, mechs)
                ids = {c["id"] for c in tset}
                vtag = f"{B.TAG}_{bench}_{name}_val"
                vrecs = []
                for k in range(K_VAL):
                    srcs = curv if k == 0 else [s for s, x in zip(curv, vrecs[:len(curv)]) if x.get("branched")]
                    vrecs += run_forks(bench, val_split, srcs, root, client, vtag, out, ids, k, cfg["workers"],
                                       {"method": "b4", "phase": "val", "round": r, "set": [m["id"] for m in mechs]})
                t = tally(vrecs)
                rd.setdefault("val_trials", []).append({"set": [c["id"] for c in mechs], **t})
                if t["W"] - t["L"] >= MARGIN:
                    lab = {"method": "b4", "phase": "inc_train", "round": r}
                    have = {x["fork_of"]: x for x in extra[tset[0]["id"]]["recs"] if x["k"] == 0} if len(tset) == 1 else {}
                    cur = advance(bench, tr_split, cur, tset, root, client, f"{B.TAG}_{bench}_{name}_train", out, cfg,
                                  fin, have, lab)
                    curv = advance(bench, val_split, curv, tset, root, client, vtag, out, cfg, fin,
                                   {x["fork_of"]: x for x in vrecs if x["k"] == 0})
                    for x in cur + curv:
                        if x["trajectory_path"] not in sigs:
                            sigs[x["trajectory_path"]] = R.trajectory_signals(x["trajectory_path"], fin)
                    incumbent, inc_root, merged = mechs, root, True
                    for c in tset:
                        c["status"] = "in_set"
                    rd["result"] = (f"new set {[c['id'] for c in mechs]} train={C.score(cur):.3f} "
                                    f"val={C.score(curv):.3f}")
                    break
                for c in tset:
                    c.setdefault("conflicts", []).append([x["id"] for x in mechs if x is not c])
            else:
                rd["result"] = f"kept set (val {C.score(curv):.3f})"
        else:
            rd["result"] = "no candidate admitted"
        if merged:
            stall = 0
        else:
            stall += 1
            if d.get("failure_mode"):
                mode_tries[d["failure_mode"]] += 1
                if mode_tries[d["failure_mode"]] >= B.MODE_FREEZE:
                    frozen.add(d["failure_mode"])
        rd["frozen"] = sorted(frozen)
        log["rounds"].append(rd)
        (ws / "pool.json").write_text(json.dumps(pool, indent=1, default=str))
        (ws / "graph.json").write_text(json.dumps(G.build_graph(pool, registry, client.model), indent=1, default=str))
        (ws / "log.json").write_text(json.dumps(log, indent=1, default=str))
        print(f"  [b4 {bench}] round {r}: mode={rd['failure_mode']} cands="
              f"{[(c['id'], c['status'], (c.get('evidence') or {}).get('W'), (c.get('evidence') or {}).get('L'), (c.get('evidence') or {}).get('n')) for c in pool if c['round'] == r]}"
              f" -> {rd['result']}", flush=True)
        if stall >= B.STALL_ROUNDS and B.MIN_ROUNDS <= r < cfg["rounds"]:
            log["early_stop"] = {"round": r, "reason": f"{stall} rounds without a merge"}
            print(f"  [b4 {bench}] early stop after round {r}", flush=True)
            break
    # ---- freeze and test
    log["final"] = {"root": str(inc_root), "set": [c["id"] for c in incumbent], "val": C.score(curv)}
    (ws / "final.json").write_text(json.dumps({"final_root": str(inc_root), "set": incumbent, "val": C.score(curv)},
                                              indent=1, default=str))
    C.budget_check(f"b4[{bench}] test")
    h0_test = shared.get("h0_test") or []
    log["test_branch"] = branch_test(bench, tasks["test"][0], h0_test, incumbent, inc_root, client, out, cfg)
    print(f"  [b4 {bench}] test_branch: {log['test_branch']}", flush=True)
    if incumbent:  # standard full re-run, comparable with B1-B3 (noisier: every episode is sampled again)
        test = B._evaluate(bench, tasks["test"][0], tasks["test"][1], inc_root, client, f"{B.TAG}_{bench}_test", out,
                           workers=cfg["workers"], label={"method": "b4", "phase": "test"})
    else:          # the final harness is H0: its test runs are the shared H0 test runs
        test = list(h0_test)
    log["test"] = {"success": C.score(test), "n": len(test), "rerun": bool(incumbent)}
    recs = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines() if l.strip()] if out.exists() else []
    log["cost"] = {"episodes": len(recs), "tokens": sum(x.get("tokens") or 0 for x in recs),
                   "evolution_tokens": sum(x.get("tokens") or 0 for x in recs if x.get("phase") not in ("test", "test_branch"))}
    (ws / "log.json").write_text(json.dumps(log, indent=1, default=str))
    return {"log": log, "test": test}
