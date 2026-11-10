"""Offline tests of the B4 v7 loop pieces (no LLM calls, no benchmark). Run: python tests/test_b4_comp.py"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import test_b4_diff as T  # noqa: E402
from baselines import b4_branch as V  # noqa: E402
from baselines import b4_comp as M  # noqa: E402
from baselines import b4_repertoire as B  # noqa: E402
from baselines import common as C  # noqa: E402

LINTER = B.Linter(["find the person who founded the old company in the north"], ["task_alpha"], {"look", "read", "finish"})


def test_metric_whitelist():
    f = {"steps": 6, "n_actions": 5, "distinct_actions": 4, "_tools": {"look": 3}}
    assert M.metric(M.compile_metric("n_actions - distinct_actions"), f) == 1.0
    assert M.metric(M.compile_metric("n('look') / max(1, steps)"), f) == 0.5
    for bad in ("__import__('os')", "steps.real", "unknown_feature + 1", "[1][0]", ""):
        try:
            M.compile_metric(bad)
            raise AssertionError(bad)
        except (ValueError, SyntaxError):
            pass


def test_observe_compares_runs_of_the_same_task():
    recs, feats = [], {}
    # task a: the successful run took more steps; task b: both failed (carries no information); task c: opposite
    for i, (tid, ok, steps) in enumerate([("a", True, 9), ("a", False, 4), ("b", False, 20), ("b", False, 2),
                                          ("c", True, 3), ("c", False, 5), ("d", True, 8), ("d", False, 4)]):
        recs.append({"task_id": tid, "success": ok, "trajectory_path": str(i)})
        feats[str(i)] = {"steps": steps}
    o = M.observe(M.compile_metric("steps"), "up", recs, feats)
    assert (o["mixed_tasks"], o["agree"], o["disagree"]) == (3, 2, 1) and o["score"] > 0
    assert M.observe(M.compile_metric("steps"), "down", recs, feats)["score"] < 0


def test_lint_rejects_task_specific_and_prompt_code():
    ok = "import re\nclass X:\n    def f(self, task):\n        return [t['function']['name'] for t in task.tools]\n"
    assert M.lint_code(ok, LINTER, ["toy"]) is None
    assert "tool name" in M.lint_code("NAME = 'look'\n", LINTER, ["toybench"])
    assert M.lint_code("NAME = 'look'\n", LINTER, ["toybench"], known={"look"}) is None
    assert "import" in M.lint_code("import os\n", LINTER, ["toybench"])
    assert "prompt edit" in M.lint_code(f"ADVICE = '{'a ' * 300}'\n", LINTER, ["toybench"])
    assert "benchmark" in M.lint_code("# tuned for toybench\nx = 1\n", LINTER, ["toybench"])
    assert "task text" in M.lint_code("x = 'the person who founded the old company'\n", LINTER, ["toybench"])
    assert "evaluate" in M.lint_code("def f(env):\n    return env.evaluate()\n", LINTER, ["toybench"])
    assert M.lint_code('"""' + "doc " * 200 + '"""\nx = 1\n', LINTER, ["toybench"]) is None  # docstrings are not prompts


def test_refuted_behaviour_is_not_proposed_again():
    h = {"name": "More Steps!", "slot": "verifier", "direction": "up", "behaviour": "steps",
         "hypothesis": "If the agent takes more steps it succeeds more often.", "mechanism": "refuse -> continue " * 3}
    c = M.validate_hyp(h, [])
    assert c["name"] == "more_steps" and c["slot"] == "verifier"
    led = [{**c, "round": 1, "verdict": "REFUTED: behaviour changed as predicted, success did not"}]
    for bad in (h, {**h, "slot": "memory"}, {**h, "behaviour": "os.system"}, {**h, "direction": "sideways"}):
        try:
            M.validate_hyp(bad, led)
            raise AssertionError(bad)
        except (ValueError, SyntaxError):
            pass
    assert M.validate_hyp({**h, "direction": "down"}, led)["direction"] == "down"


class Client:
    """Proposer calls return a component file; agent calls read one item after a refused answer, then answer B."""
    model = "fake"

    def __init__(self, body_for):
        self.body_for, self.impl, self.agent = body_for, 0, 0

    def chat(self, msgs, tools=None, tag="", **kw):
        if str(tag).startswith("b4:"):
            self.impl += 1
            prompt = msgs[0]["content"]
            vname = prompt.split("### FILE: variants/verifier/")[-1].split(".py")[0]
            return SimpleNamespace(content=f"### FILE: variants/verifier/{vname}.py\n```python\n"
                                           f"{self.body_for(vname, self.impl)}\n```")
        self.agent += 1
        read = any(tc["function"]["name"] == "read" for m in msgs for tc in m.get("tool_calls") or [])
        tcs = T._tc(self.agent + 10, "finish", {"answer": "B"}) if read else T._tc(self.agent + 10, "read", {"key": "k1"})
        return SimpleNamespace(content="", tool_calls=tcs, prompt_tokens=5, completion_tokens=1, cost=0.0)


def _cand():
    return {"id": "c1", "name": "unread", "vname": "c1_unread", "slot": "verifier", "edit_type": "acceptance",
            "failure_mode": "early answer", "direction": "up", "behaviour": "steps", "observational": {},
            "hypothesis": "If the agent reads an item in full before answering it succeeds more often.",
            "mechanism": "first answer while a reading tool was never used -> refuse once"}


def _trial(tmp, src, client):
    return M.trial(client, "toy", None, _cand(), C.H0_ROOT, [src], tmp / "ws", tmp / "out.jsonl", LINTER,
                   {"workers": 1}, random.Random(0), "finish", lambda p: M.features(p, "finish"), 1)


def test_trial_supported_candidate():
    tmp, src = T._setup()
    M.C.RUNS = tmp / "runs"
    M.SHIFT_MARGIN, M.SHIFT_ALPHA = 1, 1.0
    good = (T.VARIANTS / "verifier" / "unread_items.py").read_text()
    row = _trial(tmp, src, Client(lambda v, i: good.replace('"unread_items"', f'"{v}"')))
    assert row["status"] == "admitted" and row["verdict"].startswith("SUPPORTED"), row["verdict"]
    assert row["coverage"] == 1.0 and row["shift"]["shifted"] and row["shift"]["before"] == 2.0
    assert row["outcome"]["W"] == 2 and row["outcome"]["Wt"] == 2 and len(row["_recs"]) == 2
    assert "_root" not in M.public(row)
    M.SHIFT_MARGIN, M.SHIFT_ALPHA = 3, 0.1


def test_trial_dead_code_then_repair():
    tmp, src = T._setup()
    M.C.RUNS = tmp / "runs"
    good = (T.VARIANTS / "verifier" / "unread_items.py").read_text()
    dead = good.replace("min_left: int = 3", "min_left: int = 99")  # the condition can never hold
    client = Client(lambda v, i: (dead if i == 1 else good).replace('"unread_items"', f'"{v}"'))
    row = _trial(tmp, src, client)
    # attempt 1 changes no saved run -> repaired; the probe has one branch only: no measurable shift -> one
    # revision -> still one branch -> INEFFECTIVE (the hypothesis is not marked refuted)
    assert client.impl == 3 and row["verdict"].startswith("INEFFECTIVE"), (client.impl, row["verdict"])
    tmp, src = T._setup()  # a fresh workspace: harness roots are cached by path
    M.C.RUNS = tmp / "runs"
    always_dead = Client(lambda v, i: dead.replace('"unread_items"', f'"{v}"'))
    row = _trial(tmp, src, always_dead)
    assert row["verdict"].startswith("DEAD CODE") and always_dead.agent == 0, row["verdict"]


def test_trial_lint_feedback_reaches_the_proposer():
    tmp, src = T._setup()
    M.C.RUNS = tmp / "runs"
    good = (T.VARIANTS / "verifier" / "unread_items.py").read_text()
    seen = []

    class Spy(Client):
        def chat(self, msgs, tools=None, tag="", **kw):
            if str(tag).startswith("b4:"):
                seen.append(msgs[0]["content"])
            return super().chat(msgs, tools=tools, tag=tag, **kw)
    bad = good.replace("from h0.protocols import Verdict", "from h0.protocols import Verdict\nREAD = 'read'")
    _trial(tmp, src, Spy(lambda v, i: (bad if i == 1 else good).replace('"unread_items"', f'"{v}"')))
    assert "previous attempt was rejected" not in seen[0] and "hardcoded tool name" in seen[1]


def test_pooled_and_ledger_view():
    t = M.pooled({"W": 3, "L": 0, "n": 40, "Wt": 1, "Lt": 0}, {"W": 1, "L": 1, "n": 10, "Wt": 0, "Lt": 0})
    assert (t["W"], t["L"], t["n"]) == (4, 1, 50) and t["p"] == round(V.sign_p(4, 1), 4)
    row = {**_cand(), "round": 2, "coverage": 0.7, "verdict": "REFUTED: x",
           "shift": {"before": 5, "after": 9, "as_predicted": 12, "opposite": 1, "n": 16}, "outcome": {"W": 1, "L": 1, "n": 32}}
    v = M.ledger_view([row])
    assert "REFUTED" in v and "5 -> 9" in v and "1 wins / 1 losses of 32" in v and M.ledger_view([]).startswith("(empty")


if __name__ == "__main__":
    fns = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for f in fns:
        f()
        print("ok", f.__name__)
    print(f"{len(fns)} passed")
