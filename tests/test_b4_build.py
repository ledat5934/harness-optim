"""B4 v7: code-writing feedback (line trace of an edit that changed nothing), merge rule, composition of edits."""
import json
from pathlib import Path

from baselines import b4_comp as M
from baselines import common as C

SRC = '''class V:
    def check(self, x):
        if x is None:
            return 0
        if x > 100:
            y = x * 2
            return y
        return x

    def unused(self):
        return 1


def register(reg):
    reg.register("verifier", "v", lambda c: V(), "d")
'''


def test_trace_reports_dead_branch_and_uncalled_function():
    t = M.trace_report(SRC, {2, 3, 5, 8}, 4)
    assert "functions never called: unused" in t
    assert "L5: if x > 100:   [ran]" in t and "L6: y = x * 2   [NEVER ran]" in t
    assert "L4" not in t  # an early exit not taken is not reported
    assert "functions never called: unused (" in t  # register() itself is not listed


def test_trace_keeps_only_the_edit_own_dead_branches():
    src = SRC.replace("        return x\n", "        if x < 0:\n            x = -x\n        return x\n")
    base = {ln.strip() for ln in SRC.splitlines()}
    t = M.trace_report(src, {2, 3, 5, 8, 10}, 4, base)
    assert "if x < 0:" in t and "x = -x" in t and "y = x * 2" not in t


def test_trace_all_lines_ran():
    t = M.trace_report(SRC, {2, 3, 4, 5, 6, 7, 8, 11}, 4)
    assert "every statement ran" in t


def test_trace_empty_when_nothing_was_traced():
    assert M.trace_report(SRC, set(), 4) == ""
    assert M.trace_report("def broken(:", {1}, 4) == ""


def _t(w, l, n=64):
    return {"W": w, "L": l, "n": n, "Wt": w, "Lt": l, "p": 1.0}


def test_merge_rule_needs_pooled_sign_test():
    assert not M.merge_ok(_t(2, 0), _t(1, 0))   # 3/0: p = 0.125, terminal forks do not exempt it
    assert M.merge_ok(_t(3, 0), _t(3, 1))       # 6/1: p = 0.0625
    assert M.merge_ok(_t(4, 0), _t(3, 0))
    assert not M.merge_ok(_t(6, 0), _t(0, 1))   # held-out runs contradict
    assert not M.merge_ok(_t(4, 3), _t(4, 2))   # 8/5


def test_compose_places_an_edit_on_a_new_incumbent(tmp_path: Path):
    inc = C.new_candidate(tmp_path / "inc", C.H0_ROOT)       # incumbent after a merge in tool_policy
    b = M.root_bundle_raw(C.H0_ROOT)
    default = (C.H0_ROOT / "variants" / "tool_policy" / "default.py").read_text(encoding="utf-8")
    (inc / "variants" / "tool_policy" / "m1.py").write_text(default.replace('"default"', '"m1"'), encoding="utf-8")
    (inc / "bundle.json").write_text(json.dumps({**b, "tool_policy": {"name": "m1", "config": {}}}), encoding="utf-8")
    cand = C.new_candidate(tmp_path / "cand", C.H0_ROOT)     # candidate built on H0, in verifier
    vdef = (C.H0_ROOT / "variants" / "verifier" / "default.py").read_text(encoding="utf-8")
    (cand / "variants" / "verifier" / "c9_x.py").write_text(vdef.replace('"default"', '"c9_x"'), encoding="utf-8")
    row = {"id": "c9", "slot": "verifier", "variant": "c9_x", "_parent": C.H0_ROOT}
    got = M.compose(cand, row, inc, tmp_path / "out")
    if '"default"' not in default or '"default"' not in vdef:  # H0 registers its variants another way: skip
        return
    assert got is not None
    nb = M.root_bundle_raw(got)
    assert nb["verifier"]["name"] == "c9_x" and nb["tool_policy"]["name"] == "m1"
    assert (got / "variants" / "tool_policy" / "m1.py").exists()
    # same slot as the merged edit: cannot be composed
    assert M.compose(cand, {**row, "slot": "tool_policy", "variant": "c9_x"}, inc, tmp_path / "out2") is None


