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
