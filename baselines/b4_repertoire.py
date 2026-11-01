"""B4: repertoire of gated, declarative harness mechanisms (docs/idea_v2.md).

Each round:
  1. failure modes: failed train trajectories of the current harness are tagged with behaviour signatures computed
     from generic signals (baselines/hg/runtime.py), not from the task text.
  2. proactive feedback: a blind report (outcome hidden) and a hindsight report (told it failed) per sampled
     trajectory. Failures attributed to reasoning / ambiguity / environment are not used to propose harness changes.
  3. proposer: two branches from the same evidence, a structural mechanism (inject / annotate_obs / reject_finish:
     middleware with an executable precondition) and a guidance mechanism (system-prompt text).
  4. generalization gate: schema + DSL compile, then a lint against the train/val task texts (ids, 6-word overlaps,
     long digit runs, string constants that are not tool names).
  5. screening: each candidate runs alone on top of H0 on targeted train tasks (H0 failed them with the candidate's
     failure mode) and safe tasks (H0 always passed), paired with the H0 3-roll mean per task. A candidate that never
     fires gets no credit; one that hurts the safe tasks is rejected.
  6. merge (R3): incumbent set + admitted candidates is validated on val against the incumbent set; when the merged
     set loses and two were admitted, the stronger one alone is tried. Losing combinations are recorded as conflicts.
The pool is append-only (immutable ids); the evidence ledger (ledger.jsonl) holds one row per candidate episode.
At test time the final set is frozen; mechanisms fire lazily on their preconditions.
"""
from __future__ import annotations

import json
import random
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path

from baselines import common as C
from baselines.hg import runtime as R
from baselines.proposer_io import extract_json

HOOKED_VARIANT = '''"""agent_loop/hooked: H0 ReAct loop with mechanism hooks (B4; engine in baselines/hg/runtime.py)."""
from baselines.hg.runtime import HookedLoop


def register(reg):
    reg.register("agent_loop", "hooked", lambda c: HookedLoop(**c),
                 "H0 ReAct loop plus declarative precondition->action mechanisms (guidance, inject, annotate_obs, "
                 "reject_finish).", config_schema={"mechanisms": "list of mechanism specs"})
'''

N_TARGET, N_SAFE = 10, 6        # screening tasks per candidate
N_REPORT_FAIL, N_REPORT_PASS = 6, 2
FINISH = {"browsecomp_plus": "finish"}

# ---------------------------------------------------------------- behaviour
MODES = {
    "hedged_answer": "the final answer says the answer is unknown / cannot be determined",
    "early_stop": "stopped while more than half of the step budget was left",
    "budget_exhausted": "ran out of steps (or was forced to answer on the last step)",
    "error_heavy": "many tool observations were error messages",
    "repetition": "repeated identical actions or got identical observations repeatedly",
    "no_tool_call": "stopped after replies without a tool call",
    "other": "none of the above signatures",
}


def failure_modes(s: dict) -> list[str]:
    tags = []
    if s.get("answer_hedged"):
        tags.append("hedged_answer")
    if s.get("stopped") == "no_progress":
        tags.append("no_tool_call")
    if s.get("stopped") == "max_steps" or s.get("steps_left", 1) <= 1:
        tags.append("budget_exhausted")
    elif s.get("step_frac", 1) < 0.5:
        tags.append("early_stop")
    if s.get("n_errors", 0) >= 3 or s.get("err_streak", 0) >= 2:
        tags.append("error_heavy")
    if s.get("repeat_ratio", 0) > 0.2 or s.get("same_obs_streak", 0) >= 2:
        tags.append("repetition")
    return tags or ["other"]


PROFILE_KEYS = ("step_frac", "n_actions", "n_errors", "repeat_ratio", "answer_hedged", "distinct_tools", "tokens")