def test_long_regex_is_not_a_prompt_edit():
    from baselines import b4_repertoire as B
    lint = B.Linter([], [], set())
    alt = "|".join(f"(?:word{chr(97 + i % 26)}+\\s+other)" for i in range(40))
    assert len(alt) > M.MAX_LITERAL
    assert M.lint_code(f"import re\nP = re.compile(r\"{alt}\")\n", lint, ["zzbench"]) is None
    assert "limit" in M.lint_code(f"TEXT = \"{'advice ' * 80}\"\n", lint, ["zzbench"])


def _traj(tmp, name, steps, max_steps=10):
    ev = [{"type": "task", "instruction": "q", "max_steps": max_steps}]
    for i, (tool, args, obs) in enumerate(steps):
        ev += [{"type": "llm", "content": "t", "tool_calls": [1], "step": i},
               {"type": "step", "n": i + 1, "tool": tool, "args": args, "observation": obs}]
    p = tmp / f"{name}.json"
    p.write_text(json.dumps({"events": ev}))
    return str(p)


def test_precondition_is_measured_on_saved_steps(tmp_path):
    a = _traj(tmp_path, "a", [("look", {"q": "x"}, "r" * 50), ("look", {"q": "x"}, "r" * 50),
                              ("done", {"answer": "I could not determine the answer"}, "ok")])
    b = _traj(tmp_path, "b", [("look", {"q": "y"}, "s" * 900), ("read", {"id": 1}, "Error: not found")])
    recs = [{"trajectory_path": a, "success": False, "task_id": "1"}, {"trajectory_path": b, "success": True, "task_id": "2"}]
    rows = {x["trajectory_path"]: M.step_rows(x["trajectory_path"], "done") for x in recs}
    ra, rb = rows[a], rows[b]
    assert [f["is_repeat"] for f in ra] == [0, 1, 0] and ra[1]["dup_result"] == 1 and ra[1]["same_tool_run"] == 2
    assert ra[2]["is_finish"] and ra[2]["answer_hedged"] and ra[2]["is_last"] and not ra[1]["is_last"]
    assert rb[1]["is_error"] and rb[1]["new_tool"] and rb[1]["tools_so_far"] == 2 and rb[0]["history_chars"] == 900
    assert all(f["no_call_replies"] == 0 and f["refused_calls"] == 0 for f in ra + rb)
    w = M.when(M.compile_when("is_repeat and result_chars < 100"), recs, rows.get)
    assert (w["runs"], w["steps"], w["n_steps"], w["in_failed"], w["in_success"], w["first_step"]) == (1, 1, 5, 1.0, 0.0, 2)
    assert M.when(M.compile_when("is_last and not is_finish"), recs, rows.get)["runs"] == 1
    assert "is_repeat: true at 1 of 5 calls, in 1 of 2 runs" in M.step_facts(recs, rows.get)


def test_hypothesis_without_a_real_situation_is_rejected_before_code(tmp_path):
    a = _traj(tmp_path, "a", [("look", {"q": "x"}, "r" * 50), ("done", {"answer": "v"}, "ok")])
    recs = [{"trajectory_path": a, "success": i % 2 == 0, "task_id": str(i)} for i in range(40)]
    rows = lambda p: M.step_rows(p, "done")  # noqa: E731
    h = {"name": "n", "slot": "verifier", "behaviour": "steps", "direction": "up", "hypothesis": "If the agent " * 3,
         "mechanism": "precondition -> action " * 2}
    for bad, msg in (({}, "`when` is missing"), ({"when": "is_error and step > 1"}, "holds at 0 of 80 executed calls")):
        try:
            M.check_when(M.validate_hyp({**h, **bad}, []), recs, rows)
            raise AssertionError("accepted")
        except ValueError as e:
            assert msg in str(e), str(e)
    for bad in ("n('look') > 1", "steps > 3", "open('x')"):  # run-level names and calls are not step-level
        try:
            M.validate_hyp({**h, "when": bad}, [])
            raise AssertionError("accepted " + bad)
        except ValueError:
            pass
    c = M.validate_hyp({**h, "when": "is_finish and answer_len < 5"}, [])
    assert M.check_when(c, recs, rows)["runs"] == 40 and c["when_obs"]["in_failed"] == 1.0
    assert "precondition: `is_finish and answer_len < 5` holds at 40 of 80" in M.ledger_view(
        [{**c, "round": 1, "verdict": "INCONCLUSIVE"}])


