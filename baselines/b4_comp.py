"""B4 v7: the optimisation loop proposes edits of harness COMPONENTS (code), each tied to a behaviour hypothesis that
is tested before the outcome is.

Earlier versions (v3-v6) let the proposer add gated reminders to a fixed loop. Here step 3 of the loop is replaced:
the proposer edits a component (how tool results are presented, which tools/descriptions are offered, how calls are
parsed or repaired, how the context is built, what is checked before an answer is accepted, the control loop), as a
new variant file of one slot. Nothing is added to the system prompt.

Every candidate is a falsifiable claim in two parts:
    (a) the edit makes the agent behave differently in a stated, measurable way   (behaviour metric, direction)
    (b) behaving that way raises the success rate
and the loop tests them in order of cost:
    0. hypotheses only (text).  Free check on the saved runs: across the repeated runs of the same task, do the
       successful ones show more of the behaviour?  Only the best-supported hypotheses get code.
    1. code + gates (static gate, generalisation lint, dry replay: the edit must change at least one saved run).
    2. behaviour probe: a few branches of saved runs forked where the edited harness first differs (b4_diff).
       The metric is compared on branch vs saved run. No shift -> the IMPLEMENTATION is ineffective (one revision).
    3. outcome screen: more branches, paired with the saved outcomes. Shift without gain -> the HYPOTHESIS is
       refuted; it is not proposed again.
    4. confirmation on held-out tasks (branches of the val runs), merge, and the saved runs are advanced.
The experiment ledger keeps one row per candidate (behaviour changed? outcome changed?) and is given to the proposer
in later rounds: it accumulates which behaviours are worth causing for this agent model and which are not.

Env: B4_N_HYP (5), B4_N_CAND (3), B4_N_PROBE (16), B4_N_SCREEN (64), B4_K_VAL (3), B4_K_TEST (2), plus B4_TAG,
B4_SEED, B4_RESUME, B4_ALPHA of the earlier versions.
"""
from __future__ import annotations

import ast
import json
import os
import random
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path

from baselines import b4_branch as V
from baselines import b4_diff as D
from baselines import b4_modes as G
from baselines import b4_repertoire as B
from baselines import common as C
from baselines.hg import runtime as R
from baselines.proposer_io import apply_files, extract_json, gate_hint, reply_files

N_HYP = int(os.environ.get("B4_N_HYP", "5"))        # hypotheses asked per round (text only)
N_CAND = int(os.environ.get("B4_N_CAND", "3"))      # hypotheses that get code per round
N_PROBE = int(os.environ.get("B4_N_PROBE", "16"))   # branches of the behaviour probe
N_SCREEN = int(os.environ.get("B4_N_SCREEN", "64"))  # branches of the outcome screen, probe included
K_VAL = int(os.environ.get("B4_K_VAL", "3"))        # branches per touched val run
K_TEST = int(os.environ.get("B4_K_TEST", "2"))      # branches per touched test run
N_REVIEW = int(os.environ.get("B4_N_REVIEW", "3"))  # independent adoption reviews per tested candidate
OBS_MARGIN = 2                                      # tasks (agree - disagree) for saved runs to move a hypothesis
SHIFT_MARGIN, SHIFT_ALPHA = 3, 0.1                  # behaviour shift: net pairs in the stated direction, sign test
MAX_LITERAL = 400                                   # longest string constant in a component (no prompt edits)
SLOTS = ("tool_policy", "context_mgmt", "verifier", "agent_loop")  # memory (cross-episode) cannot be forked

# ---------------------------------------------------------------- behaviour metrics
FEATURES = {
    "steps": "environment steps taken (tool calls executed, the final answer included)",
    "step_frac": "steps / step budget (0..1)",
    "llm_calls": "model calls made",
    "n_actions": "tool calls other than the final answer",
    "distinct_actions": "different (tool, arguments) pairs among them",
    "distinct_tools": "different tools used",
    "repeat_ratio": "share of tool calls that repeat an earlier identical call",
    "n_errors": "short tool results (an error message, not content) that look like an error",
    "obs_chars": "characters of all tool results returned by the environment",
    "answered": "1 if the run ended with a final answer, else 0",
    "answer_len": "characters of the final answer",
    "answer_hedged": "1 if the final answer says it is unknown / could not be determined",
    "finish_rejects": "final answers refused by the harness before one was accepted",
    "tokens": "tokens used by the run",
}
_OK = (ast.Expression, ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.UnaryOp, ast.USub, ast.Not, ast.BoolOp,
       ast.And, ast.Or, ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.IfExp, ast.Name,
       ast.Load, ast.Constant, ast.Call)


def compile_metric(expr: str):
    """Whitelisted numeric expression over FEATURES and n('<tool>') -> code object. Raises ValueError."""
    if not isinstance(expr, str) or not expr.strip() or len(expr) > 200:
        raise ValueError("behaviour must be a non-empty expression of <= 200 chars")
    tree = ast.parse(expr.strip(), mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, _OK):
            raise ValueError(f"disallowed syntax: {type(node).__name__}")
        if isinstance(node, ast.Name) and node.id not in FEATURES and node.id not in ("n", "min", "max", "abs"):
            raise ValueError(f"unknown feature {node.id!r}")
        if isinstance(node, ast.Call) and not (isinstance(node.func, ast.Name) and node.func.id in ("n", "min", "max", "abs")):
            raise ValueError("only n(), min(), max(), abs() may be called")
    return compile(tree, "<metric>", "eval")


ERR_MAX_CHARS = 400   # an error message is short; a long result that merely mentions "error" is content
_ERR = re.compile(r"\b(error|exception|traceback|failed|failure|invalid|not found|denied|unauthori[sz]ed|forbidden|"
                  r"does not exist|no such|not allowed|missing required|unexpected)\b", re.I)


def _is_error(obs) -> bool:
    o = str(obs or "").strip()
    return len(o) <= ERR_MAX_CHARS and bool(_ERR.search(o))


def features(path: str, fin: str | None) -> dict:
    """End-of-run behaviour features of a saved trajectory."""
    s = R.trajectory_signals(path, fin)
    ev = V.load_events(path)
    steps = [e for e in ev if e.get("type") == "step"]
    acts = [e for e in steps if not (fin and e.get("tool") == fin)]
    keys = [(e.get("tool"), json.dumps(e.get("args"), sort_keys=True, default=str)) for e in acts]
    task = next((e for e in ev if e.get("type") == "task"), {})
    return {"steps": len(steps), "step_frac": len(steps) / max(1, int(task.get("max_steps") or 30)),
            "llm_calls": sum(1 for e in ev if e.get("type") == "llm"), "n_actions": len(acts),
            "distinct_actions": len(set(keys)), "distinct_tools": len({k[0] for k in keys}),
            "repeat_ratio": float(s.get("repeat_ratio") or 0), "n_errors": float(sum(_is_error(e.get("observation")) for e in acts)),
            "obs_chars": sum(len(str(e.get("observation") or "")) for e in acts),
            "answered": float(bool(s.get("answered"))), "answer_len": float(s.get("answer_len") or 0),
            "answer_hedged": float(bool(s.get("answer_hedged"))),
            "finish_rejects": sum(1 for e in ev if e.get("type") == "verifier_reject"),
            "tokens": float(s.get("tokens") or 0), "_tools": dict(Counter(k[0] for k in keys))}


def metric(code, f: dict) -> float | None:
    env = {k: v for k, v in f.items() if k in FEATURES}
    tc = f.get("_tools") or {}
    env.update(n=lambda t: tc.get(t, 0), min=min, max=max, abs=abs)
    try:
        return float(eval(code, {"__builtins__": {}}, env))  # noqa: S307 - whitelisted AST, no builtins
    except Exception:
        return None