def profile(sigs: list[dict]) -> dict:
    """Behaviour profile of the model under a harness (docs/idea_v2.md 4.1): means of generic signals."""
    if not sigs:
        return {}
    p = {k: round(sum(float(s.get(k) or 0) for s in sigs) / len(sigs), 3) for k in PROFILE_KEYS}
    p["success"] = round(sum(s["success"] for s in sigs) / len(sigs), 3)
    p["hedged_fail_rate"] = round(sum(1 for s in sigs if s.get("answer_hedged") and not s["success"]) / len(sigs), 3)
    p["early_stop_fail_rate"] = round(sum(1 for s in sigs if "early_stop" in failure_modes(s) and not s["success"])
                                      / len(sigs), 3)
    p["n"] = len(sigs)
    return p


# ---------------------------------------------------------------- gate
class Linter:
    """Generalization gate, tier 1 (static): nothing specific to the tasks it was learned from may leak in."""

    def __init__(self, instructions: list[str], task_ids: list[str], tool_names: set[str]):
        self.ids = [t for t in task_ids if len(t) >= 4]
        self.tools = tool_names
        self.shingles = set()
        for ins in instructions:
            w = re.findall(r"\w+", ins.lower())
            self.shingles.update(" ".join(w[i:i + 6]) for i in range(len(w) - 5))

    def check(self, m: dict) -> str | None:
        blob = f"{m['text']} {m['precondition']}"
        low = blob.lower()
        for t in self.ids:
            if t.lower() in low:
                return "contains a task id"
        w = re.findall(r"\w+", low)
        for i in range(len(w) - 5):
            if " ".join(w[i:i + 6]) in self.shingles:
                return f"copies task text: '{' '.join(w[i:i + 6])}'"
        if re.search(r"\d{4,}", m["text"]):
            return "contains a long number (task-specific literal)"
        for s in re.findall(r"['\"]([^'\"]+)['\"]", m["precondition"]):
            if s not in self.tools:
                return f"string constant {s!r} in the precondition is not a tool name"
        return None


# ---------------------------------------------------------------- proactive feedback
BLIND = """You are reviewing a finished run of an AI agent. You do NOT know whether it succeeded.
Agent run (digest):
{digest}

Answer ONLY with JSON: {{"confidence": <0..1 that the run solved the task>, "difficulty": "<one sentence: what was hard>",
"harness_obstacles": ["<ways the agent's scaffolding (tools, instructions, observations, step budget, stopping rules) got in the way>"]}}"""

HINDSIGHT = """You are reviewing a finished run of an AI agent. The grader marked this run as FAILED.
Agent run (digest):
{digest}

Classify the main cause. "harness" = the scaffolding around the model (tools, observation format, instructions,
stopping/termination rules, step budget, error handling) could reasonably be changed so a model like this succeeds;
"reasoning" = the model had what it needed but reasoned wrongly; "ambiguous" = the task itself is unclear;
"environment" = infrastructure/tool failure outside the agent's control.
Answer ONLY with JSON: {{"cause": "harness|reasoning|ambiguous|environment", "why": "<one sentence>",
"general_fix": "<one sentence, phrased as a rule that would apply to many tasks, or empty>"}}"""


def _ask_json(client, prompt: str, tag: str, max_tokens: int = 1200) -> dict:
    try:
        r = client.chat([{"role": "user", "content": prompt}], tag=tag, max_tokens=max_tokens,
                         fallback_no_reasoning=True)
        d = extract_json(r.content or "")
        return d if isinstance(d, dict) else {}
    except Exception as e:  # feedback is optional evidence, never fatal
        return {"_error": f"{type(e).__name__}: {e}"[:200]}


