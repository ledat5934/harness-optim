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
    assert row["verdict"].startswith("SUPPORTED") and row["status"] == "rejected", row["verdict"]  # not yet reviewed
    feats = lambda p: M.features(p, "finish")  # noqa: E731
    assert row["effects"]["steps"]["up"] == 2 and "steps: 2.0 -> " in M.effects_view(row["effects"], only_clear=False)
    # the review chooses, the measurements bound it: success needs reliable wins, another benefit its claimed effect
    yes = {"decision": "adopt", "benefit": "success", "reason": "wins"}
    assert M.apply_review(dict(row), yes, feats)["status"] == "admitted"
    assert M.apply_review({**row, "outcome": {**row["outcome"], "W": 1, "Wt": 0, "p": 0.5}}, yes, feats)["status"] == "rejected"
    eff = {"decision": "adopt", "benefit": "efficiency", "reason": "cheaper", "claim": {"behaviour": "steps", "direction": "up"}}
    got = M.apply_review(dict(row), eff, feats)
    assert got["status"] == "admitted" and got["basis"] == "efficiency" and got["claim_shift"]["shifted"]
    assert M.apply_review(dict(row), {**eff, "claim": {"behaviour": "steps", "direction": "down"}}, feats)["status"] == "rejected"
    assert M.apply_review(dict(row), {k: v for k, v in eff.items() if k != "claim"}, feats)["status"] == "rejected"
    no = M.apply_review(dict(row), {"decision": "reject", "benefit": "success", "reason": "too costly"}, feats)
    assert no["status"] == "rejected" and "too costly" in no["decision"]
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


def test_review_answer_is_normalised():
    row = {**_cand(), "round": 1, "coverage": 1.0, "verdict": "REFUTED: x", "effects": {},
           "shift": {"before": 5, "after": 9, "as_predicted": 12, "opposite": 1, "n": 16}, "outcome": {"W": 1, "L": 1, "n": 32, "p": 0.75}}

    def ask(answer):
        seen = []
        c = SimpleNamespace(chat=lambda msgs, **kw: (seen.append((msgs[0]["content"], kw.get("tag"))),
                                                     SimpleNamespace(content=json.dumps(answer)))[1])
        return M.review(c, "toy", row, "success rate 20%"), seen
    rv, seen = ask({"decision": "Adopt", "benefit": "Efficiency", "reason": "half the tokens",
                    "claim": {"behaviour": "tokens", "direction": "down"}})
    assert rv == {"decision": "adopt", "benefit": "efficiency", "reason": "half the tokens",
                  "claim": {"behaviour": "tokens", "direction": "down"}}
    assert seen[0][1] == "b4:toy:review" and "net change +0" in seen[0][0] and "30 ended like" in seen[0][0] and "success rate 20%" in seen[0][0]
    assert "claim" not in ask({"decision": "adopt", "benefit": "efficiency", "claim": {"behaviour": "os.x", "direction": "down"}})[0]
    assert ask({"nonsense": 1})[0]["decision"] == "reject"
    assert "another benefit (e.g. lower cost at equal success): possible" in seen[0][0] and "more successes: not possible" in seen[0][0]
    # three reviews, the most frequent decision wins; a tie goes to the cautious side
    answers = iter([{"decision": "adopt", "benefit": "efficiency", "claim": {"behaviour": "tokens", "direction": "down"}},
                    {"decision": "reject"}, {"decision": "adopt", "benefit": "efficiency"},
                    {"decision": "adopt", "benefit": "success"}, {"decision": "reject"}, {"decision": "revise", "revision": "x"}])
    c = SimpleNamespace(chat=lambda msgs, **kw: SimpleNamespace(content=json.dumps(next(answers))))
    rv = M.review_vote(c, "toy", row, "s", can_revise=True)
    assert rv["decision"] == "adopt" and rv["claim"]["behaviour"] == "tokens" and rv["votes"] == {"adopt": 2, "reject": 1}
    assert M.review_vote(c, "toy", row, "s", can_revise=True)["decision"] == "reject"


def test_select_keeps_proposer_order_unless_runs_speak_clearly():
    o = lambda a, d: {"observational": {"agree": a, "disagree": d}}  # noqa: E731
    assert M.select([o(2, 1), o(0, 3), o(3, 0), o(0, 0)]) == [2, 0, 3, 1]


def test_pooled_and_ledger_view():
    t = M.pooled({"W": 3, "L": 0, "n": 40, "Wt": 1, "Lt": 0}, {"W": 1, "L": 1, "n": 10, "Wt": 0, "Lt": 0})
    assert (t["W"], t["L"], t["n"]) == (4, 1, 50) and t["p"] == round(V.sign_p(4, 1), 4)
    row = {**_cand(), "round": 2, "coverage": 0.7, "verdict": "REFUTED: x",
           "shift": {"before": 5, "after": 9, "as_predicted": 12, "opposite": 1, "n": 16}, "outcome": {"W": 1, "L": 1, "n": 32}}
    row.update(effects={"tokens": {"before": 9.0, "after": 4.0, "up": 0, "down": 30, "n": 32, "clear": True}},
               decision="ADOPTED for efficiency (held-out runs agree): cheaper")
    v = M.ledger_view([row])
    assert "tokens: 9.0 -> 4.0" in v and "ADOPTED for efficiency" in v
    assert "REFUTED" in v and "5 -> 9" in v and "1 wins / 1 losses of 32" in v and M.ledger_view([]).startswith("(empty")


if __name__ == "__main__":
    fns = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for f in fns:
        f()
        print("ok", f.__name__)
    print(f"{len(fns)} passed")
