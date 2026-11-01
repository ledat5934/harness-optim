"""B4 runtime: behaviour signals, the precondition DSL and the hooked agent loop.

A *mechanism* is a declarative candidate `precondition -> action` (docs/idea_v2.md, 3.1 and 3.4):

    {"id": "m3", "slot": "termination", "kind": "reject_finish", "mechanism": "refuse-early-giveup",
     "precondition": "answer_hedged and steps_left > 5", "text": "...", "max_fires": 1}

kinds and their hook (the slot taxonomy of docs/idea_v2.md, section 2):
    guidance       S1/S9  appended to the system prompt at episode start (precondition on start signals)
    inject         S5/S6/S7  a user message inserted before the next LLM call
    annotate_obs   S4     a note appended to the observation just returned by a tool
    reject_finish  S7/S8  the finish call is refused with `text` as feedback (before the verifier)

Preconditions are expressions over generic, benchmark-independent signals (SIGNALS). They are parsed with a
whitelist (no attribute access, no subscripts, no calls except n/min/max/abs), so a candidate cannot run code.
Every firing is recorded in the trajectory as a `mech` event (activation telemetry: a mechanism that never
fires gets no credit).
"""
from __future__ import annotations

import ast
import json
import re

from h0.protocols import Action, LoopOutcome, LoopState

# ---------------------------------------------------------------- signals
_ERR = re.compile(r"\b(error|exception|traceback|failed|failure|invalid|not found|denied|unauthori[sz]ed|forbidden|"
                  r"does not exist|no such|not allowed|missing required|unexpected)\b", re.I)
_HEDGE = re.compile(r"((?:can['’]?t|cannot|could(?: not|n['’]t)|unable to|not able to|did not|didn['’]t)\s+"
                    r"(?:\w+\s+){0,3}?(?:determine|find|identify|confirm|locate|verify|establish)"
                    r"|\bunknown\b|not known|insufficient|no (?:reliable |clear )?(?:information|evidence)|"
                    r"\bunclear\b|i don['’]t know|\bn/a\b|undetermined|not (?:be )?determined)", re.I)

SIGNALS = {
    "step": "steps taken so far",
    "max_steps": "step budget of the task",
    "steps_left": "max_steps - step",
    "step_frac": "step / max_steps (0..1)",
    "n_actions": "tool calls executed so far",
    "n_errors": "observations so far that look like an error message",
    "err_streak": "consecutive most-recent observations that look like errors",
    "recent_errors": "error-like observations among the last 5",
    "repeat_streak": "consecutive most-recent actions identical (tool+args) to the one before",
    "repeat_ratio": "fraction of actions that repeat an earlier identical action",
    "same_obs_streak": "consecutive most-recent observations identical to the previous observation",
    "last_obs_len": "characters of the last observation",
    "no_action_streak": "consecutive replies without a tool call",
    "distinct_tools": "number of different tools used",
    "finish_attempts": "finish calls so far (including the current one)",
    "is_finish": "true while the agent is calling the finish tool",
    "answer_len": "characters of the answer in the current finish call (0 otherwise)",
    "answer_hedged": "the current finish answer says the answer is unknown / not found / cannot be determined",
    "has_finish_tool": "the task ends with an explicit finish tool carrying an answer or completion",
}
FUNCS = {"n": "n('tool') = times that tool was called", "min": "min", "max": "max", "abs": "abs"}