def reports(client, recs: list[dict], sigs: dict, rng: random.Random, bench: str) -> list[dict]:
    fails = [r for r in recs if not r["success"] and r.get("trajectory_path")]
    passes = [r for r in recs if r["success"] and r.get("trajectory_path")]
    sample = rng.sample(fails, min(N_REPORT_FAIL, len(fails))) + rng.sample(passes, min(N_REPORT_PASS, len(passes)))
    out = []
    for r in sample:
        dig = C.summarize_trajectory(r["trajectory_path"], max_events=30, max_chars=300, show_outcome=False,
                                     task_chars=600)
        b = _ask_json(client, BLIND.format(digest=dig), f"b4:{bench}:blind")
        row = {"task_id": r["task_id"], "success": r["success"], "blind": b,
               "modes": failure_modes(sigs.get(r["trajectory_path"], {}))}
        if not r["success"]:
            row["hindsight"] = _ask_json(client, HINDSIGHT.format(digest=dig), f"b4:{bench}:hindsight")
        out.append(row)
    return out


def calibration(reps: list[dict]) -> dict:
    """Blind confidence vs outcome: is the model's self-report usable as a signal?"""
    pts = [(float(r["blind"].get("confidence", 0.5) or 0.5), r["success"]) for r in reps
           if isinstance(r.get("blind"), dict) and "confidence" in r["blind"]]
    if not pts:
        return {}
    conf_ok = [c for c, s in pts if s]
    conf_fail = [c for c, s in pts if not s]
    return {"mean_conf_success": round(sum(conf_ok) / len(conf_ok), 2) if conf_ok else None,
            "mean_conf_fail": round(sum(conf_fail) / len(conf_fail), 2) if conf_fail else None, "n": len(pts)}


# ---------------------------------------------------------------- proposer
PROPOSE = """You improve the scaffolding ("harness") around an AI agent. The agent model is fixed; you can only add
MECHANISMS. A mechanism is a declarative rule `precondition -> action` that runs inside the agent loop.

## Rules (generalization gate, enforced automatically)
- A mechanism must be a GENERAL principle that would help on tasks never seen. Never mention task ids, specific
  entities, names, answers, file names or text copied from tasks. Long numbers are rejected.
- The precondition must be an observable condition on the run, written in the expression language below.
- Placement: capability gaps -> better use of the existing tools (inject/annotate_obs); enforcement ("do not X")
  -> reject_finish or inject with a precondition; behavioural advice -> guidance. Enforcement written only as advice
  is often ignored by strong models.
- Do not propose fixes for failures whose cause is the model's reasoning, task ambiguity or the environment.
- Do not repeat a mechanism already in the pool (same behaviour, same trigger), especially rejected ones.

## Expression language for preconditions
Python-like boolean expression over these signals (no other names, no attribute access):
{signals}
Functions: n('<tool name>') (times a tool was called), min, max, abs. Tool names available: {tools}.
`text` may contain {{steps_left}}, {{step}}, {{max_steps}} placeholders.

## Mechanism kinds
- guidance: text appended to the system prompt at the start (precondition is usually True).
- inject: a user message inserted before the next model call when the precondition holds (checked every step).
- annotate_obs: a note appended to the tool observation just returned when the precondition holds.
- reject_finish: refuse the agent's final answer with `text` as feedback when the precondition holds (only for tasks
  with a finish tool; the final forced answer on the last step is never refused). {finish_note}
Each mechanism fires at most `max_fires` times per episode (1..5).

## Evidence
Model behaviour profile under the current harness (means over train runs):
{profile}

Failure modes of the current harness on train (count of failed runs per behaviour signature):
{modes}

Self-reports of sampled runs (blind = before knowing the outcome; hindsight = after being told it failed):
{reports}

Digests of failed train runs (outcome shown):
{digests}

## Current pool (status, evidence: dT = mean paired gain on targeted tasks, dS = on safe tasks, fired = tasks where
it fired)
{pool}

## Output
Propose exactly two mechanisms for ONE failure mode that is frequent and attributable to the harness:
a "structural" one (kind inject, annotate_obs or reject_finish) and a "guidance" one (kind guidance).
Answer ONLY with JSON:
{{"failure_mode": "<one of: {mode_names}>", "analysis": "<2-3 sentences>",
  "structural": {{"kind": "...", "slot": "<context|action_interface|tool_policy|observation|error_recovery|orchestration|termination|verification|memory>",
                 "mechanism": "<short name>", "target_behavior": "<behaviour it changes>",
                 "precondition": "<expression>", "text": "<message to the agent>", "max_fires": 1}},
  "guidance": {{"kind": "guidance", "slot": "context", "mechanism": "...", "target_behavior": "...",
               "precondition": "True", "text": "...", "max_fires": 1}}}}"""


