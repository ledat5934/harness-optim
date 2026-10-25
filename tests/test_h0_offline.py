"""Offline H0 checks (no network, no spend): registry, compose, loop control flow, verifier reject path."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.common import StepResult, TaskSpec, run_with_env  # noqa: E402
from h0.compose import DEFAULT_BUNDLE, LazyHarness, compose, get_registry, validate_bundle  # noqa: E402
from h0.protocols import SLOTS  # noqa: E402


class FakeResp:
    def __init__(self, content="", tool_calls=None):
        self.content, self.tool_calls = content, tool_calls or []
        self.prompt_tokens, self.completion_tokens, self.cost = 10, 5, 0.0


def tc(i, name, args):
    return {"id": f"c{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


class FakeLLM:
    def __init__(self, script):
        self.script, self.calls = list(script), []

    def chat(self, messages, tools=None, tag="", **kw):
        self.calls.append(messages)
        return self.script.pop(0)


class ToyEnv:
    """Counter env: `inc` adds 1; done when the counter hits 2 (no finish tool) or `finish` is called."""

    def __init__(self, finish_tool=""):
        self.n, self.finish_tool, self.answer = 0, finish_tool, None

    def reset(self):
        tools = [{"type": "function", "function": {"name": "inc", "description": "add 1",
                                                    "parameters": {"type": "object", "properties": {}}}}]
        if self.finish_tool:
            tools.append({"type": "function", "function": {"name": "finish", "description": "answer",
                                                            "parameters": {"type": "object", "properties": {"answer": {"type": "string"}}}}})
        return TaskSpec("t1", "toy", "Reach 2.", "n=0", tools, finish_tool=self.finish_tool, max_steps=6)

    def step(self, tool, args):
        if tool == "finish":
            self.answer = args.get("answer")
            return StepResult("ok", done=True)
        self.n += 1
        return StepResult(f"n={self.n}", done=(not self.finish_tool and self.n >= 2))

    def evaluate(self):
        return (self.n >= 2 and (not self.finish_tool or self.answer == "2")), {"n": self.n}

    def close(self):
        pass


def test_registry_and_compose():
    reg = get_registry()
    assert not reg.load_errors, reg.load_errors
    for s in SLOTS:
        assert reg.has(s, "default"), s
    h = compose(None)
    assert h.bundle == DEFAULT_BUNDLE
    try:
        validate_bundle({"memory": {"name": "nope"}}, reg)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_env_done_path():
    llm = FakeLLM([FakeResp("thinking", [tc(1, "inc", {})]), FakeResp("again", [tc(2, "inc", {})])])
    r = run_with_env("toy", "t1", lambda: ToyEnv(), LazyHarness(), llm, run_tag="test")
    assert r.success and r.steps == 2, r


def test_finish_reject_then_accept_and_text_fallback():
    llm = FakeLLM([
        FakeResp("", [tc(1, "inc", {})]),
        FakeResp('{"name": "inc", "arguments": {}}'),          # text-fallback tool call
        FakeResp("", [tc(3, "finish", {"answer": ""})]),        # rejected by verifier (empty)
        FakeResp("", [tc(4, "finish", {"answer": "2"})]),
    ])
    r = run_with_env("toy", "t1", lambda: ToyEnv("finish"), LazyHarness(), llm, run_tag="test")
    assert r.success, r
    traj = json.loads(Path(r.trajectory_path).read_text())
    assert any(e["type"] == "verifier_reject" for e in traj["events"])


def test_no_action_stops():
    llm = FakeLLM([FakeResp("hmm")] * 3)
    r = run_with_env("toy", "t1", lambda: ToyEnv(), LazyHarness(), llm, run_tag="test")
    assert not r.success and r.extra["llm_calls"] == 3


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