def observe(code, direction: str, recs: list[dict], feats: dict) -> dict:
    """Free check of part (b) of a hypothesis on saved runs. Tasks have several runs of the same harness: among the
    tasks with both outcomes, is the metric higher (direction 'up') in the successful runs? Task difficulty is held
    fixed, which a plain success-vs-failure comparison does not do. Correlational: it ranks, it does not decide."""
    sgn = 1 if direction == "up" else -1
    by = defaultdict(lambda: ([], []))
    ok, bad = [], []
    for x in recs:
        v = metric(code, feats[x["trajectory_path"]])
        if v is None:
            continue
        (ok if x["success"] else bad).append(v)
        by[x["task_id"]][0 if x["success"] else 1].append(v)
    agree = disagree = 0
    for a, b in by.values():
        if a and b:
            d = sgn * (sum(a) / len(a) - sum(b) / len(b))
            agree += d > 1e-9
            disagree += d < -1e-9
    mean = lambda xs: round(sum(xs) / len(xs), 3) if xs else None  # noqa: E731
    return {"mean_success": mean(ok), "mean_fail": mean(bad), "mixed_tasks": sum(1 for a, b in by.values() if a and b),
            "agree": agree, "disagree": disagree,
            "score": round((agree - disagree) / max(1, agree + disagree), 3) if agree + disagree else 0.0}


def behaviour_shift(code, direction: str, recs: list[dict], feats) -> dict:
    """Part (a): the metric on each branch against the saved run it forks. Under no effect both are samples of the
    same continuation, so the sign test applies."""
    sgn = 1 if direction == "up" else -1
    up = down = 0
    old, new = [], []
    for x in recs:
        if not x.get("branched") or x.get("error") or not x.get("trajectory_path"):
            continue
        a, b = metric(code, feats(x["fork_of"])), metric(code, feats(x["trajectory_path"]))
        if a is None or b is None:
            continue
        old.append(a)
        new.append(b)
        up += sgn * (b - a) > 1e-9
        down += sgn * (b - a) < -1e-9
    p = V.sign_p(up, down)
    return {"n": len(old), "before": round(sum(old) / len(old), 3) if old else None,
            "after": round(sum(new) / len(new), 3) if new else None, "as_predicted": up, "opposite": down,
            "p": round(p, 4), "shifted": bool(up - down >= SHIFT_MARGIN and p <= SHIFT_ALPHA)}


def effects(recs: list[dict], feats) -> dict:
    """Every feature (not only the predicted one) on each branch against the saved run it forks: what else the edit
    changed (cost, length of runs, kind of answers). Two-sided sign test per feature."""
    pairs = [(feats(x["fork_of"]), feats(x["trajectory_path"])) for x in recs
             if x.get("branched") and not x.get("error") and x.get("trajectory_path")]
    out = {}
    for k in FEATURES if pairs else ():
        up = sum(1 for a, b in pairs if b[k] - a[k] > 1e-9)
        down = sum(1 for a, b in pairs if a[k] - b[k] > 1e-9)
        out[k] = {"before": round(sum(a[k] for a, _ in pairs) / len(pairs), 3),
                  "after": round(sum(b[k] for _, b in pairs) / len(pairs), 3), "up": up, "down": down, "n": len(pairs),
                  "clear": bool(abs(up - down) >= SHIFT_MARGIN and min(V.sign_p(up, down), V.sign_p(down, up)) <= SHIFT_ALPHA)}
    return out


def effects_view(eff: dict, only_clear: bool = True) -> str:
    rows = [f"{k}: {e['before']} -> {e['after']} (higher in {e['up']}, lower in {e['down']} of {e['n']} branches)"
            for k, e in (eff or {}).items() if e.get("clear") or not only_clear]
    return "; ".join(rows) or "(no feature changed clearly)"


REVIEW = """You decide whether a tested edit of the scaffolding ("harness") around an AI agent is adopted into the
harness. The agent model is fixed. The measurements below are facts; the decision is a judgement of value.

## The edit ({slot})
hypothesis: {hypothesis}
mechanism: {mechanism}

## Measured on training tasks
Each branch replays a saved run of the current harness under the edited harness up to the first point where the
edit changes something, and continues live from there; it is compared with the saved run it forks (same task).
- share of saved runs the edit changes: {coverage}
- predicted behaviour `{behaviour}` ({direction}): {before} -> {after} ({as_predicted} branches as predicted,
  {opposite} against, of {n_shift})
- success: of {n} branches, {same} ended like the saved run they fork, {W} succeeded where the saved run failed,
  {L} failed where it succeeded: net change {net:+d} (one-sided sign test of a gain: p = {p}). Two runs of the SAME
  harness on a task also differ now and then, so a few wins and losses in equal number are what "no change" looks like.
- reading of the hypothesis: {verdict}
- every feature that changed clearly (mean before -> after): {effects}
Features: {features}

## What the measurements allow (checked by the pipeline, not for you to re-judge)
- adoption for more successes: {can_success}
- adoption for another benefit (e.g. lower cost at equal success): {can_other}

## The current harness
{state}

## Decision
Your part is the judgement of value: is the harness better with this edit than without it? Better can be: more
successes; or the same successes at a clearly lower cost (tokens, steps); or another measured benefit you can name.
A higher cost is acceptable when it buys successes. A large measured benefit outweighs small side effects; an edit
whose only effects are neutral or unwanted is rejected (every component adds complexity).
Whatever you rely on is measured again on held-out tasks before the edit is merged; for a benefit other than
success, `claim` is the measured effect you rely on (it must appear again there, with no loss of success).
{revise}
Answer ONLY with JSON:
{{"decision": "{choices}", "benefit": "success|efficiency|other",
 "claim": {{"behaviour": "<numeric expression over the features>", "direction": "up|down"}},
 "revision": "<only for revise: what the mechanism must do differently, as precondition -> action>",
 "reason": "<2-3 sentences>"}}"""

REVISE = """If the edit has a real measured benefit together with a side effect that moved the wrong way, you may instead
ask for ONE revision of the code that keeps the benefit and removes the side effect (decision "revise"); the revised
edit is measured again from scratch.
"""


def review(client, bench: str, row: dict, state: str, can_revise: bool = False) -> dict:
    """The adoption decision is a judgement of value (is this trade worth it), made by the LLM from the measured
    effects; `apply_review` and the held-out check keep it inside what the measurements support."""
    sh, t = row.get("shift") or {}, row.get("outcome") or {}
    d = B._ask_json(client, REVIEW.format(
        slot=row["slot"], hypothesis=row["hypothesis"], mechanism=row["mechanism"], coverage=row.get("coverage"),
        behaviour=row["behaviour"], direction=row["direction"], before=sh.get("before"), after=sh.get("after"),
        as_predicted=sh.get("as_predicted"), opposite=sh.get("opposite"), n_shift=sh.get("n"), W=t.get("W"),
        L=t.get("L"), n=t.get("n"), p=t.get("p"), same=t.get("n", 0) - t.get("W", 0) - t.get("L", 0),
        net=t.get("W", 0) - t.get("L", 0), revise=REVISE if can_revise else "",
        can_success=("possible: the gain is statistically reliable" + (
            f" ({t.get('Wt', 0)} of the wins came where the saved run had already given its final answer and the "
            "edit alone changed the ending: such a win is caused by the edit, it is not run-to-run variation, so "
            "the sign test above understates the evidence)" if t.get("Wt", 0) - t.get("Lt", 0) >= V.MARGIN else ""))
        if V.reliable(t) else
        "not possible: the gain is not statistically reliable",
        can_other="possible: no net loss of success was measured" if t.get("W", 0) - t.get("L", 0) >= 0 else
        "not possible: more losses than wins",
        choices="adopt|reject|revise" if can_revise else "adopt|reject", verdict=row["verdict"], effects=effects_view(row.get("effects")),
        features="; ".join(f"{k} = {v}" for k, v in FEATURES.items()), state=state), f"b4:{bench}:review")
    dec = str(d.get("decision") or "").strip().lower()
    rv = {"decision": dec if dec == "adopt" or (dec == "revise" and can_revise and d.get("revision")) else "reject",
          "benefit": str(d.get("benefit") or "").strip().lower()[:20] or "other",
          "reason": str(d.get("reason") or d.get("_error") or "no usable answer")[:400]}
    if rv["decision"] == "revise":
        rv["revision"] = str(d["revision"])[:600]
    c = d.get("claim") if isinstance(d.get("claim"), dict) else {}
    beh, direction = str(c.get("behaviour") or "").strip(), str(c.get("direction") or "").strip().lower()
    try:
        compile_metric(beh)
        if direction in ("up", "down"):
            rv["claim"] = {"behaviour": beh, "direction": direction}
    except Exception:
        pass
    return rv