def pool_view(pool: list[dict]) -> str:
    if not pool:
        return "(empty)"
    rows = []
    for c in pool:
        e = c.get("evidence", {})
        rows.append(f"- {c['id']} [{c['status']}] {c['kind']} '{c.get('mechanism')}' when `{c['precondition']}`: "
                    f"{c['text'][:160]!r} | dT={e.get('dT')} dS={e.get('dS')} fired={e.get('fired')} "
                    f"{('reason: ' + c['reason']) if c.get('reason') else ''}")
    return "\n".join(rows)


def propose(client, bench: str, prof: dict, modes: Counter, reps: list[dict], digests: list[str], pool: list[dict],
            tools: set[str], r: int, ws: Path) -> tuple[dict, str]:
    usable = [x for x in reps if not x["success"] and x.get("hindsight", {}).get("cause") == "harness"]
    rep_lines = []
    for x in reps:
        h = x.get("hindsight") or {}
        rep_lines.append(f"- {'PASS' if x['success'] else 'FAIL'} modes={x['modes']} blind_conf={x['blind'].get('confidence')} "
                         f"obstacles={x['blind'].get('harness_obstacles')} cause={h.get('cause')} fix={h.get('general_fix')!r}")
    prompt = PROPOSE.format(
        signals="\n".join(f"  {k}: {v}" for k, v in R.SIGNALS.items()), tools=sorted(tools),
        finish_note="This benchmark has a finish tool." if bench in FINISH else
        "This benchmark has NO finish tool (the task ends inside the environment), so reject_finish never fires here.",
        profile=json.dumps(prof), modes=json.dumps(dict(modes.most_common())),
        reports="\n".join(rep_lines) + f"\n({len(usable)} failures attributed to the harness)",
        digests="\n\n".join(digests), pool=pool_view(pool), mode_names=", ".join(MODES))
    (ws / f"propose_r{r}.txt").write_text(prompt, encoding="utf-8")
    resp = client.chat([{"role": "user", "content": prompt}], tag=f"b4:{bench}:propose", max_tokens=4000,
                       fallback_no_reasoning=True)
    raw = resp.content or ""
    (ws / f"propose_r{r}_reply.txt").write_text(raw, encoding="utf-8")
    d = extract_json(raw)
    return (d if isinstance(d, dict) else {}), raw


# ---------------------------------------------------------------- roots and evaluation
def make_root(ws: Path, name: str, mechs: list[dict]) -> Path:
    root = ws / "roots" / name
    C.new_candidate(root, C.H0_ROOT, {"mechanisms": [m["id"] for m in mechs]})
    (root / "variants" / "agent_loop" / "hooked.py").write_text(HOOKED_VARIANT, encoding="utf-8")
    spec = [{k: m[k] for k in ("id", "slot", "kind", "mechanism", "target_behavior", "precondition", "text", "max_fires")}
            for m in mechs]
    (root / "bundle.json").write_text(json.dumps({"agent_loop": {"name": "hooked", "config": {"mechanisms": spec}}},
                                                 indent=1), encoding="utf-8")
    return root


def h0_task_stats(h0_train: list[dict]) -> dict[str, float]:
    by = defaultdict(list)
    for r in h0_train:
        by[r["task_id"]].append(1.0 if r["success"] else 0.0)
    return {t: sum(v) / len(v) for t, v in by.items()}