class Tracker:
    """Incremental signal state of one episode (also replayable over a saved trajectory)."""

    def __init__(self, max_steps: int, has_finish: bool):
        self.max_steps, self.has_finish = max_steps, has_finish
        self.step = 0
        self.actions: list[str] = []
        self.tools: list[str] = []
        self.obs: list[str] = []
        self.errs: list[bool] = []
        self.no_action_streak = 0
        self.finish_attempts = 0
        self.cur_answer: str | None = None

    def on_action(self, tool: str, args) -> None:
        self.actions.append(json.dumps([tool, args], sort_keys=True, default=str))
        self.tools.append(tool)
        self.no_action_streak = 0

    def on_obs(self, obs: str) -> None:
        self.obs.append(obs or "")
        self.errs.append(bool(_ERR.search((obs or "")[:2000])))

    def signals(self) -> dict:
        def streak(xs, pred):
            k = 0
            for x in reversed(xs):
                if not pred(x):
                    break
                k += 1
            return k
        rep_streak = 0
        for i in range(len(self.actions) - 1, 0, -1):
            if self.actions[i] != self.actions[i - 1]:
                break
            rep_streak += 1
        seen, rep = set(), 0
        for a in self.actions:
            rep += a in seen
            seen.add(a)
        same_obs = 0
        for i in range(len(self.obs) - 1, 0, -1):
            if self.obs[i] != self.obs[i - 1]:
                break
            same_obs += 1
        ans = self.cur_answer
        return {
            "step": self.step, "max_steps": self.max_steps, "steps_left": self.max_steps - self.step,
            "step_frac": self.step / max(1, self.max_steps), "n_actions": len(self.actions),
            "n_errors": sum(self.errs), "err_streak": streak(self.errs, bool), "recent_errors": sum(self.errs[-5:]),
            "repeat_streak": rep_streak, "repeat_ratio": rep / len(self.actions) if self.actions else 0.0,
            "same_obs_streak": same_obs, "last_obs_len": len(self.obs[-1]) if self.obs else 0,
            "no_action_streak": self.no_action_streak, "distinct_tools": len(set(self.tools)),
            "finish_attempts": self.finish_attempts, "is_finish": ans is not None,
            "answer_len": len(ans or ""), "answer_hedged": bool(ans is not None and (not ans.strip() or _HEDGE.search(ans[:400]))),
            "has_finish_tool": self.has_finish,
        }

    def n(self, tool: str) -> int:
        return self.tools.count(tool)


# ---------------------------------------------------------------- DSL
_OK_NODES = (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not, ast.USub, ast.Compare, ast.Eq,
             ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod,
             ast.Name, ast.Load, ast.Constant, ast.Call)


def compile_pre(expr: str):
    """Whitelisted expression -> code object. Raises ValueError with the reason."""
    if not isinstance(expr, str) or not expr.strip() or len(expr) > 300:
        raise ValueError("precondition must be a non-empty expression of <= 300 chars")
    tree = ast.parse(expr.strip(), mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, _OK_NODES):
            raise ValueError(f"disallowed syntax: {type(node).__name__}")
        if isinstance(node, ast.Name) and node.id not in SIGNALS and node.id not in FUNCS \
                and node.id not in ("True", "False"):
            raise ValueError(f"unknown signal {node.id!r}")
        if isinstance(node, ast.Call) and not (isinstance(node.func, ast.Name) and node.func.id in FUNCS):
            raise ValueError("only n(), min(), max(), abs() may be called")
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) > 40:
            raise ValueError("string constants must be tool names (<= 40 chars)")
    return compile(tree, "<pre>", "eval")


def eval_pre(code, tr: Tracker, sig: dict | None = None) -> bool:
    env = dict(sig or tr.signals())
    env.update(n=tr.n, min=min, max=max, abs=abs)
    try:
        return bool(eval(code, {"__builtins__": {}}, env))  # noqa: S307 - whitelisted AST, no builtins
    except Exception:
        return False


KINDS = ("guidance", "inject", "annotate_obs", "reject_finish")


def validate_mechanism(m: dict) -> dict:
    """Schema check + normalisation. Raises ValueError."""
    if not isinstance(m, dict):
        raise ValueError("mechanism must be an object")
    kind = m.get("kind")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    text = str(m.get("text") or "").strip()
    if not 10 <= len(text) <= 1200:
        raise ValueError("text must be 10..1200 characters")
    pre = str(m.get("precondition") or "True").strip()
    compile_pre(pre)
    try:
        max_fires = int(m.get("max_fires", 1 if kind == "reject_finish" else 2))
    except (TypeError, ValueError):
        raise ValueError("max_fires must be an int")
    if kind == "reject_finish" and "is_finish" not in pre and "answer_" not in pre and "finish_attempts" not in pre:
        pre = f"({pre}) and is_finish"
    return {"id": str(m.get("id") or ""), "slot": str(m.get("slot") or ""), "kind": kind,
            "mechanism": str(m.get("mechanism") or "")[:80], "target_behavior": str(m.get("target_behavior") or "")[:160],
            "precondition": pre, "text": text, "max_fires": max(1, min(5, max_fires))}