def review_vote(client, bench: str, row: dict, state: str, can_revise: bool = False) -> dict:
    """Single answers to the same evidence differ: N_REVIEW independent reviews, the most frequent decision wins
    (a tie goes to the more cautious one)."""
    rvs = [review(client, bench, row, state, can_revise) for _ in range(N_REVIEW)]
    n = Counter(x["decision"] for x in rvs)
    dec = min(n, key=lambda d: (-n[d], ("reject", "revise", "adopt").index(d)))
    pick = [x for x in rvs if x["decision"] == dec]
    best = Counter(x["benefit"] for x in pick).most_common(1)[0][0]
    rv = next(x for x in pick if x["benefit"] == best and (best == "success" or "claim" in x or dec != "adopt"))\
        if any(x["benefit"] == best and (best == "success" or "claim" in x or dec != "adopt") for x in pick) else pick[0]
    return {**rv, "votes": dict(n)}


def apply_review(row: dict, rv: dict, feats) -> dict:
    """Guard rails around the review. The LLM chooses; it cannot adopt on grounds the training branches do not
    show: 'success' needs reliable wins, any other benefit needs no net loss and its claimed effect measured."""
    t = row["outcome"]
    row["review"] = rv
    if rv["decision"] == "revise":
        row.update(status="revise", decision=f"REVISION ASKED (review): {rv['revision']}")
    elif rv["decision"] != "adopt":
        row.update(status="rejected", decision=f"NOT ADOPTED (review): {rv['reason']}")
    elif rv["benefit"] == "success":
        ok = V.reliable(t)
        row.update(status="admitted" if ok else "rejected", basis="success",
                   decision="" if ok else "NOT ADOPTED: the review relied on a success gain that is not reliable")
    else:
        c = rv.get("claim")
        sh = behaviour_shift(compile_metric(c["behaviour"]), c["direction"], row["_recs"], feats) if c else None
        ok = bool(sh and sh["shifted"] and t["W"] - t["L"] >= 0)
        row.update(status="admitted" if ok else "rejected", basis=rv["benefit"], claim_shift=sh,
                   decision="" if ok else "NOT ADOPTED: the benefit the review relied on is not in the measurements")
    return row


# ---------------------------------------------------------------- generalisation lint for component code
IMPORTS = {"__future__", "json", "re", "math", "collections", "itertools", "functools", "dataclasses", "typing",
           "hashlib", "difflib", "string", "statistics", "copy", "textwrap", "heapq", "h0.protocols",
           "benchmarks.common"}
BANNED_NAMES = {"open", "eval", "exec", "compile", "__import__", "globals", "locals", "input", "breakpoint"}
BANNED_ATTRS = {"evaluate"}  # the environment's grader