def bootstrap_lcb(xs: list[float], rng: random.Random, n: int = 1000) -> float:
    if not xs:
        return 0.0
    means = sorted(sum(rng.choice(xs) for _ in xs) / len(xs) for _ in range(n))
    return round(means[int(0.05 * n)], 3)


def screen(bench, split, cand: dict, ws: Path, client, out: Path, cfg: dict, p_h0: dict, sig_by_task: dict,
           rng: random.Random, r: int, ledger: Path) -> dict:
    """Candidate alone on top of H0, paired with the H0 3-roll mean on targeted and safe train tasks."""
    mode = cand.get("failure_mode")
    target = [t for t, p in p_h0.items() if p < 1 and any(mode in failure_modes(s) for s in sig_by_task.get(t, [])
                                                          if not s["success"])]
    others = [t for t, p in p_h0.items() if p < 1 and t not in target]
    rng.shuffle(target), rng.shuffle(others)
    target = (target + others)[:N_TARGET]
    safe = [t for t, p in p_h0.items() if p == 1]
    rng.shuffle(safe)
    safe = safe[:N_SAFE]
    root = make_root(ws, f"r{r}_{cand['id']}", [cand])
    ok, glog = C.static_gate(root)
    if not ok:
        return {"status": "rejected", "reason": "static gate: " + glog[-200:]}
    tag = f"b4_{bench}_r{r}_{cand['id']}"
    recs = C.evaluate(bench, split, target + safe, root, client, tag, out, workers=cfg["workers"],
                      label={"method": "b4", "phase": "screen", "round": r, "cand": cand["id"]})
    dT, dS, fired, bdelta = [], [], 0, defaultdict(list)
    for rec in recs:
        s = R.trajectory_signals(rec.get("trajectory_path") or "", FINISH.get(bench))
        f = cand["id"] in s.get("mech_fired", [])
        fired += f
        d = (1.0 if rec["success"] else 0.0) - p_h0[rec["task_id"]]
        (dT if rec["task_id"] in target else dS).append(d)
        base = [x for x in sig_by_task.get(rec["task_id"], [])]
        for k in ("step_frac", "n_errors", "answer_hedged", "repeat_ratio", "tokens"):
            if base and k in s:
                bdelta[k].append(float(s[k]) - sum(float(b.get(k) or 0) for b in base) / len(base))
        C.append_jsonl(ledger, {"cand": cand["id"], "round": r, "task_id": rec["task_id"],
                                "set": "target" if rec["task_id"] in target else "safe", "fired": f,
                                "success": rec["success"], "p_h0": p_h0[rec["task_id"]], "tokens": rec.get("tokens"),
                                "error": rec.get("error"), "modes": failure_modes(s) if s else []})
    ev = {"dT": round(sum(dT) / max(1, len(dT)), 3), "dS": round(sum(dS) / max(1, len(dS)), 3),
          "lcbT": bootstrap_lcb(dT, rng), "fired": fired, "n": len(recs),
          "errors": sum(1 for x in recs if x.get("error")),
          "behavior_delta": {k: round(sum(v) / len(v), 3) for k, v in bdelta.items() if v}}
    if fired == 0:
        return {"status": "rejected", "reason": "never fired (no credit)", "evidence": ev}
    if sum(dS) < -1.0:
        return {"status": "rejected", "reason": "hurts tasks H0 always solves", "evidence": ev}
    if ev["dT"] <= 0:
        return {"status": "rejected", "reason": "no gain on targeted tasks", "evidence": ev}
    return {"status": "admitted", "evidence": ev}


def val_run(bench, split, ids, mechs, name, ws, client, out, cfg, r) -> tuple[float, int, list[dict], Path]:
    root = make_root(ws, name, mechs)
    recs = C.evaluate(bench, split, ids, root, client, f"b4_{bench}_r{r}_{name}_val", out, workers=cfg["workers"],
                      label={"method": "b4", "phase": "val", "round": r, "set": [m["id"] for m in mechs]})
    return C.score(recs), sum(x.get("tokens") or 0 for x in recs), recs, root