class _Fmt(dict):
    def __missing__(self, k):
        return "{" + k + "}"


def render(text: str, sig: dict) -> str:
    try:
        return text.format_map(_Fmt({k: (round(v, 2) if isinstance(v, float) else v) for k, v in sig.items()}))
    except Exception:
        return text


# ---------------------------------------------------------------- hooked loop
class HookedLoop:
    """The H0 ReAct loop (agent_loop/default) with four hook points for mechanisms. With no mechanisms it
    behaves exactly like agent_loop/default."""

    def __init__(self, mechanisms: list | None = None, max_no_action: int = 3, temperature: float | None = None,
                 max_tokens: int | None = None, budget_nudge_steps: int = 2):
        self.mechs = [validate_mechanism(m) for m in (mechanisms or [])]
        self.code = {i: compile_pre(m["precondition"]) for i, m in enumerate(self.mechs)}
        self.max_no_action, self.temperature, self.max_tokens = max_no_action, temperature, max_tokens
        self.budget_nudge_steps = budget_nudge_steps

    def _fire(self, kind, tr, fired, rec, sig=None):
        sig = sig or tr.signals()
        out = []
        for i, m in enumerate(self.mechs):
            if m["kind"] != kind or fired.get(i, 0) >= m["max_fires"]:
                continue
            if eval_pre(self.code[i], tr, sig):
                fired[i] = fired.get(i, 0) + 1
                rec.note("mech", id=m["id"], kind=kind, step=tr.step)
                out.append(render(m["text"], sig))
        return out

    def run(self, task, env, h, llm, rec) -> LoopOutcome:
        tr = Tracker(task.max_steps, bool(task.finish_tool))
        fired: dict[int, int] = {}
        system = h.system_prompt
        guide = self._fire("guidance", tr, fired, rec)
        if guide:
            system = system + "\n\nOperating guidance:\n" + "\n".join(f"- {g}" for g in guide)
        state = LoopState(step=0, history=[{"role": "user", "content": _first_user(task)}])
        notes = h.memory.recall(task)
        no_action, llm_calls, nudged = 0, 0, False
        while state.step < task.max_steps:
            tr.step = state.step
            tr.cur_answer = None
            for t in self._fire("inject", tr, fired, rec):
                state.history.append({"role": "user", "content": t})
            tools = h.tool_policy.tools(task)
            remaining = task.max_steps - state.step
            if task.finish_tool and self.budget_nudge_steps and remaining <= self.budget_nudge_steps and not nudged:
                state.history.append({"role": "user", "content":
                                      f"Only {remaining} step(s) left. Call `{task.finish_tool}` now with your best "
                                      f"final answer based on the evidence gathered so far."})
                nudged = True
            tool_choice = None
            if task.finish_tool and self.budget_nudge_steps and remaining == 1:
                only = [t for t in tools if t["function"]["name"] == task.finish_tool]
                if only:
                    tools = only
                    tool_choice = {"type": "function", "function": {"name": task.finish_tool}}
            msgs = h.context_mgmt.build(system, task, state.history, notes)
            resp = llm.chat(msgs, tools=tools, tag=f"h:{task.benchmark}", tool_choice=tool_choice,
                            temperature=self.temperature, max_tokens=self.max_tokens)
            llm_calls += 1
            rec.llm(resp, step=state.step)
            actions = h.tool_policy.parse(resp, task)
            state.history.append(_assistant_msg(resp, actions))
            if not actions:
                no_action += 1
                tr.no_action_streak = no_action
                if no_action >= self.max_no_action:
                    return LoopOutcome("no_progress", state.step, llm_calls=llm_calls)
                state.history.append({"role": "user", "content":
                                      "You did not call a tool. Continue by calling exactly one tool."})
                continue
            no_action = 0
            act = actions[0]
            offered = {t["function"]["name"] for t in tools}
            if act.tool not in offered:
                for a in actions:
                    _tool_reply(state, a, f"Tool '{a.tool}' is not available now. Available: {sorted(offered)}.")
                state.step += 1
                continue
            for extra in actions[1:]:
                if extra.call_id:
                    state.history.append({"role": "tool", "tool_call_id": extra.call_id,
                                          "content": "Ignored: only one tool call is executed per step."})
            if task.finish_tool and act.tool == task.finish_tool:
                state.finish_attempts += 1
                tr.finish_attempts = state.finish_attempts
                tr.cur_answer = str(act.args.get("answer", act.args.get("status", "")) if isinstance(act.args, dict) else "")
                if remaining > 1:  # never refuse the forced last-step answer
                    rej = self._fire("reject_finish", tr, fired, rec)
                    if rej:
                        _tool_reply(state, act, "Not accepted yet: " + " ".join(rej))
                        state.step += 1
                        continue
                v = h.verifier.check(task, act, state, env_done=False)
                if not v.accept:
                    _tool_reply(state, act, f"Not accepted yet: {v.feedback}")
                    rec.note("verifier_reject", feedback=v.feedback, step=state.step)
                    state.step += 1
                    continue
                sr = env.step(act.tool, act.args)
                state.step += 1
                rec.step(act.tool, act.args, sr.observation)
                return LoopOutcome("finish", state.step, final_answer=str(act.args.get("answer", "")),
                                   llm_calls=llm_calls)
            tr.on_action(act.tool, act.args)
            sr = env.step(act.tool, act.args)
            state.step += 1
            obs = h.tool_policy.format_observation(act, sr, task)
            tr.on_obs(sr.observation)
            tr.step = state.step
            notes_obs = self._fire("annotate_obs", tr, fired, rec)
            if notes_obs:
                obs = obs + "\n\n[Note] " + " ".join(notes_obs)
            state.last_observation = obs
            rec.step(act.tool, act.args, sr.observation)
            _tool_reply(state, act, obs)
            if sr.done:
                v = h.verifier.check(task, act, state, env_done=True)
                if v.accept:
                    return LoopOutcome("done", state.step, llm_calls=llm_calls)
                state.history.append({"role": "user", "content": f"Verifier: {v.feedback}"})
        return LoopOutcome("max_steps", state.step, llm_calls=llm_calls)


