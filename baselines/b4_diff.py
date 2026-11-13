"""B4 v7: divergence-point branching. Any edit of a harness component is evaluated by forking saved runs at the
first step where the edited harness behaves differently.

v6 (b4_branch.py) forks a saved run where a declared mechanism fires. Here the candidate is ordinary component code
(a new variant of a slot: tool_policy, context_mgmt, verifier, agent_loop), so there is no declared trigger. The
trigger is measured instead:

  1. reference: the saved run is replayed under the harness that produced it; the hash of every request the harness
     sends to the model (messages, tools, tool_choice) is recorded. No model call (cached per saved run).
  2. replay under the candidate: saved responses are served while the candidate sends the same requests. The first
     request that differs is the divergence point: from there the model is called for real.
  3. pair: the continuation is compared with the saved run's outcome, as in v6.

So "the steps where the edit changes what the model sees or what the harness does" is the edit's precondition,
computed on trajectories instead of declared by the proposer (docs/idea_v2.md 3.1: a runnable predicate). It gives,
before any model call (`dry=True`): the share of saved runs the edit touches, the step where it first matters, and
whether it touches failing or passing runs. An edit that touches no run is dead code (F2) and costs nothing.

A run counts as changed when a request differs, when the candidate asks for a response the saved run does not have
(terminal divergence: the saved run was over, so its outcome from that state is certain), or when the executed
actions differ although every request matched (e.g. the run ends earlier). Otherwise it is the saved run.
Cross-episode components (memory) are out of scope: a saved run must not depend on other runs.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

from baselines import b4_branch as V
from baselines import common as C


class DryStop(Exception):
    """Raised at the divergence point of a dry replay (no model call is made)."""


def req_hash(msgs, tools, kw: dict) -> str:
    blob = json.dumps([msgs, tools, kw.get("tool_choice")], sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def _saved(e: dict):
    """A saved response served again. It carries the tokens it cost when it was made (and no new cost): a branch
    is then a whole run, comparable with the saved run it forks on every feature."""
    return SimpleNamespace(content=e.get("content") or "", tool_calls=e.get("tool_calls") or [], message={},
                           prompt_tokens=int(e.get("pt") or 0), completion_tokens=int(e.get("ct") or 0), cost=0.0,
                           latency_s=0.0, raw={})


class DiffLLM:
    """Serves a saved run's agent responses while the harness sends the reference requests; goes live at the first
    request that differs. `ref=None` records the reference hashes instead (and never calls the model)."""

    def __init__(self, real, events: list[dict], ref: list[str] | None = None, dry: bool = False,
                 judge: bool = False):
        self.real, self.ref, self.dry, self.judge = real, ref, dry, judge
        self.saved = [e for e in events if e.get("type") == "llm" and "check" not in e]
        self.hashes: list[str] = []
        self.i, self.live, self.fork_call = 0, False, None

    def chat(self, msgs, tools=None, tag: str = "", **kw):
        agent = str(tag).startswith("h:") and not str(tag).endswith(":check")
        if self.ref is None:  # recording the reference
            if not agent:
                return SimpleNamespace(content="", tool_calls=[], message={}, prompt_tokens=0, completion_tokens=0,
                                       cost=0.0, latency_s=0.0, raw={})
            if self.i >= len(self.saved):
                raise RuntimeError("replay overrun: the source harness asks for more responses than were saved")
            self.hashes.append(req_hash(msgs, tools, kw))
            self.i += 1
            return _saved(self.saved[self.i - 1])
        if agent and not self.live:
            if self.i < len(self.saved) and self.i < len(self.ref) and req_hash(msgs, tools, kw) == self.ref[self.i]:
                self.i += 1
                return _saved(self.saved[self.i - 1])
            self.live, self.fork_call = True, self.i
        if self.dry and self.live:
            raise DryStop(f"diverged at call {self.fork_call}")
        if not agent and not self.live:
            if not str(tag).startswith("judge"):  # an auxiliary model call the source harness never made
                self.live, self.fork_call = True, self.i
                if self.dry:
                    raise DryStop(f"diverged at call {self.fork_call}")
            elif not self.judge:  # an unchanged run keeps its saved verdict: no judge call
                return _saved({})
        return self.real.chat(msgs, tools=tools, tag=tag, **kw)

    def __getattr__(self, k):
        return getattr(self.real, k)


def _steps(events: list[dict]) -> list:
    return [(e.get("tool"), json.dumps(e.get("args"), sort_keys=True, default=str)) for e in events
            if e.get("type") == "step"]


def reference(bench: str, split: str, src: dict, src_root, cache: Path) -> dict:
    """Request hashes of a saved run under the harness that produced it: {"hashes": [...], "faithful": bool}.
    `faithful` is False when the replay does not reproduce the saved run's actions and observations (the
    environment is not deterministic for this run): such a run cannot be forked."""
    f = cache / f"{V._fid(src['trajectory_path'])}.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    ev = V.load_events(src["trajectory_path"])
    bl = DiffLLM(None, ev)
    res = C.adapter(bench).run_episode(src["task_id"], C.LazyHarness(src_root), bl, split=split,
                                       run_tag=f"ref_{V._fid(src['trajectory_path'])}")
    new = V.load_events(res.trajectory_path)
    obs = lambda evs: [str(e.get("observation")) for e in evs if e.get("type") == "step"]  # noqa: E731
    ok = not res.error and bl.i == len(bl.saved) and _steps(new) == _steps(ev) and obs(new) == obs(ev)
    out = {"hashes": bl.hashes, "faithful": bool(ok), "error": res.error}
    cache.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out), encoding="utf-8")
    return out


def run_diff(bench: str, split: str, srcs: list[dict], root, src_root, client, tag: str, out: Path | None,
             cache: Path, k: int = 0, workers: int = 4, label: dict | None = None, dry: bool = False) -> list[dict]:
    """One branch (index k) of every saved run in `srcs` under the harness at `root`. `dry=True` stops at the
    divergence point: no model call, records only carry `branched` / `fork_call` / `terminal`."""
    ad = C.adapter(bench)
    done = {}
    if out is not None and V.B.RESUME and out.exists() and not dry:
        for line in out.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("fork_of") and str(rec.get("run_tag", "")).startswith(tag + "_k") and not rec.get("error"):
                done[rec["run_tag"]] = rec

    def one(src):
        run_tag = f"{tag}_{'dry' if dry else 'k' + str(k)}_{V._fid(src['trajectory_path'])}"
        if run_tag in done:
            return done[run_tag]
        ref = reference(bench, split, src, src_root, cache)
        base = {"task_id": src["task_id"], "split": split, "run_tag": run_tag, "root": str(root), **(label or {}),
                "fork_of": src["trajectory_path"], "src_success": bool(src["success"]), "k": k}
        if not ref["faithful"]:
            return {**base, "success": bool(src["success"]), "branched": False, "unfaithful": True, "error": None}
        ev = V.load_events(src["trajectory_path"])
        bl = DiffLLM(client, ev, ref["hashes"], dry=dry)
        t0 = time.time()
        res = ad.run_episode(src["task_id"], C.LazyHarness(root), bl, split=split, run_tag=run_tag)
        err = None if dry and bl.live else res.error
        same = not bl.live and not err and bl.i == len(bl.saved) and _steps(V.load_events(res.trajectory_path)) == _steps(ev)
        if not same and not bl.live and not err and not dry:  # ended differently without a new request: judge it
            bl = DiffLLM(client, ev, ref["hashes"], judge=True)
            res = ad.run_episode(src["task_id"], C.LazyHarness(root), bl, split=split, run_tag=run_tag)
            err = res.error
        rec = {**dataclasses.asdict(res), **base, "error": err, "wall_s": round(time.time() - t0, 1),
               "model": getattr(client, "model", None), "branched": not same and not err, "fork_call": bl.fork_call,
               "replayed": bl.i, "n_saved": len(bl.saved),
               "tokens_replayed": sum(int(e.get("pt") or 0) + int(e.get("ct") or 0) for e in bl.saved[:bl.i]),
               # terminal: the candidate continues after the saved run's last response, or ends differently with
               # every request identical: the saved run's outcome from the divergence state is certain
               "terminal": bool(not same and not err and (not bl.live or bl.fork_call >= len(bl.saved)))}
        if same or dry:  # unchanged: this is the saved run (the judge is not re-asked)
            rec["success"] = bool(src["success"])
        if out is not None and not dry:
            C.append_jsonl(out, rec)
            print(f"    [{run_tag}] {src['task_id'][:40]:40s} ok={rec['success']} was={src['success']} "
                  f"branched={rec['branched']} at={bl.fork_call}/{len(bl.saved)} tok={res.tokens} "
                  f"err={(err or '')[:60]}", flush=True)
        return rec

    memo = _dry_memo(root, src_root, split, srcs, cache) if dry and V.B.RESUME else None
    if memo is not None and memo.exists():
        try:
            return json.loads(memo.read_text(encoding="utf-8"))
        except Exception:
            pass
    if bench == "appworld" or workers <= 1:
        recs = [one(s) for s in srcs]
    else:
        with ThreadPoolExecutor(max_workers=min(4, workers)) as ex:
            recs = list(ex.map(one, srcs))
    if memo is not None and not any(x.get("error") for x in recs):
        memo.parent.mkdir(parents=True, exist_ok=True)
        memo.write_text(json.dumps(recs, default=str), encoding="utf-8")
    return recs


def _dry_memo(root, src_root, split, srcs, cache: Path) -> Path:
    """A dry replay calls no model and is a function of the two harnesses' code and the saved runs: on resume it is
    read back instead of recomputed (keyed by content, so a rewritten candidate is replayed again)."""
    key = hashlib.sha1(json.dumps([C.tree_hash(Path(root)), C.tree_hash(Path(src_root)), split,
                                   [s["trajectory_path"] for s in srcs]]).encode("utf-8")).hexdigest()[:20]
    return Path(cache).parent / "dry_memo" / f"{key}.json"


def divergence_map(recs: list[dict]) -> dict:
    """What an edit touches, from a dry replay: coverage, where it first matters, and on which runs."""
    ok = [x for x in recs if not x.get("unfaithful") and not x.get("error")]
    b = [x for x in ok if x["branched"]]
    pos = sorted((x["fork_call"] if x.get("fork_call") is not None else x["n_saved"]) / max(1, x["n_saved"]) for x in b)
    fail = [x for x in ok if not x["src_success"]]
    good = [x for x in ok if x["src_success"]]
    return {"n": len(ok), "unfaithful": sum(1 for x in recs if x.get("unfaithful")),
            "errors": sum(1 for x in recs if x.get("error")),
            "touched": len(b), "coverage": round(len(b) / max(1, len(ok)), 3),
            "terminal": sum(1 for x in b if x["terminal"]),
            "at_first_call": sum(1 for x in b if x.get("fork_call") == 0),
            "median_position": round(pos[len(pos) // 2], 2) if pos else None,
            "touched_failing": round(sum(1 for x in fail if x["branched"]) / max(1, len(fail)), 3),
            "touched_passing": round(sum(1 for x in good if x["branched"]) / max(1, len(good)), 3)}


def estimate(srcs: list[dict], recs: list[dict]) -> dict:
    """Score of the edited harness on the saved runs: untouched runs keep their outcome, touched runs take the mean
    of their branches. Paired tallies per branch and per saved run."""
    by: dict[str, list] = {}
    for x in recs:
        if x.get("branched") and not x.get("error"):
            by.setdefault(x["fork_of"], []).append(x)
    base = sum(bool(s["success"]) for s in srcs) / max(1, len(srcs))
    est, tw, tl, allb = 0.0, 0, 0, []
    for s in srcs:
        b = by.get(s["trajectory_path"], [])
        m = sum(1 for x in b if x["success"]) / len(b) if b else float(bool(s["success"]))
        est += m
        tw += m > float(bool(s["success"]))
        tl += m < float(bool(s["success"]))
        allb += b
    t = V.tally(allb)
    n = max(1, len(srcs))
    return {"base": round(base, 4), "est": round(est / n, 4), "gain": round(est / n - base, 4), "n": len(srcs),
            "touched": len(by), "task_wins": tw, "task_losses": tl, "task_p": round(V.sign_p(tw, tl), 4),
            "branch": {k: t[k] for k in ("W", "L", "n", "p", "Wt", "Lt")},
            "errors": sum(1 for x in recs if x.get("error")), "tokens": sum(x.get("tokens") or 0 for x in recs)}
