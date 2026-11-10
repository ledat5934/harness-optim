"""Offline tests of B4 v6 trigger-point branching (no LLM calls, no benchmark). Run: python tests/test_b4_branch.py"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from baselines import b4_branch as V  # noqa: E402
from baselines.hg import runtime as R  # noqa: E402
from h0.protocols import Action, Verdict  # noqa: E402


def _tc(name, args):
    import json
    return [{"id": "c1", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]


class _Real:
    """The live model: always searches once more, then answers 'Paris'."""
    model = "fake"

    def __init__(self):
        self.calls = 0

    def chat(self, msgs, tools=None, tag="", **kw):
        self.calls += 1
        tc = _tc("search", {"q": "live"}) if self.calls == 1 else _tc("finish", {"answer": "Paris"})
        return SimpleNamespace(content="", tool_calls=tc, prompt_tokens=7, completion_tokens=1, cost=0.0)


class _Rec:
    def __init__(self):
        self.events = []

    def llm(self, resp, **kw):
        self.events.append({"type": "llm", "content": resp.content, "tool_calls": resp.tool_calls, **kw})

    def note(self, kind, **kw):
        self.events.append({"type": kind, **kw})

    def step(self, tool, args, obs, **kw):
        self.events.append({"type": "step", "tool": tool, "args": args, "observation": obs})


def _harness():
    def parse(resp, t):
        import json
        return [Action(c["function"]["name"], json.loads(c["function"]["arguments"]), call_id=c["id"],
                       raw={"function": c["function"]}) for c in resp.tool_calls]
    return SimpleNamespace(
        system_prompt="sys", memory=SimpleNamespace(recall=lambda t: None),
        context_mgmt=SimpleNamespace(build=lambda s, t, hist, n: [{"role": "system", "content": s}] + hist),
        verifier=SimpleNamespace(check=lambda *a, **k: Verdict(True)),
        tool_policy=SimpleNamespace(
            tools=lambda t: [{"type": "function", "function": {"name": n}} for n in ("search", "finish")],
            parse=parse, format_observation=lambda a, sr, t: sr.observation))


SAVED = [{"type": "llm", "content": "", "tool_calls": _tc("search", {"q": "a"}), "step": 0},
         {"type": "llm", "content": "", "tool_calls": _tc("search", {"q": "b"}), "step": 1},
         {"type": "llm", "content": "", "tool_calls": _tc("finish", {"answer": "unknown"}), "step": 2}]


def _run(mechs, branch_ids, live_at=None):
    task = SimpleNamespace(max_steps=8, finish_tool="finish", instruction="Find the city.", initial_observation="",
                           benchmark="toy")
    env = SimpleNamespace(step=lambda tool, args: SimpleNamespace(observation="doc", done=False))
    real, rec = _Real(), _Rec()
    bl = V.BranchLLM(real, SAVED, branch_ids, live_at)
    out = R.HookedLoop(mechs).run(task, env, _harness(), bl, rec)
    return out, bl, real, rec


def test_replay_without_fire_is_the_saved_run():
    m = {"id": "m1", "kind": "inject", "precondition": "n('search') >= 5", "text": "Try another way to search."}
    out, bl, real, rec = _run([m], {"m1"})
    assert real.calls == 0 and not bl.live and not bl.fired and bl.i == 3
    assert out.final_answer == "unknown"


def test_reject_finish_branches_after_the_saved_answer():
    m = {"id": "m1", "kind": "reject_finish", "precondition": "answer_hedged and n('search') >= 2",
         "text": "Do not give up yet: search again."}
    out, bl, real, rec = _run([m], {"m1"})
    assert bl.fired and bl.fork_call == 3 and real.calls == 2  # the whole saved run is the prefix
    assert out.final_answer == "Paris"
    assert [e["tool"] for e in rec.events if e["type"] == "step"] == ["search", "search", "search", "finish"]


def test_inject_branches_before_the_call_it_changes():
    m = {"id": "m1", "kind": "inject", "precondition": "n('search') >= 1", "text": "Open a document before searching."}
    out, bl, real, rec = _run([m], {"m1"})
    assert bl.fork_call == 1 and real.calls == 2 and out.final_answer == "Paris"


def test_mechanism_already_in_the_harness_does_not_branch():
    old = {"id": "m0", "kind": "inject", "precondition": "n('search') >= 1", "text": "Open a document before searching."}
    out, bl, real, rec = _run([old], {"m9"})
    assert real.calls == 0 and not bl.live and any(e["type"] == "mech" for e in rec.events)


def test_live_at_forks_the_control_arm():
    out, bl, real, rec = _run([], set(), live_at=1)
    assert bl.fork_call == 1 and real.calls == 2 and not bl.fired


def test_tally_and_sign_test():
    recs = [{"branched": True, "success": True, "src_success": False}] * 4 + \
           [{"branched": True, "success": False, "src_success": True}] + \
           [{"branched": False, "success": True, "src_success": True}] * 5 + \
           [{"branched": True, "success": False, "src_success": False}] * 3
    t = V.tally(recs)
    assert (t["W"], t["L"], t["n"], t["ran"]) == (4, 1, 8, 13)
    assert abs(V.sign_p(4, 1) - 6 / 32) < 1e-9 and V.sign_p(3, 0) == 0.125 and V.sign_p(0, 0) == 1.0


if __name__ == "__main__":
    fns = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for f in fns:
        f()
        print("ok", f.__name__)
    print(f"{len(fns)} passed")