def _first_user(task) -> str:
    parts = [task.instruction]
    if task.initial_observation:
        parts.append(f"Initial observation:\n{task.initial_observation}")
    return "\n\n".join(parts)


def _assistant_msg(resp, actions) -> dict:
    m = {"role": "assistant", "content": resp.content or ""}
    native = [a for a in actions if a.call_id]
    if native:
        m["tool_calls"] = [{"id": a.call_id, "type": "function", "function": a.raw["function"]} for a in native]
    return m


def _tool_reply(state, act: Action, text: str) -> None:
    if act.call_id:
        state.history.append({"role": "tool", "tool_call_id": act.call_id, "content": text})
    else:
        state.history.append({"role": "user", "content": f"Observation:\n{text}"})


# ---------------------------------------------------------------- offline: signals of a saved trajectory
def trajectory_signals(path: str, finish_tool: str | None = None) -> dict:
    """End-of-episode behaviour signature of a saved trajectory (same signals as at runtime), plus outcome fields."""
    try:
        d = json.loads(open(path, encoding="utf-8").read())
    except Exception:
        return {}
    ev = d.get("events", [])
    task = next((e for e in ev if e["type"] == "task"), {})
    max_steps = int(task.get("max_steps") or 30)
    steps = [e for e in ev if e["type"] == "step"]
    fin = finish_tool
    tr = Tracker(max_steps, True)
    last_answer = None
    for e in steps:
        a = e.get("args") if isinstance(e.get("args"), dict) else {}
        if fin and e.get("tool") == fin or (fin is None and "answer" in a and e is steps[-1]):
            last_answer = str(a.get("answer", ""))
            continue
        tr.on_action(e.get("tool"), e.get("args"))
        tr.on_obs(str(e.get("observation") or ""))
    tr.step = len(steps)
    tr.cur_answer = last_answer
    s = tr.signals()
    out = d.get("outcome")
    s.update(success=bool(d.get("success")), stopped=(out or {}).get("stopped") if isinstance(out, dict) else out,
             tokens=d.get("tokens") or 0, mech_fired=sorted({e.get("id") for e in ev if e["type"] == "mech"}),
             answered=last_answer is not None)
    return s