def test_refused_calls_are_not_replies_without_a_call(tmp_path):
    ev = [{"type": "task", "instruction": "q", "max_steps": 10},
          {"type": "llm", "content": "", "tool_calls": [1], "step": 0},
          {"type": "step", "n": 1, "tool": "look", "args": {}, "observation": "r"},
          {"type": "llm", "content": "", "tool_calls": [1], "step": 1},   # a final answer the harness refused
          {"type": "llm", "content": "thinking", "tool_calls": [], "step": 2},
          {"type": "llm", "content": "", "tool_calls": [1], "step": 3},
          {"type": "step", "n": 2, "tool": "done", "args": {"answer": "v"}, "observation": "ok"}]
    p = tmp_path / "t.json"
    p.write_text(json.dumps({"events": ev}))
    r = M.step_rows(str(p), "done")
    assert (r[1]["refused_calls"], r[1]["no_call_replies"]) == (1, 1) and r[0]["refused_calls"] == 0


def test_a_number_in_a_string_names_the_constant_and_spares_inherited_ones():
    lin = M.B.Linter([], [], set())
    src = 'X = "default 2048"\n\ndef register(reg):\n    pass\n'
    assert "'default 2048'" in M.lint_code(src, lin, ["b"])
    assert M.lint_code(src, lin, ["b"], known={"default 2048"}) is None


def test_served_responses_keep_their_tokens():
    from baselines import b4_diff as D
    r = D._saved({"content": "c", "tool_calls": [], "pt": 120, "ct": 30})
    assert (r.prompt_tokens, r.completion_tokens, r.cost) == (120, 30, 0.0)


def test_a_number_in_the_registration_description_is_not_a_literal():
    lin = M.B.Linter([], [], set())
    src = 'def register(reg):\n    reg.register("verifier", "v", lambda c: 1, "keeps results under 8000 chars")\n'
    assert M.lint_code(src, lin, ["zzbench"]) is None
    assert M.lint_code('X = "under 8000 chars"\n' + src, lin, ["zzbench"]) is not None


def test_hypotheses_about_failed_runs_get_code_first():
    obs = {"agree": 0, "disagree": 0}
    hyps = [{"observational": obs, "when_obs": {"in_failed": 1.0, "in_success": 1.0}},
            {"observational": obs, "when_obs": {"in_failed": 0.03, "in_success": 0.45}},
            {"observational": obs, "when_obs": {"in_failed": 0.88, "in_success": 0.0}},
            {"observational": obs}]
    assert M.select(hyps) == [2, 0, 3, 1]
    assert M.when_disc({"in_failed": None, "in_success": 0.5}) == 0.0


def test_an_edit_narrower_than_its_precondition_is_sent_back():
    w = {"runs": 106, "n_runs": 150, "steps": 106, "n_steps": 700, "in_failed": 0.88, "in_success": 0.0, "first_step": 5}
    cand = {"when": "is_finish == 1 and answer_hedged == 1", "when_obs": w}
    why = M.reach_gap(cand, {"touched": 18, "n": 150})
    assert "18 of 150" in why and "answer_hedged: " in why and "is_finish: " in why and "is_last" not in why
    assert M.reach_gap(cand, {"touched": 60, "n": 150}) == ""
    assert M.reach_gap({"when": "step >= 1"}, {"touched": 1, "n": 150}) == ""