# ---------------------------------------------------------------- main loop
def run(bench: str, shared: dict, client, cfg: dict = C.SMOKE) -> dict:
    ws = C.RUNS / "b4" / bench
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    out = C.OUT / f"b4_{bench}.jsonl"
    ledger = ws / "ledger.jsonl"
    tasks = shared["tasks"]
    tr_split, val_split = tasks["train"][0], tasks["val"][0]
    val_ids = tasks["val"][1]
    rng = random.Random(0)
    fin = FINISH.get(bench)

    p_h0 = h0_task_stats(shared["h0_train"])
    sig_by_task: dict[str, list[dict]] = defaultdict(list)
    sig_by_path = {}
    instructions, tools = [], set()
    for rec in shared["h0_train"] + shared["h0_val"]:
        p = rec.get("trajectory_path")
        if not p or not Path(p).exists():
            continue
        s = R.trajectory_signals(p, fin)
        sig_by_path[p] = s
        if rec in shared["h0_train"]:
            sig_by_task[rec["task_id"]].append(s)
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        for e in d.get("events", []):
            if e["type"] == "task":
                instructions.append(str(e.get("instruction") or ""))
            elif e["type"] == "step":
                tools.add(e.get("tool"))
    linter = Linter(instructions, list(p_h0) + list(val_ids), {t for t in tools if t})
    prof0 = profile([sig_by_path[r["trajectory_path"]] for r in shared["h0_train"] if r.get("trajectory_path") in sig_by_path])
    (ws / "profile.json").write_text(json.dumps({"model": client.model, "harness": "h0", "profile": prof0}, indent=1))

    pool: list[dict] = []
    incumbent: list[dict] = []
    inc_val, inc_tok = C.score(shared["h0_val"]), sum(r.get("tokens") or 0 for r in shared["h0_val"])
    inc_root = C.H0_ROOT
    cur_recs, cur_sigs = list(shared["h0_train"]), dict(sig_by_path)  # evidence of the current harness
    log = {"rounds": [], "profile_h0": prof0}
    for r in range(1, cfg["rounds"] + 1):
        C.budget_check(f"b4[{bench}] round {r}")
        rd = {"round": r}
        fails = [x for x in cur_recs if not x["success"]]
        modes = Counter(m for x in fails for m in failure_modes(cur_sigs.get(x.get("trajectory_path"), {})))
        reps = reports(client, cur_recs, cur_sigs, rng, bench)
        rd["calibration"] = calibration(reps)
        rd["causes"] = dict(Counter((x.get("hindsight") or {}).get("cause") for x in reps if not x["success"]))
        dig_src = [x for x in fails if x.get("trajectory_path")]
        rng.shuffle(dig_src)
        digests = [C.summarize_trajectory(x["trajectory_path"], max_events=24, max_chars=300, task_chars=400)
                   for x in dig_src[:5]]
        prof = profile([cur_sigs[x["trajectory_path"]] for x in cur_recs if x.get("trajectory_path") in cur_sigs])
        d, raw = propose(client, bench, prof, modes, reps, digests, pool, linter.tools, r, ws)
        rd["failure_mode"] = d.get("failure_mode")
        rd["analysis"] = str(d.get("analysis", ""))[:500]
        admitted = []
        for branch in ("structural", "guidance"):
            cid = f"m{len(pool) + 1}"
            spec = d.get(branch)
            entry = {"id": cid, "round": r, "branch": branch, "failure_mode": d.get("failure_mode"), "status": "",
                     "kind": "", "precondition": "", "text": ""}
            try:
                m = R.validate_mechanism({**(spec or {}), "id": cid})
                if branch == "guidance" and m["kind"] != "guidance" or branch == "structural" and m["kind"] == "guidance":
                    raise ValueError(f"branch {branch} got kind {m['kind']}")
                entry.update(m)
                why = linter.check(m)
                if why:
                    raise ValueError("generalization gate: " + why)
            except Exception as e:
                entry.update(status="rejected", reason=str(e)[:200], kind=(spec or {}).get("kind", ""),
                             precondition=str((spec or {}).get("precondition", "")),
                             text=str((spec or {}).get("text", "")))
                pool.append(entry)
                continue
            entry.update(screen(bench, tr_split, entry, ws, client, out, cfg, p_h0, sig_by_task, rng, r, ledger))
            pool.append(entry)
            if entry["status"] == "admitted":
                admitted.append(entry)
        rd["candidates"] = [{k: c.get(k) for k in ("id", "branch", "kind", "status", "reason", "evidence")}
                            for c in pool if c["round"] == r]
        # merge (R3): incumbent + admitted, validated against the incumbent on val
        if admitted:
            trials = [admitted]
            if len(admitted) == 2:
                trials.append([max(admitted, key=lambda c: c["evidence"]["dT"])])
            for tset in trials:
                mechs = incumbent + tset
                v, tok, vrecs, root = val_run(bench, val_split, val_ids, mechs, f"r{r}_set{len(mechs)}_"
                                              + "_".join(c["id"] for c in tset), ws, client, out, cfg, r)
                rd.setdefault("val_trials", []).append({"set": [c["id"] for c in mechs], "val": v, "tokens": tok})
                if C.better(v, tok, inc_val, inc_tok):
                    incumbent, inc_val, inc_tok, inc_root = mechs, v, tok, root
                    for c in tset:
                        c["status"] = "in_set"
                    rd["result"] = f"new set {[c['id'] for c in mechs]} val={v:.3f}"
                    break
                for c in tset:
                    c.setdefault("conflicts", []).append([x["id"] for x in mechs if x is not c])
            else:
                rd["result"] = f"kept set (val {inc_val:.3f})"
        else:
            rd["result"] = "no candidate admitted"
        rd["val"] = inc_val
        # evidence of the current harness for the next round: its screening/val episodes + H0 train where unchanged
        if incumbent:
            new = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]
            cur = [x for x in new if x.get("root") == str(inc_root)]
            for x in cur:
                if x.get("trajectory_path"):
                    cur_sigs[x["trajectory_path"]] = R.trajectory_signals(x["trajectory_path"], fin)
            cur_recs = cur + [x for x in shared["h0_train"] if x["task_id"] not in {c["task_id"] for c in cur}]
        log["rounds"].append(rd)
        (ws / "pool.json").write_text(json.dumps(pool, indent=1, default=str))
        (ws / "log.json").write_text(json.dumps(log, indent=1, default=str))
        print(f"  [b4 {bench}] round {r}: mode={rd['failure_mode']} "
              f"cands={[(c['id'], c['status'], (c.get('evidence') or {}).get('dT')) for c in pool if c['round'] == r]} "
              f"-> {rd['result']}", flush=True)
    # ---- freeze and test
    log["final"] = {"root": str(inc_root), "set": [c["id"] for c in incumbent], "val": inc_val}
    (ws / "final.json").write_text(json.dumps({"final_root": str(inc_root), "set": incumbent, "val": inc_val},
                                              indent=1, default=str))
    C.budget_check(f"b4[{bench}] test")
    test = C.evaluate(bench, tasks["test"][0], tasks["test"][1], inc_root, client, f"b4_{bench}_test", out,
                      workers=cfg["workers"], label={"method": "b4", "phase": "test"})
    fired = Counter(m for x in test for m in R.trajectory_signals(x.get("trajectory_path") or "", fin).get("mech_fired", []))
    log["test"] = {"success": C.score(test), "n": len(test), "fired": dict(fired)}
    (ws / "log.json").write_text(json.dumps(log, indent=1, default=str))
    return {"log": log, "test": test}
