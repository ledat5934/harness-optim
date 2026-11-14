"""Offline tests of B4 v5 (no LLM calls, no benchmark): two-tier preconditions, the replay pre-check and fired-only
credit. Run: python tests/test_b4_v5.py"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from baselines import b4_repertoire as B  # noqa: E402
from baselines.hg import runtime as R  # noqa: E402
from h0.protocols import Action, Verdict  # noqa: E402


def _traj(steps: list[tuple[str, dict, str]], max_steps: int = 10) -> str:
    ev = [{"type": "task", "max_steps": max_steps, "instruction": "x"}]
    ev += [{"type": "step", "n": i + 1, "tool": t, "args": a, "observation": o} for i, (t, a, o) in enumerate(steps)]
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump({"events": ev, "success": False}, f)
    f.close()
    return f.name


def test_llm_check_schema():
    m = R.validate_mechanism({"kind": "inject", "precondition": "n_errors >= 1", "text": "Read the error and retry.",
                              "llm_check": "Did the last tool call fail because of a wrong argument?"})
    assert m["llm_check"].startswith("Did")
    for bad in ({"kind": "guidance", "text": "Be careful with errors.", "llm_check": "Is this a long enough question?"},
                {"kind": "inject", "text": "Be careful with errors.", "llm_check": "short?"}):
        try:
            R.validate_mechanism(bad)
            raise AssertionError("should be rejected")
        except ValueError:
            pass
    assert R.validate_mechanism({"kind": "inject", "text": "Read the error and retry."})["llm_check"] == ""


def test_replay_fires_hook_points():
    p = _traj([("search", {"q": "a"}, "Error: invalid query"), ("search", {"q": "b"}, "Error: invalid query"),
               ("finish", {"answer": "cannot be determined"}, "ok")])
    c = R.compile_pre
    assert R.replay_fires(c("n_errors >= 2"), p, "inject", "finish")          # before the 3rd call
    assert R.replay_fires(c("err_streak >= 2"), p, "annotate_obs", "finish")  # after the 2nd result
    assert not R.replay_fires(c("n_errors >= 3"), p, "inject", "finish")
    assert R.replay_fires(c("answer_hedged and n('search') >= 2"), p, "reject_finish", "finish")
    assert not R.replay_fires(c("answer_hedged and n('search') >= 3"), p, "reject_finish", "finish")
    assert R.replay_fires(c("True"), p, "guidance", "finish")


class _LLM:
    """Agent: search, then finish with a hedged answer, then a real answer. Checks answer `check_reply`."""

    def __init__(self, check_reply: str):
        self.check_reply, self.calls, self.checks = check_reply, 0, 0

    def chat(self, msgs, tools=None, tag="", **kw):
        if tag.endswith(":check"):
            self.checks += 1
            return SimpleNamespace(content=self.check_reply, tool_calls=[], prompt_tokens=5, completion_tokens=1, cost=0.0)
        self.calls += 1
        call = [("search", {"q": "x"}), ("finish", {"answer": "unknown"}), ("finish", {"answer": "Paris"})][min(self.calls - 1, 2)]
        return SimpleNamespace(content="", tool_calls=[call], prompt_tokens=10, completion_tokens=2, cost=0.0)


class _Rec:
    def __init__(self):
        self.events = []

    def llm(self, resp, **kw):
        self.events.append({"type": "llm", **kw})

    def note(self, kind, **kw):
        self.events.append({"type": kind, **kw})

    def step(self, tool, args, obs, **kw):
        self.events.append({"type": "step", "tool": tool})


def _run(check_reply: str):
    task = SimpleNamespace(max_steps=8, finish_tool="finish", instruction="Find the city.", initial_observation="",
                           benchmark="toy")
    h = SimpleNamespace(
        system_prompt="sys", memory=SimpleNamespace(recall=lambda t: None),
        context_mgmt=SimpleNamespace(build=lambda s, t, hist, n: [{"role": "system", "content": s}] + hist),
        verifier=SimpleNamespace(check=lambda *a, **k: Verdict(True)),
        tool_policy=SimpleNamespace(
            tools=lambda t: [{"type": "function", "function": {"name": n}} for n in ("search", "finish")],
            parse=lambda resp, t: [Action(c[0], c[1]) for c in resp.tool_calls],
            format_observation=lambda a, sr, t: sr.observation))
    env = SimpleNamespace(step=lambda tool, args: SimpleNamespace(observation="doc text", done=False))
    loop = R.HookedLoop([{"id": "m1", "kind": "reject_finish", "precondition": "answer_hedged",
                          "text": "Search more before giving up.",
                          "llm_check": "Has the agent searched in more than one way?"}])
    llm, rec = _LLM(check_reply), _Rec()
    out = loop.run(task, env, h, llm, rec)
    return out, llm, rec


def test_llm_check_gates_firing():
    out, llm, rec = _run("YES")
    assert llm.checks == 1 and any(e["type"] == "mech" for e in rec.events)
    assert out.final_answer == "Paris"  # hedged answer refused, second answer accepted
    out, llm, rec = _run("NO, it did not")
    assert llm.checks == 1 and not any(e["type"] == "mech" for e in rec.events)
    assert out.final_answer == "unknown"
    assert any(e["type"] == "mech_check" and e["yes"] is False for e in rec.events)


def test_paired_margin_fired_only():
    new = [{"task_id": t, "success": s} for t, s in (("a", True), ("b", False), ("c", True), ("d", False))]
    old = [{"task_id": t, "success": s} for t, s in (("a", False), ("b", True), ("c", False), ("d", True))]
    assert B.paired_margin(new, old) == (2, 2)
    assert B.paired_margin(new, old, {"a", "c"}) == (2, 0)


def test_precheck_revises_a_mechanism_that_would_not_fire():
    fail = _traj([("search", {"q": "a"}, "nothing"), ("finish", {"answer": "unknown"}, "ok")])
    good = _traj([("search", {"q": "a"}, "doc"), ("finish", {"answer": "Paris"}, "ok")])
    fails = [{"task_id": "t1", "success": False, "trajectory_path": fail}]
    cur = fails + [{"task_id": "t2", "success": True, "trajectory_path": good}]
    sigs = {fail: R.trajectory_signals(fail, "finish"), good: R.trajectory_signals(good, "finish")}
    lint = B.Linter(["Find the capital city of the country"], ["t1", "t2"], {"search", "finish"})
    m = R.validate_mechanism({"id": "m1", "kind": "reject_finish", "precondition": "answer_hedged and n('search') >= 5",
                              "text": "Do not give up yet: try other searches."})

    class Client:
        n = 0

        def chat(self, msgs, tag="", **kw):
            Client.n += 1
            assert "0 of 1" in msgs[0]["content"]
            return SimpleNamespace(content='{"precondition": "answer_hedged and n(\'search\') >= 1"}')
    with tempfile.TemporaryDirectory() as ws:
        m2, pc = B.precheck_revise(Client(), "toy", m, "hedged_answer", None, fails, cur, sigs, {"t1": 0, "t2": 1},
                                   lint, "finish", 1, Path(ws))
    assert Client.n == 1 and pc["pred_fail"] == 1 and pc["pred_ok"] == 0 and pc["before"]["pred_fail"] == 0
    assert m2["precondition"].startswith("(answer_hedged and n('search') >= 1)") or "n('search') >= 1" in m2["precondition"]
    assert pc["pred_tasks"] == ["t1"]


def test_linter_covers_llm_check():
    lint = B.Linter(["what is the name of the river that flows through the old town"], ["task_42"], {"search"})
    m = R.validate_mechanism({"kind": "inject", "text": "Check the evidence again.",
                              "llm_check": "Is the name of the river that flows through the old town known?"})
    assert lint.check(m) and "copies task text" in lint.check(m)


if __name__ == "__main__":
    fns = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for f in fns:
        f()
        print("ok", f.__name__)
    print(f"{len(fns)} passed")