def str_consts(src: str) -> set:
    try:
        return {n.value for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    except SyntaxError:
        return set()


def lint_code(src: str, linter: B.Linter, bench_names, known: set = frozenset()) -> str | None:
    """Tier 1 of the generalisation gate (CLAUDE.md, docs/idea_v2.md 3.1), for code: nothing of the tasks or of the
    benchmark may be written into a component; tools are reached through the task's own schemas."""
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return f"syntax error: {e}"
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body \
                and isinstance(node.body[0], ast.Expr) and isinstance(getattr(node.body[0], "value", None), ast.Constant):
            docs.add(id(node.body[0].value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name not in IMPORTS:
                    return f"import of {a.name!r} is not allowed (allowed: {sorted(IMPORTS)})"
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "") not in IMPORTS:
                return f"import from {node.module!r} is not allowed (allowed: {sorted(IMPORTS)})"
        elif isinstance(node, ast.Name) and node.id in BANNED_NAMES:
            return f"use of {node.id}() is not allowed"
        elif isinstance(node, ast.Attribute) and node.attr in BANNED_ATTRS:
            return f"access to .{node.attr} is not allowed"
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
            s = node.value
            if s in linter.tools and s not in known:  # `known`: constants of the code it started from
                return (f"hardcoded tool name {s!r}: a component must work for any tool set, find tools through "
                        "task.tools (their schemas) and task.finish_tool")
            if len(s) > MAX_LITERAL:
                return (f"a string constant of {len(s)} chars: long instruction text is a prompt edit, not a "
                        "component edit")
            if re.search(r"\d{4,}", s):
                return "a string constant contains a long number (task-specific literal)"
    low = src.lower()
    for b in bench_names:
        if b.lower() in low:
            return f"names the benchmark ({b})"
    for t in linter.ids:
        if re.search(r"(?<![\w])%s(?![\w])" % re.escape(t.lower()), low) and not t.isdigit():
            return "contains a task id"
    w = re.findall(r"\w+", low)
    for i in range(len(w) - 5):
        if " ".join(w[i:i + 6]) in linter.shingles:
            return f"copies task text: '{' '.join(w[i:i + 6])}'"
    return None


# ---------------------------------------------------------------- proposer
EDIT_TYPES = """- tool results: how an environment result becomes the text the model reads (which parts are kept when it is too
  long, ordering, de-duplication against earlier results, marking what was cut and how to get it)
- tool calls: repairing or normalising the model's call before it is executed (malformed arguments, an exact repeat
  of an earlier call, a call that cannot succeed)
- tool set: which tools are offered at a step and how their descriptions/parameters are worded
- context: what of the history is sent at each step (compaction of old results, a running digest of what was
  found, keeping the task and key evidence visible)
- working notes: structured state the harness keeps during one run and shows to the model (items seen, calls
  tried, candidate answers)
- acceptance: what is checked before a final answer is accepted, and what the agent is told when it is not
- control: the loop itself (step budget use, what happens after an error or a refused answer, when to stop,
  an extra model call that checks or compares candidate answers before finishing)"""

HYP = """You improve the scaffolding ("harness") around an AI agent by editing its COMPONENTS (Python code). The
agent model is fixed. You do not write advice for the model: adding instructions or reminders to prompts is not
allowed. An edit must change what information reaches the model or what the harness does with the model's output.

## Editable components (slots)
- tool_policy: tools(task) -> tool schemas offered; parse(resp, task) -> actions; format_observation(action, result,
  task) -> the text of a tool result
- context_mgmt: build(system, task, history, memory_notes) -> the messages sent to the model at each step
- verifier: check(task, action, state, env_done) -> accept or refuse (with feedback) a final answer
- agent_loop: run(task, env, h, llm, rec) -> the whole think/act/observe loop
Kinds of edit you may consider:
{edit_types}

## Current harness (complete source)
{tree}

## Evidence from {n_runs} saved runs of the current harness on training tasks (success rate {succ})
Behaviour features, mean over successful runs vs failed runs:
{feat_table}
How the runs look (a precondition that these numbers rule out will never hold):
{facts}
Failure modes (from run reviews): {modes}
Reviews of single runs:
{reports}
Digests of failed runs:
{digests}

## Experiment ledger (earlier candidates of this search; "behaviour" = did the agent act differently, "outcome" =
paired wins/losses of branches against the saved runs)
{ledger}
Read the ledger as experimental results. A behaviour marked REFUTED was caused successfully and did not raise
success: do not target it again ("adoption" says whether the edit was kept anyway, e.g. for its lower cost). INEFFECTIVE means the code did not cause the behaviour: the idea is still open, by another route.

## Task
Propose {n} DIFFERENT candidate edits, in at least two different slots. Each is a hypothesis in two parts:
(a) the edit makes the agent behave differently in a measurable way, (b) that behaviour raises the success rate
(or keeps it while making runs clearly cheaper: a reviewer weighs every measured effect before an edit is adopted).
`behaviour` is ONE numeric expression computed on ONE run from these end-of-run features (and n('<tool name>') =
calls of that tool; tool names seen: {tools}); `direction` says which way the edit moves it. Only feature names,
numbers, + - * / ( ), min, max, abs: for example `n_actions - distinct_actions` or `obs_chars / max(1, n_actions)`.
No mean(...), no second metric, no words.
{features}
Rules:
- General principle only, of the form "precondition observable during a run -> action of the harness". Nothing
  specific to a task: no entities, answers, task text; no tool names inside the component (tools are found through
  their schemas at run time).
- The edit must act on real runs: say on which share of runs its precondition should hold.
- One slot per candidate; the edit wraps or replaces the current variant of that slot.

Answer ONLY with JSON:
{{"analysis": "<3-5 sentences: what limits this agent, from the evidence and the ledger>",
 "candidates": [{{"name": "<snake_case, <= 24 chars>", "slot": "tool_policy|context_mgmt|verifier|agent_loop",
   "edit_type": "<one of the kinds above>", "failure_mode": "<the failure mode it targets>",
   "hypothesis": "<If the agent ... then it succeeds more often, because ...>",
   "behaviour": "<expression>", "direction": "up|down",
   "mechanism": "<precondition -> action, 2-4 sentences: exactly what the component does>"}}, ...]}}"""

IMPL = """You implement ONE edit of a harness component as a new variant file. The agent model is fixed.

## The edit
slot: {slot}
hypothesis: {hypothesis}
expected behaviour change: `{behaviour}` goes {direction}
mechanism: {mechanism}

## Interfaces (h0/protocols.py and benchmarks/common.py)
{protocols}

class TaskSpec: task_id, benchmark, instruction, initial_observation, tools, guidance, finish_tool (name of the
    tool that submits the final answer), max_steps, meta
    task.tools is a list of OpenAI function schemas, each exactly
    {{"type": "function", "function": {{"name": ..., "description": ..., "parameters": {{...}}}}}}:
    a tool's name is t["function"]["name"] (t.get("name") is always None).
class StepResult: observation (str), done (bool), info (dict)
{shapes}
## Current code (the slot you edit, the loop that calls it, and every edit already adopted in another slot: they
## are active on every run, so your mechanism must work together with them)
{code}

## Requirements
- Write the complete file `variants/{slot}/{vname}.py`. It must define `register(reg)` that calls
  `reg.register("{slot}", "{vname}", lambda c: <YourClass>(...), "<one-line description>")`.
- The slot currently runs variant "{base}" with config {base_cfg}. Keep its behaviour except for your edit: either
  wrap it (`reg.instantiate("{slot}", "{base}", {base_cfg})` inside the factory, then delegate) or copy its code
  into your file and change it. The file is loaded on its own: it cannot import another variant file, `variants`,
  `h0` or any project module (no `from variants...`, no relative imports). Whatever you need from the current code,
  get it through `reg.instantiate` or copy it.
- All parameters have defaults (the factory is called with an empty config).
- Imports allowed: {imports}. No file, network or environment access.
- General: no tool names, task text, entities or benchmark names in the file. Find tools through `task.tools`
  (`t["function"]["name"]`, `["description"]`, `["parameters"]`) and `task.finish_tool`.
- No prompt edits: do not add standing advice to the system prompt or to every message. Text shown to the model
  must be produced by the mechanism from the state of the run (e.g. what was cut, what was refused and why), and
  no string constant may exceed {max_literal} characters.
- The mechanism must act on real runs. A component whose condition never holds is rejected.
- Model calls from agent_loop other than the main one must use `tag=f"h:{{task.benchmark}}:check"`.
- Keep per-run state on the instance keyed by task.task_id, or in `state.notes` (a fresh harness object is built
  for every run).
{feedback}
Output exactly one file as text in your answer, nothing else (you do not need any tool: the pipeline saves the
block below itself):
### FILE: variants/{slot}/{vname}.py
```python
<complete file>
```"""


def feat_table(recs: list[dict], feats: dict) -> str:
    rows = []
    for k in FEATURES:
        a = [feats[x["trajectory_path"]][k] for x in recs if x["success"]]
        b = [feats[x["trajectory_path"]][k] for x in recs if not x["success"]]
        rows.append(f"  {k:17s} success={sum(a) / max(1, len(a)):9.2f}  failed={sum(b) / max(1, len(b)):9.2f}")
    return "\n".join(rows)


def _shape(v, depth: int = 0) -> str:
    """Structure of a value without its content: keys, types, sizes."""
    if isinstance(v, dict):
        if depth >= 3:
            return "{...}"
        return "{" + ", ".join(f"{json.dumps(str(k))}: {_shape(x, depth + 1)}" for k, x in list(v.items())[:12]) + "}"
    if isinstance(v, list):
        return f"[{len(v)} x {_shape(v[0], depth + 1)}]" if v else "[]"
    if isinstance(v, str):
        return f"str({len(v)} chars)"
    return type(v).__name__


def obs_shapes(recs: list[dict], per_kind: int = 1, scan: int = 12) -> str:
    """What tool results look like on saved runs, as structure only (field names, types, sizes; no content): the
    implementer must not guess field names. Results are grouped by the argument names of the call, not tool names."""
    seen: dict = {}
    for x in recs[:scan]:
        try:
            ev = V.load_events(x["trajectory_path"])
        except Exception:
            continue
        for e in ev:
            if e.get("type") != "step" or e.get("observation") is None:
                continue
            kind = ", ".join(sorted((e.get("args") or {}).keys())) if isinstance(e.get("args"), dict) else ""
            if len(seen.setdefault(kind, [])) >= per_kind:
                continue
            obs = str(e["observation"])
            try:
                shape = "JSON text: " + _shape(json.loads(obs))
            except (TypeError, ValueError):
                shape = "plain text: " + _shape(obs)
            if shape not in seen[kind]:
                seen[kind].append(shape)
    return "\n".join(f"- result of a call with arguments ({k or 'none'}): {s_[:900]}"
                     for k, v in seen.items() for s_ in v)


def run_facts(recs: list[dict], feats: dict, budget=None) -> str:
    """Distributions the proposer needs to choose a precondition that actually holds on runs of this harness."""
    def q(xs):
        xs = sorted(xs)
        return "no data" if not xs else f"10% <= {xs[len(xs) // 10]:.0f}, median {xs[len(xs) // 2]:.0f}, 90% <= {xs[(9 * len(xs)) // 10]:.0f}, max {xs[-1]:.0f}"
    fs = [feats[x["trajectory_path"]] for x in recs]
    per = [f["obs_chars"] / f["n_actions"] for f in fs if f["n_actions"]]
    return (f"  steps per run: {q([f['steps'] for f in fs])}" + (f" (step budget {budget})" if budget else "") + "\n"
            f"  characters per tool result (run average): {q(per)}\n"
            f"  repeated identical calls: in {sum(1 for f in fs if f['repeat_ratio'] > 0)} of {len(fs)} runs; "
            f"error-like results: in {sum(1 for f in fs if f['n_errors'] > 0)}; runs ending without a final answer: "
            f"{sum(1 for f in fs if not f['answered'])}; final answers saying 'unknown': "
            f"{sum(1 for f in fs if f['answer_hedged'])}\n" + _endings(fs))


def _endings(fs: list[dict]) -> str:
    """Why runs end without a final answer: a precondition on 'the last step' is dead code when they stop earlier."""
    un = [f for f in fs if not f["answered"]]
    if not un:
        return "  every run ended with a final answer"
    full = sum(1 for f in un if f["step_frac"] >= 0.95)
    idle = [f["llm_calls"] - f["steps"] for f in un]
    by_tools = Counter(f["distinct_tools"] for f in un)
    return (f"  of the {len(un)} runs without a final answer: {full} used the whole step budget, {len(un) - full} "
            f"stopped before it (the loop gives up after consecutive model replies that call no tool); model replies "
            f"without an executed tool call in these runs: median {sorted(idle)[len(idle) // 2]}; different tools "
            f"they used: " + ", ".join(f"{k} tool(s) in {v} runs" for k, v in sorted(by_tools.items()))
            + f" (runs WITH a final answer: "
            + ", ".join(f"{k} in {v}" for k, v in sorted(Counter(f['distinct_tools'] for f in fs if f['answered']).items()))
            + ")")


def reports_view(reps: list[dict]) -> str:
    out = []
    for x in reps:
        h, b = x.get("hindsight") or {}, x.get("blind") or {}
        if h.get("cause"):
            out.append(f"- failed run, cause={h.get('cause')}: {str(h.get('why') or '')[:200]} "
                       f"| fix: {str(h.get('general_fix') or '')[:200]}")
        for o in (b.get("harness_obstacles") or [])[:2] if isinstance(b, dict) and not x.get("label_only") else []:
            out.append(f"- obstacle noted ({'passed' if x['success'] else 'failed'} run): {str(o)[:200]}")
    return "\n".join(out[:30]) or "(none)"


def ledger_view(ledger: list[dict]) -> str:
    if not ledger:
        return "(empty: first round)"
    rows = []
    for e in ledger:
        sh, t, o = e.get("shift") or {}, e.get("outcome") or {}, e.get("observational") or {}
        rows.append(
            f"- [round {e['round']}] {e['slot']}/{e['name']}: {e['hypothesis'][:220]}\n"
            f"    mechanism: {e['mechanism'][:260]}\n"
            f"    metric `{e['behaviour']}` ({e['direction']}); saved runs: {o.get('agree', 0)} tasks agree / "
            f"{o.get('disagree', 0)} disagree; runs touched: {e.get('coverage', '?')}\n"
            f"    behaviour: {sh.get('before')} -> {sh.get('after')} ({sh.get('as_predicted', 0)} as predicted / "
            f"{sh.get('opposite', 0)} opposite of {sh.get('n', 0)}); outcome: {t.get('W', 0)} wins / {t.get('L', 0)} "
            f"losses of {t.get('n', 0)} branches\n    verdict on the hypothesis: {e['verdict']}"
            + (f"\n    other clear effects: {effects_view(e['effects'])}" if e.get("effects") else "")
            + (f"\n    adoption: {e['decision']}" if e.get("decision") else ""))
    return "\n".join(rows)


def propose(client, bench: str, ctx: dict, ledger: list[dict], r: int, ws: Path, feedback: str = "") -> dict:
    prompt = HYP.format(edit_types=EDIT_TYPES, tree=ctx["tree"], n_runs=ctx["n_runs"], succ=ctx["succ"],
                        feat_table=ctx["feat_table"], facts=ctx["facts"], modes=ctx["modes"], reports=ctx["reports"],
                        digests="\n\n".join(ctx["digests"]), ledger=ledger_view(ledger), n=N_HYP,
                        tools=sorted(ctx["tools"]),
                        features="\n".join(f"  {k}: {v}" for k, v in FEATURES.items()))
    if feedback:
        prompt += "\n\nYour previous answer could not be used:\n" + feedback + "\nAnswer again, complete."
    (ws / f"r{r}_hyp_prompt{'_retry' if feedback else ''}.txt").write_text(prompt, encoding="utf-8")
    d = {}
    for attempt in range(2):
        resp = client.chat([{"role": "user", "content": prompt}], tag=f"b4:{bench}:hyp", max_tokens=6000,
                           fallback_no_reasoning=True)
        (ws / f"r{r}_hyp_reply{'_retry' if feedback else ''}_{attempt}.txt").write_text(resp.content or "", encoding="utf-8")
        d = extract_json(resp.content or "", key="candidates")
        if isinstance(d, dict) and isinstance(d.get("candidates"), list) and d["candidates"]:
            return d
    return d if isinstance(d, dict) else {}


def validate_hyp(h: dict, ledger: list[dict]) -> dict:
    if not isinstance(h, dict):
        raise ValueError("not an object")
    slot = str(h.get("slot") or "").strip()
    if slot not in SLOTS:
        raise ValueError(f"slot must be one of {SLOTS}")
    name = re.sub(r"[^a-z0-9_]", "_", str(h.get("name") or "").strip().lower())[:24].strip("_") or "edit"
    direction = str(h.get("direction") or "").strip().lower()
    if direction not in ("up", "down"):
        raise ValueError("direction must be up or down")
    beh = str(h.get("behaviour") or "").strip()
    compile_metric(beh)
    for k in ("hypothesis", "mechanism"):
        if len(str(h.get(k) or "").strip()) < 20:
            raise ValueError(f"{k} is missing")
    norm = re.sub(r"\s+", "", beh)
    for e in ledger:
        if e["verdict"].startswith("REFUTED") and re.sub(r"\s+", "", e["behaviour"]) == norm and e["direction"] == direction:
            raise ValueError(f"behaviour `{beh}` {direction} was refuted in round {e['round']}")
    return {"name": name, "slot": slot, "direction": direction, "behaviour": beh,
            "hypothesis": str(h["hypothesis"]).strip()[:600], "mechanism": str(h["mechanism"]).strip()[:900],
            "edit_type": str(h.get("edit_type") or "")[:60], "failure_mode": str(h.get("failure_mode") or "")[:80]}


def root_bundle_raw(root: Path) -> dict:
    p = Path(root) / "bundle.json"
    try:
        raw = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:
        raw = {}
    return {s: ({"name": v} if isinstance(v, str) else v) for s, v in raw.items()}


def implement(client, bench: str, cand: dict, parent: Path, dest: Path, feedback: str = "",
              shapes: str = "") -> tuple[bool, str]:
    """One proposer call that writes the variant file into a fresh copy of `parent`, selects it in bundle.json, and
    runs the static gate. Returns (ok, reason)."""
    slot, vname = cand["slot"], cand["vname"]
    cur = root_bundle_raw(parent).get(slot) or {"name": "default", "config": {}}
    files = [parent / "variants" / slot / f"{cur['name']}.py"]
    if slot != "agent_loop":  # how the slot is called
        files.append(parent / "variants" / "agent_loop" / f"{(root_bundle_raw(parent).get('agent_loop') or {'name': 'default'})['name']}.py")
    if cur["name"] != "default":  # a wrapper: show what it wraps
        files.append(parent / "variants" / slot / "default.py")
    for s2, sel in sorted(root_bundle_raw(parent).items()):  # edits already adopted in other slots act on every run
        if isinstance(sel, dict) and sel.get("name") not in (None, "default"):
            f2 = parent / "variants" / s2 / f"{sel['name']}.py"
            if f2 not in files:
                files.append(f2)
    code = "\n\n".join(f"### FILE: {f.relative_to(parent).as_posix()}\n{f.read_text(encoding='utf-8')}"
                       for f in files if f.exists())
    proto = (C.ROOT / "h0" / "protocols.py").read_text(encoding="utf-8")
    proto = proto[proto.find("@dataclass"):proto.find("SLOTS =")]
    prompt = IMPL.format(slot=slot, hypothesis=cand["hypothesis"], behaviour=cand["behaviour"],
                         direction=cand["direction"], mechanism=cand["mechanism"], protocols=proto, code=code,
                         vname=vname, base=cur["name"], base_cfg=json.dumps(cur.get("config") or {}),
                         imports=", ".join(sorted(IMPORTS - {"__future__"})), max_literal=MAX_LITERAL,
                         shapes=("\n## What tool results look like on saved runs (structure only; read fields by these "
                                 "names, do not guess others)\n" + shapes + "\n") if shapes else "",
                         feedback=("\n## Your previous attempt was rejected\n" + feedback + "\n") if feedback else "")
    C.new_candidate(dest, parent, {"method": "b4", "cand": cand["id"], "slot": slot, "variant": vname})
    resp = client.chat([{"role": "user", "content": prompt}], tag=f"b4:{bench}:impl", max_tokens=12000,
                       fallback_no_reasoning=True)
    (dest.parent / f"{dest.name}_reply.txt").write_text(resp.content or "", encoding="utf-8")
    rel = f"variants/{slot}/{vname}.py"
    got = reply_files(resp)
    body = got.get(rel) or next((v for k, v in got.items() if k.endswith(".py")), None)
    if not body:
        return False, f"no `### FILE: {rel}` block in the answer"
    apply_files(dest, {rel: body})
    bundle = root_bundle_raw(parent)
    bundle[slot] = {"name": vname, "config": {}}
    (dest / "bundle.json").write_text(json.dumps(bundle, indent=1), encoding="utf-8")
    if not re.search(r"""reg\.register\(\s*["']%s["']\s*,\s*["']%s["']""" % (slot, vname), body):
        return False, f'the file must call reg.register("{slot}", "{vname}", ...)'
    ok, glog = C.static_gate(dest)
    if not ok:
        return False, "validation failed (import / registry / offline toy run):\n" + glog[-1200:] + gate_hint(glog)
    return True, ""


# ---------------------------------------------------------------- evaluation helpers
def ref_cache(bench: str, root) -> Path:
    base = C.RUNS / "diff_ref" / bench
    return base if Path(root).resolve() == Path(C.H0_ROOT).resolve() else base / C.tree_hash(Path(root))


def memo_search(bench: str, cap_chars: int = 300_000_000) -> None:
    """Replays repeat the same environment calls many times: memoise a deterministic search backend in-process."""
    ad = C.adapter(bench)
    if not hasattr(ad, "searcher"):
        return
    s = ad.searcher()
    if getattr(s, "_memo", None) is not None:
        return
    s._memo, size = {}, [0]
    raw = {"search": s.search, "doc_raw": s.doc_raw}

    def wrap(kind):
        def f(*a):
            key = (kind, *a)
            if key in s._memo:
                return s._memo[key]
            v = raw[kind](*a)
            n = len(v or "") if isinstance(v, (str, type(None))) else sum(len(h[2] or "") for h in v)
            if size[0] + n <= cap_chars:
                s._memo[key] = v
                size[0] += n
            return v
        return f
    s.search, s.doc_raw = wrap("search"), wrap("doc_raw")


def pooled(*ts: dict) -> dict:
    t = {k: sum(x.get(k, 0) for x in ts) for k in ("W", "L", "n", "Wt", "Lt")}
    t["p"] = round(V.sign_p(t["W"], t["L"]), 4)
    return t


class Reject(Exception):
    def __init__(self, verdict: str, reason: str):
        super().__init__(reason)
        self.verdict = verdict


def build(client, bench, split, cand, inc_root: Path, cur: list[dict], ws: Path, linter, cfg, tries: int = 2,
          feedback: str = "", suffix: str = "", facts: str = "") -> dict:
    """Code + gates for one candidate: static gate, lint, dry replay on the saved train runs (the edit must change
    at least one, without raising). One repair per failed gate, `tries` attempts in total."""
    why = ""
    shapes = obs_shapes(cur)
    for attempt in range(tries):
        root = ws / "roots" / f"{cand['id']}{suffix}_a{attempt}"
        ok, why = implement(client, bench, cand, inc_root, root, feedback, shapes)
        if ok:
            known = set().union(*(str_consts(f.read_text(encoding="utf-8"))
                                  for f in (Path(inc_root) / "variants").rglob("*.py")))
            why = lint_code((root / "variants" / cand["slot"] / f"{cand['vname']}.py").read_text(encoding="utf-8"),
                            linter, [bench, bench.split("_")[0]], known) or ""
            if why:
                why = "generalisation gate: " + why
        if not why:
            dry = D.run_diff(bench, split, cur, root, inc_root, client, f"{B.TAG}_{bench}_{root.name}", None,
                             ref_cache(bench, inc_root), dry=True, workers=cfg["workers"])
            dmap = D.divergence_map(dry)
            errs = [x["error"] for x in dry if x.get("error")]
            if len(errs) > max(2, 0.05 * len(dry)):
                why = (f"the component raised on {len(errs)} of {len(dry)} saved runs replayed under it, e.g.: "
                       f"{Counter(str(e)[:300] for e in errs).most_common(1)[0][0]}")
            elif dmap["touched"] == 0:
                why = (f"the edit changed nothing in any of {dmap['n']} saved runs replayed under it: its condition "
                       "never held, or its action left every model request and every executed action unchanged. "
                       "Make the condition one that holds on ordinary runs of this harness."
                       + (" The saved runs look like this:\n" + facts if facts else ""))
            else:
                return {"root": root, "dry": dry, "map": dmap, "attempts": attempt + 1}
        print(f"    [{cand['id']}] attempt {attempt}: {why[:160]}", flush=True)
        feedback = why
    raise Reject("NOT BUILT" if "changed nothing" not in why else "DEAD CODE", why[:400])


def trial(client, bench, split, cand, inc_root: Path, cur: list[dict], ws: Path, out: Path, linter, cfg, rng, fin,
          feats, r: int, facts: str = "", fb: str = "", suffix: str = "") -> dict:
    """Stages 1-3 for one candidate. Returns its ledger row (and private fields `_root`, `_recs`, `_touched`)."""
    code = compile_metric(cand["behaviour"])
    row = {k: cand[k] for k in ("id", "name", "slot", "edit_type", "failure_mode", "hypothesis", "mechanism",
                                "behaviour", "direction", "observational")}
    row.update(round=r, verdict="", status="rejected")
    for rev in range(2):
        try:
            b = build(client, bench, split, cand, inc_root, cur, ws, linter, cfg, feedback=fb, suffix=suffix, facts=facts)
        except Reject as e:
            row.update(verdict=f"{e.verdict}: {e}"[:300] if rev == 0 else
                       "INEFFECTIVE: the code did not cause the behaviour and its revision was not built; "
                       "the hypothesis itself is untested")
            return row
        root, dmap = b["root"], b["map"]
        touched = [s for s, x in zip(cur, b["dry"]) if x.get("branched")]
        row.update(coverage=dmap["coverage"], map=dmap, variant=cand["vname"])
        order = list(touched)
        rng.shuffle(order)
        tag = f"{B.TAG}_{bench}_{root.name}"
        label = {"method": "b4", "phase": "screen", "round": r, "cand": cand["id"]}
        recs = D.run_diff(bench, split, order[:N_PROBE], root, inc_root, client, tag, out, ref_cache(bench, inc_root),
                          k=0, workers=cfg["workers"], label=label)
        sh, t = behaviour_shift(code, cand["direction"], recs, feats), V.tally(recs)
        row.update(shift=sh, outcome=t, _root=root, _recs=recs, _touched=touched)
        if sh["shifted"] or t["W"] - t["L"] >= V.MARGIN:
            break
        if rev == 0:  # the code did not cause the behaviour: one revision, told what was measured
            fb = (f"The component ran and changed {dmap['touched']} of {dmap['n']} saved runs, but the behaviour it was "
                  f"meant to cause did not appear: `{cand['behaviour']}` went from {sh['before']} to {sh['after']} over "
                  f"{sh['n']} branched runs ({sh['as_predicted']} in the predicted direction, {sh['opposite']} against). "
                  "Change the mechanism so that the agent actually behaves differently.")
            suffix += "_rev"
            continue
        row.update(verdict="INEFFECTIVE: the code did not cause the behaviour (after one revision); "
                           "the hypothesis itself is untested")
        return row
    # outcome screen: more branches (other touched runs first, then second branches of the same forks)
    rest, k1 = order[N_PROBE:N_SCREEN], order[:max(0, N_SCREEN - len(order))]
    half = rest[:len(rest) // 2] if len(rest) >= 16 else rest
    for srcs, k in ((half, 0), (rest[len(half):], 0), (k1, 1)):
        if not srcs:
            continue
        recs += D.run_diff(bench, split, srcs, root, inc_root, client, tag, out, ref_cache(bench, inc_root), k=k,
                           workers=cfg["workers"], label=label)
        t = V.tally(recs)
        if t["L"] - t["W"] >= 3:  # clearly harmful: stop paying
            break
    sh, t = behaviour_shift(code, cand["direction"], recs, feats), V.tally(recs)
    gain = dmap["coverage"] * (t["W"] - t["L"]) / max(1, t["n"])
    row.update(shift=sh, outcome=t, gain=round(gain, 4), _recs=recs, effects=effects(recs, feats))
    how = "behaviour changed as predicted" if sh["shifted"] else "behaviour did NOT change as predicted"
    if V.reliable(t):
        row.update(verdict=f"SUPPORTED on training runs ({how})")
    elif t["L"] > t["W"]:
        row.update(verdict=f"HARMFUL: {how}, more losses than wins" if not sh["shifted"] else
                   "REFUTED: behaviour changed as predicted and success went down")
    elif sh["shifted"] and t["W"] - t["L"] <= 0:
        row.update(verdict="REFUTED: behaviour changed as predicted, success did not")
    else:
        row.update(verdict=f"INCONCLUSIVE: {how}, gain too small to tell from noise")
    return row


def advance(bench, split, recs, touched_paths: set, have: dict, root, src_root, client, tag, out, cfg, label):
    """Runs of the harness after a merge: an untouched saved run IS a run of the new harness; a touched one is
    replaced by one branch (`have`: branches already run, by source path)."""
    todo = [x for x in recs if x["trajectory_path"] in touched_paths and x["trajectory_path"] not in have]
    got = {x["fork_of"]: x for x in D.run_diff(bench, split, todo, root, src_root, client, tag, out,
                                               ref_cache(bench, src_root), k=0, workers=cfg["workers"],
                                               label=label)} if todo else {}
    res = []
    for x in recs:
        b = have.get(x["trajectory_path"]) or got.get(x["trajectory_path"])
        res.append(b if b and not b.get("error") and b.get("branched") and b.get("trajectory_path") else x)
    return res


def public(row: dict) -> dict:
    return {k: v for k, v in row.items() if not k.startswith("_")}


def select(hyps: list[dict]) -> list[int]:
    """Order in which hypotheses get code. The saved runs rarely contain enough tasks with both outcomes to rank by
    them: the proposer's own order is kept, moved only by clear observational evidence (for: first, against: last)."""
    def cls(h):
        d = h["observational"]["agree"] - h["observational"]["disagree"]
        return 0 if d >= OBS_MARGIN else 2 if d <= -OBS_MARGIN else 1
    return sorted(range(len(hyps)), key=lambda i: (cls(hyps[i]), i))


def harness_state(recs: list[dict], fmap: dict, merged: list[dict]) -> str:
    fs = [fmap[x["trajectory_path"]] for x in recs]
    m = lambda k: sum(f[k] for f in fs) / max(1, len(fs))  # noqa: E731
    return (f"success rate on training tasks {C.score(recs):.1%}; per run: {m('tokens'):.0f} tokens, {m('steps'):.1f} "
            f"steps ({m('step_frac'):.0%} of the step budget), {m('obs_chars'):.0f} characters of tool results\n"
            "edits adopted so far: " + ("; ".join(f"{e['slot']}/{e['name']} ({e.get('basis')})" for e in merged) or "none"))


# ---------------------------------------------------------------- main loop
def run(bench: str, shared: dict, client, cfg: dict = C.SMOKE) -> dict:
    ws = C.RUNS / B.TAG / bench
    if ws.exists() and not B.RESUME:
        shutil.rmtree(ws)
    (ws / "roots").mkdir(parents=True, exist_ok=True)
    out = C.OUT / f"{B.TAG}_{bench}.jsonl"
    if out.exists() and not B.RESUME:
        out.unlink()
    client = B._Replay(client, ws / "llm_cache.jsonl")
    memo_search(bench)
    tasks = shared["tasks"]
    tr_split, val_split = tasks["train"][0], tasks["val"][0]
    rng = random.Random(B.SEED)
    fin = B.FINISH.get(bench)

    def usable(recs):
        return [x for x in recs if x.get("trajectory_path") and Path(x["trajectory_path"]).exists() and not x.get("error")]
    cur, curv = usable(shared["h0_train"]), usable(shared["h0_val"])
    if not cur or not curv:
        raise SystemExit("B4 v7 forks the saved H0 runs: the H0 train/val records need their trajectory files")
    fcache: dict[str, dict] = {}

    def feats(path):
        if path not in fcache:
            fcache[path] = features(path, fin)
        return fcache[path]
    instructions, tools = [], set()
    for rec in cur + curv:
        for e in V.load_events(rec["trajectory_path"]):
            if e["type"] == "task":
                instructions.append(str(e.get("instruction") or ""))
            elif e["type"] == "step":
                tools.add(e.get("tool"))
    tools = {t for t in tools if t}
    linter = B.Linter(instructions, sorted({x["task_id"] for x in cur}) + list(tasks["val"][1]), tools)

    inc_root = Path(C.H0_ROOT)
    ledger: list[dict] = []
    merged_ids: list[str] = []
    registry: dict = {}
    log = {"version": "v7-components", "rounds": [],
           "params": {"n_hyp": N_HYP, "n_cand": N_CAND, "n_probe": N_PROBE, "n_screen": N_SCREEN, "k_val": K_VAL,
                      "k_test": K_TEST, "alpha": V.ALPHA, "margin": V.MARGIN}}
    stall, n_c = 0, 0
    for r in range(1, cfg["rounds"] + 1):
        C.budget_check(f"b4[{bench}] round {r}")
        rd = {"round": r, "train": round(C.score(cur), 4), "val": round(C.score(curv), 4)}
        sigs = {x["trajectory_path"]: R.trajectory_signals(x["trajectory_path"], fin) for x in cur}
        fails = [x for x in cur if not x["success"]]
        reps = B.reports(client, cur, sigs, rng, bench)
        labelled = [{"task_id": x["task_id"], "label": str(h.get("failure_label") or h.get("why") or "")[:120],
                     "why": str(h.get("why") or "")[:200], "cause": h.get("cause"), "rule_modes": x["modes"]}
                    for x in reps if not x["success"] for h in [x.get("hindsight") or {}] if h.get("cause")]
        registry = G.discover_modes(client, bench, labelled, registry, tools, B._ask_json)
        mode_info = G.mode_counts(registry, G.mode_tasks(registry, fails, sigs), set())
        dig = list(fails)
        rng.shuffle(dig)
        fmap = {x["trajectory_path"]: feats(x["trajectory_path"]) for x in cur}
        ctx = {"tree": C.tree_text(inc_root, None), "n_runs": len(cur), "succ": f"{C.score(cur):.1%}",
               "feat_table": feat_table(cur, fmap), "facts": run_facts(cur, fmap), "modes": json.dumps(mode_info, default=str)[:2500],
               "reports": reports_view(reps), "tools": tools,
               "digests": [C.summarize_trajectory(x["trajectory_path"], max_events=24, max_chars=300, task_chars=400)
                           for x in dig[:5]]}
        # stage 0: hypotheses against the saved runs (free); one re-ask when too few are usable
        hyps, why = [], ""
        for ask in range(2):
            d = propose(client, bench, ctx, ledger, r, ws, feedback=why)
            hyps, bad = [], []
            for h in (d.get("candidates") or [])[:N_HYP + 2]:
                try:
                    c = validate_hyp(h, ledger)
                    c["observational"] = observe(compile_metric(c["behaviour"]), c["direction"], cur, fmap)
                    hyps.append(c)
                except Exception as e:
                    bad.append({"name": str((h or {}).get("name"))[:40] if isinstance(h, dict) else "?",
                                "behaviour": str((h or {}).get("behaviour"))[:120] if isinstance(h, dict) else "",
                                "reason": str(e)[:200]})
            if bad:
                rd.setdefault("invalid", []).extend(bad)
            if len(hyps) >= N_CAND:
                break
            why = "\n".join(f"- {b['name']}: behaviour `{b['behaviour']}` rejected ({b['reason']})" for b in bad) \
                or "- no usable candidates"
        rd["analysis"] = str(d.get("analysis", ""))[:600]
        ranked = select(hyps)
        rows, tried, per_slot, revised = [], set(), Counter(), False
        state = harness_state(cur, fmap, [e for e in ledger if e.get("status") == "merged"])
        for i in ranked:
            # a candidate whose code never ran on a real run cost no agent runs: the next hypothesis takes its place
            if sum(1 for x in rows if not x["id"].endswith("r")
                   and not x["verdict"].startswith(("DEAD CODE", "NOT BUILT"))) >= N_CAND:
                break
            if per_slot[hyps[i]["slot"]] >= max(1, N_CAND - 1):  # not all of a round in one slot
                continue
            tried.add(i)
            per_slot[hyps[i]["slot"]] += 1
            n_c += 1
            cand = {**hyps[i], "id": f"c{n_c}"}
            cand["vname"] = f"{cand['id']}_{cand['name']}"
            print(f"  [b4 {bench}] round {r} {cand['id']} {cand['slot']}/{cand['name']}: `{cand['behaviour']}` "
                  f"{cand['direction']} obs={cand['observational']}", flush=True)
            row = trial(client, bench, tr_split, cand, inc_root, cur, ws, out, linter, cfg, rng, fin, feats, r,
                        ctx["facts"])
            rows.append(row)
            if row.get("effects") and row["outcome"]["L"] - row["outcome"]["W"] < V.MARGIN:  # not clearly harmful
                apply_review(row, review_vote(client, bench, row, state, can_revise=not revised), feats)
            print(f"  [b4 {bench}] round {r} {cand['id']}: cover={row.get('coverage')} shift={row.get('shift')} "
                  f"outcome={ {k: (row.get('outcome') or {}).get(k) for k in ('W', 'L', 'n', 'p')} } "
                  f"-> {row['verdict']}", flush=True)
            if row.get("review"):
                print(f"    [{cand['id']}] effects: {effects_view(row['effects'])}\n    [{cand['id']}] review: "
                      f"{row['review']} -> {row['status']}", flush=True)
            if row["status"] == "revise":  # one revision per round: the reviewer's change, measured from scratch
                revised = True
                c2 = {**cand, "id": cand["id"] + "r", "mechanism": (cand["mechanism"] + " REVISED: " + row["review"]["revision"])[:1500]}
                fb = (f"An earlier version of this edit was measured on {row['outcome']['n']} runs. Clear effects: "
                      f"{effects_view(row['effects'])}. Success: {row['outcome']['W']} wins / {row['outcome']['L']} losses. "
                      f"The reviewer asks for this change: {row['review']['revision']}\nThe earlier code:\n```python\n"
                      + (row["_root"] / "variants" / cand["slot"] / f"{cand['vname']}.py").read_text(encoding="utf-8")[:9000] + "\n```")
                row2 = trial(client, bench, tr_split, c2, inc_root, cur, ws, out, linter, cfg, rng, fin, feats, r,
                             ctx["facts"], fb=fb)
                rows.append(row2)
                if row2.get("effects") and row2["outcome"]["L"] - row2["outcome"]["W"] < V.MARGIN:
                    apply_review(row2, review_vote(client, bench, row2, state), feats)
                print(f"  [b4 {bench}] round {r} {c2['id']}: shift={row2.get('shift')} outcome={row2.get('outcome')} "
                      f"-> {row2['verdict']} | effects: {effects_view(row2.get('effects'))} | review: "
                      f"{row2.get('review')} -> {row2['status']}", flush=True)
        rd["hypotheses"] = [{**{k: hyps[i][k] for k in ("name", "slot", "behaviour", "direction", "observational")},
                             "chosen": i in tried} for i in ranked]
        # stage 4: confirmation on held-out tasks, most promising first; one merge per round
        merged = False
        for row in sorted([x for x in rows if x["status"] == "admitted"],
                          key=lambda x: (x.get("basis") != "success", -x.get("gain", 0))):
            root = row["_root"]
            vtag = f"{B.TAG}_{bench}_{root.name}_val"
            vdry = D.run_diff(bench, val_split, curv, root, inc_root, client, vtag, None, ref_cache(bench, inc_root),
                              dry=True, workers=cfg["workers"])
            vhit = [s for s, x in zip(curv, vdry) if x.get("branched")]
            vrecs = []
            for k in range(K_VAL):
                vrecs += D.run_diff(bench, val_split, vhit, root, inc_root, client, vtag, out,
                                    ref_cache(bench, inc_root), k=k, workers=cfg["workers"],
                                    label={"method": "b4", "phase": "val", "round": r, "cand": row["id"]})
            tv = V.tally(vrecs)
            both = pooled(row["outcome"], tv)
            row["val"] = {k: tv[k] for k in ("W", "L", "n", "p", "Wt", "Lt")}
            row["pooled"] = both
            # held-out runs must not contradict the training evidence. Adopted for success: the pooled evidence must
            # stay reliable. Adopted for another benefit: no net loss, and the claimed effect appears again.
            if row["basis"] == "success":
                confirmed = tv["W"] - tv["L"] >= 0 and V.reliable(both)
            else:
                c = row["review"]["claim"]
                row["val_claim"] = behaviour_shift(compile_metric(c["behaviour"]), c["direction"], vrecs, feats)
                confirmed = tv["L"] - tv["W"] < V.MARGIN and both["W"] - both["L"] >= 0 and row["val_claim"]["shifted"]
            if confirmed:
                lab = {"method": "b4", "phase": "inc_train", "round": r, "cand": row["id"]}
                cur = advance(bench, tr_split, cur, {s["trajectory_path"] for s in row["_touched"]},
                              {x["fork_of"]: x for x in row["_recs"] if x["k"] == 0}, root, inc_root, client,
                              f"{B.TAG}_{bench}_{root.name}", out, cfg, lab)
                curv = advance(bench, val_split, curv, {s["trajectory_path"] for s in vhit},
                               {x["fork_of"]: x for x in vrecs if x["k"] == 0}, root, inc_root, client, vtag, out, cfg,
                               {**lab, "phase": "inc_val"})
                inc_root, merged = root, True
                merged_ids.append(row["id"])
                row.update(status="merged", decision=f"ADOPTED for {row['basis']} (held-out runs agree): "
                                                     f"{row['review']['reason']}",
                           verdict=row["verdict"].replace("SUPPORTED on training runs",
                                                          "SUPPORTED and MERGED (held-out runs agree)"))
                rd["result"] = f"merged {row['id']} ({row['slot']}/{row['name']}): train={C.score(cur):.3f} val={C.score(curv):.3f}"
                break
            row.update(status="not_confirmed", decision=f"NOT ADOPTED: the {row['basis']} benefit measured on training "
                       f"runs was not confirmed on held-out runs ({tv['W']} wins / {tv['L']} losses of {tv['n']}"
                       + (f"; claim {row['val_claim']['as_predicted']} as predicted / {row['val_claim']['opposite']} "
                          f"against" if row.get("val_claim") else "") + ")")
            if row["basis"] == "success":
                row["verdict"] = "NOT CONFIRMED: gain on training runs, not on held-out runs"
        if not merged:
            rd["result"] = "no merge" if any(x["status"] == "not_confirmed" for x in rows) else "no candidate admitted"
        ledger += [public(x) for x in rows]
        rd["candidates"] = [public(x) for x in rows]
        stall = 0 if merged else stall + 1
        log["rounds"].append(rd)
        (ws / "ledger.json").write_text(json.dumps(ledger, indent=1, default=str))
        (ws / "log.json").write_text(json.dumps(log, indent=1, default=str))
        print(f"  [b4 {bench}] round {r}: {[(x['id'], x['slot'], x['verdict'].split(':')[0]) for x in rows]} -> "
              f"{rd['result']}", flush=True)
        if stall >= B.STALL_ROUNDS and B.MIN_ROUNDS <= r < cfg["rounds"]:
            log["early_stop"] = {"round": r, "reason": f"{stall} rounds without a merge"}
            break
    # ---- freeze and test
    log["final"] = {"root": str(inc_root), "merged": merged_ids, "train": C.score(cur), "val": C.score(curv)}
    (ws / "final.json").write_text(json.dumps(log["final"], indent=1, default=str))
    C.budget_check(f"b4[{bench}] test")
    h0_test = usable(shared.get("h0_test") or [])
    base = C.score(h0_test) if h0_test else 0.0
    if merged_ids and h0_test:
        ts = tasks["test"][0]
        tag = f"{B.TAG}_{bench}_testfork"
        tdry = D.run_diff(bench, ts, h0_test, inc_root, C.H0_ROOT, client, tag, None, ref_cache(bench, C.H0_ROOT),
                          dry=True, workers=cfg["workers"])
        hit = [s for s, x in zip(h0_test, tdry) if x.get("branched")]
        trecs = []
        for k in range(K_TEST):
            trecs += D.run_diff(bench, ts, hit, inc_root, C.H0_ROOT, client, tag, out, ref_cache(bench, C.H0_ROOT), k=k,
                                workers=cfg["workers"], label={"method": "b4", "phase": "test_branch"})
        log["test_branch"] = {**D.estimate(h0_test, trecs), "k": K_TEST, "map": D.divergence_map(tdry)}
        test = B._evaluate(bench, ts, tasks["test"][1], inc_root, client, f"{B.TAG}_{bench}_test", out,
                           workers=cfg["workers"], label={"method": "b4", "phase": "test"})
    else:  # the final harness is H0: its test runs are the shared H0 test runs
        log["test_branch"] = {"base": round(base, 4), "est": round(base, 4), "gain": 0.0, "n": len(h0_test), "touched": 0}
        test = list(shared.get("h0_test") or [])
    print(f"  [b4 {bench}] test_branch: {log['test_branch']}", flush=True)
    log["test"] = {"success": C.score(test), "n": len(test), "rerun": bool(merged_ids)}
    recs = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines() if l.strip()] if out.exists() else []
    log["cost"] = {"episodes": len(recs), "tokens": sum(x.get("tokens") or 0 for x in recs),
                   "evolution_tokens": sum(x.get("tokens") or 0 for x in recs if x.get("phase") not in ("test", "test_branch"))}
    (ws / "log.json").write_text(json.dumps(log, indent=1, default=str))
    return {"log": log, "test": test}
