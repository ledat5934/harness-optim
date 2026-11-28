"""Offline tests of B4 v7 divergence-point branching (no LLM calls, no benchmark). Run: python tests/test_b4_diff.py"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import benchmarks.common as BC  # noqa: E402
from baselines import b4_diff as D  # noqa: E402
from baselines import common as C  # noqa: E402
from benchmarks.common import StepResult, TaskSpec, run_with_env  # noqa: E402

VARIANTS = Path(__file__).resolve().parents[1] / "baselines" / "b4_variants"
LONG = "x" * 3000


def _tc(i, name, args):
    return [{"id": f"c{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]


def _tool(name, param):
    return {"type": "function", "function": {"name": name, "description": name, "parameters": {
        "type": "object", "properties": {param: {"type": "string"}}, "required": [param]}}}


class Env:
    """`look(q)` returns 4 long records, `read(key)` one record in full, `finish(answer)` ends. Correct = 'B'."""

    def __init__(self):
        self.answer = None

    def reset(self):
        return TaskSpec("t1", "toy", "Find it.", "", [_tool("look", "q"), _tool("read", "key"),
                                                      _tool("finish", "answer")], finish_tool="finish", max_steps=8)

    def step(self, tool, args):
        if tool == "look":
            return StepResult(json.dumps([{"key": f"k{i}", "body": LONG + f" item{i}"} for i in range(4)]))
        if tool == "read":
            return StepResult(json.dumps({"key": args.get("key"), "body": "short"}))
        self.answer = args.get("answer")
        return StepResult("ok", done=True)

    def evaluate(self):
        return self.answer == "B", {}

    def close(self):
        pass


class Script:
    model = "fake"

    def __init__(self, script):
        self.script, self.n = list(script), 0

    def chat(self, msgs, tools=None, tag="", **kw):
        self.n += 1
        tcs = self.script.pop(0)
        return SimpleNamespace(content="", tool_calls=tcs, prompt_tokens=5, completion_tokens=1, cost=0.0)


class Adapter:
    @staticmethod
    def run_episode(task_id, harness, llm, split=None, run_tag="adhoc", max_steps=None):
        return run_with_env("toy", task_id, Env, harness, llm, run_tag=run_tag)


def _setup():
    tmp = Path(tempfile.mkdtemp())
    BC.TRAJ_DIR = tmp / "traj"
    C.adapter = lambda bench: Adapter
    src = Adapter.run_episode("t1", C.LazyHarness(C.H0_ROOT),
                              Script([_tc(1, "look", {"q": "a"}), _tc(2, "finish", {"answer": "A"})]), run_tag="h0")
    assert not src.error and not src.success
    return tmp, {"task_id": "t1", "success": src.success, "trajectory_path": src.trajectory_path}


def _root(tmp, slot, name, cfg=None):
    root = C.new_candidate(tmp / f"root_{name}", C.H0_ROOT)
    shutil.copy2(VARIANTS / slot / f"{name}.py", root / "variants" / slot / f"{name}.py")
    (root / "bundle.json").write_text(json.dumps({slot: {"name": name, "config": cfg or {}}}))
    return root


def test_unchanged_harness_is_the_saved_run():
    tmp, src = _setup()
    live = Script([])
    rec = D.run_diff("toy", None, [src], C.H0_ROOT, C.H0_ROOT, live, "t", None, tmp / "ref")[0]
    assert not rec["branched"] and rec["success"] is False and live.n == 0 and not rec["error"]
    assert D.divergence_map([rec])["touched"] == 0


def test_observation_edit_diverges_at_the_next_request():
    tmp, src = _setup()
    root = _root(tmp, "tool_policy", "fit_items")
    dry = D.run_diff("toy", None, [src], root, C.H0_ROOT, Script([]), "t", None, tmp / "ref", dry=True)[0]
    assert dry["branched"] and dry["fork_call"] == 1 and not dry["terminal"] and not dry["error"]
    live = Script([_tc(3, "finish", {"answer": "B"})])
    rec = D.run_diff("toy", None, [src], root, C.H0_ROOT, live, "t", None, tmp / "ref")[0]
    assert rec["branched"] and rec["success"] and live.n == 1
    est = D.estimate([src], [rec])
    assert est["gain"] == 1.0 and est["branch"]["W"] == 1 and est["branch"]["Wt"] == 0


def test_verifier_edit_is_a_terminal_divergence():
    tmp, src = _setup()
    root = _root(tmp, "verifier", "unread_items")
    live = Script([_tc(3, "read", {"key": "k1"}), _tc(4, "finish", {"answer": "B"})])
    rec = D.run_diff("toy", None, [src], root, C.H0_ROOT, live, "t", None, tmp / "ref")[0]
    assert rec["branched"] and rec["terminal"] and rec["fork_call"] == 2 and rec["success"] and live.n == 2
    assert D.estimate([src], [rec])["branch"]["Wt"] == 1


def test_fit_items_keeps_every_record():
    sys.path.insert(0, str(VARIANTS / "tool_policy"))
    import fit_items as F
    base = SimpleNamespace(format_observation=lambda a, r, t: "DEFAULT")
    task = Env().reset()
    act = SimpleNamespace(tool="look", args={"q": "a"})
    obs = Env().step("look", {}).observation
    out = F.FitItems(base, max_obs_chars=2000, hint=True).format_observation(act, StepResult(obs), task)
    assert len(out) <= 2000 and all(f'"k{i}"' in out for i in range(4)) and "`read`" in out and "`key`" in out
    assert F.FitItems(base).format_observation(act, StepResult("short"), task) == "DEFAULT"
    assert F.FitItems(base, max_obs_chars=100).format_observation(act, StepResult("y" * 500), task) == "DEFAULT"


if __name__ == "__main__":
    fns = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for f in fns:
        f()
        print("ok", f.__name__)
    print(f"{len(fns)} passed")
