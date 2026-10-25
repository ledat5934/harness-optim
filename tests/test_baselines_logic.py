"""Offline tests for B2's ModularRSI wiring: router buckets, infra errors, contrast findings, verdict validation, lane
choice, reward-blind evidence and the vendored prompts (no API calls, no episodes).

  python tests/test_baselines_logic.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from baselines import common as C  # noqa: E402
from baselines.b2_modular import _blind_evidence, _finding, _instr, parse_verdict, to_summary  # noqa: E402
from baselines.vendor.modularrsi import prompts as P  # noqa: E402
from baselines.vendor.modularrsi import trajectory_analysis as TA  # noqa: E402
from baselines.vendor.modularrsi.router import Bucket, Ledger, RouterConfig, route_batch  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="b2test_"))


def traj(name: str, task: str, instr: str = "do it") -> str:
    p = TMP / f"{name}.json"
    p.write_text(json.dumps({"task_id": task, "success": True, "steps": 1, "tokens": 5, "events": [
        {"type": "task", "instruction": instr},
        {"type": "step", "n": 1, "tool": "act", "args": {"c": 1}, "observation": "ok"}]}), encoding="utf-8")
    return str(p)


def roll(tid, ok, steps=10, rep=0.0, error=None, idx=0):
    return {"task_id": tid, "success": ok, "steps": steps, "repeat_ratio": rep, "tokens": 5, "error": error,
            "trajectory_path": traj(f"{tid}_{idx}_{ok}_{steps}", tid, f"instr {tid}")}


def route(recs):
    summaries = [to_summary(r, i) for i, r in enumerate(recs)]
    rec_of = {s.trial_name: r for s, r in zip(summaries, recs)}
    return route_batch(summaries, ledger=Ledger(), epoch=0, cfg=RouterConfig(k=3), history_pass_lookup=None), rec_of


def test_route_buckets():
    recs = [roll("eff", True), roll("eff", True), roll("eff", True),
            roll("was", True, steps=40), roll("was", True, steps=35), roll("was", True, steps=50),
            roll("mix", True), roll("mix", False), roll("mix", True),
            roll("fail", False), roll("fail", False), roll("fail", False)]
    res, _ = route(recs)
    assert res.buckets[Bucket.ALL_PASS_EFFICIENT.value] == ["eff"]
    assert res.buckets[Bucket.ALL_PASS_WASTEFUL.value] == ["was"]
    assert res.buckets[Bucket.MIXED.value] == ["mix"]
    assert res.buckets[Bucket.FIXABLE_FAIL.value] == ["fail"]
    assert {d.task for d in res.diagnose} == {"mix", "fail"}
    assert {d.task for d in res.efficiency} == {"was"}  # wasteful passes get the efficiency investigator


def test_infra_error_is_not_a_fail():
    recs = [roll("inf", False, error="RuntimeError: endpoint down"), roll("inf", False, error="x"),
            roll("inf", False, error="y")]
    res, _ = route(recs)
    assert res.buckets["infra_only"] == ["inf"]
    assert not res.diagnose  # no verdict, so nothing to contrast
    assert to_summary(recs[0], 0).reward is None


def test_verdict_parsing():
    ok = '<review_verdict decision="accept" reason="targets a real failure mode"/>'
    assert parse_verdict(ok)["decision"] == "accept"
    rej = '<review_verdict decision="reject" reject_class="implementation" reason="bug" repair_brief="fix the loop"/>'
    v = parse_verdict(rej)
    assert v["decision"] == "reject" and v["reject_class"] == "implementation" and v["repair_brief"] == "fix the loop"
    # the quoted format-spec template must not count as a verdict
    tmpl = '<review_verdict decision="accept|reject" reject_class="proposal|implementation" reason="one sentence"/>'
    assert parse_verdict(tmpl) is None
    # accept must not carry a reject_class; reject must carry one
    assert parse_verdict('<review_verdict decision="accept" reject_class="proposal" reason="x"/>') is None
    assert parse_verdict('<review_verdict decision="reject" reason="x"/>') is None
    # the last valid verdict wins (the reviewer may resubmit)
    both = ('<review_verdict decision="reject" reject_class="proposal" reason="a"/>\n'
            '<review_verdict decision="accept" reason="b"/>')
    assert parse_verdict(both)["decision"] == "accept"


def test_finding_parsing_and_lanes():
    text = ('analysis...\n<contrast_finding>{"task": "t1", "is_culprit": true, "fixable_now": "true", '
            '"suggested_change": "retry with the failing state re-read"}</contrast_finding>')
    f = _finding(text, "agent_loop", "t1")
    assert f["is_culprit"] and f["fixable_now"] and f["slot"] == "agent_loop" and f["parse"] == TA.PARSE_OK
    # cut off before the closing tag: no verdict exists, so it must not count as a culprit
    g = _finding('{"is_culprit": true, "fixable_now": true, "mechanism": "needs a kernel change', "memory", "t2")
    assert g["parse"] == TA.PARSE_FAILED and g["is_culprit"] is False and g["fixable_now"] is False
    # a stray quote inside a string is salvaged key by key, labelled as a guess
    h = _finding('<contrast_finding>{"task": "t3", "is_culprit": true, "fixable_now": true, '
                 '"suggested_change": "say "hi" then retry"}</contrast_finding>', "tool_policy", "t3")
    assert h["parse"] in (TA.PARSE_OK, TA.PARSE_SALVAGED) and h["is_culprit"]


def test_blind_evidence_hides_outcomes():
    rolls = [roll("t1", False, idx=1), roll("t1", True, idx=2)]
    text = _blind_evidence([{"task": "t1", "fail": rolls[0], "pass": rolls[1], "rolls": rolls}])
    assert "PASS" not in text and "FAIL" not in text and "success=" not in text
    assert "ROLL 1" in text and "ROLL 2" in text


def test_summarize_hides_outcome_when_asked():
    p = traj("sum", "t", "do it")
    assert "success=True" in C.summarize_trajectory(p)
    assert "success=" not in C.summarize_trajectory(p, show_outcome=False)
    assert C.traj_stats(p) == {"steps": 1, "repeat_ratio": 0.0}
    assert _instr({"trajectory_path": p}) == "do it"


def test_vendored_prompts_are_clean():
    texts = {"contrast": P.CONTRAST_INVESTIGATION, "efficiency": P.EFFICIENCY_INVESTIGATION, "review": P.REVIEW}
    for name, t in texts.items():
        for bad in ("read_file", "task_complete", "MODULE TRACE", "tools/helpers", "edit any", "commit_patch"):
            assert bad not in t, (name, bad)
    # every placeholder the code fills must be present, and only those
    for key in ("{locked}", "{covers}", "{yardstick}", "{probes}", "{task}", "{pass_origin}", "{pass_block}",
                "{fail_block}", "{evidence_field}"):
        assert key in P.CONTRAST_INVESTIGATION, key
    assert "{diff_text}" in P.REVIEW and "{intent}" in P.REVIEW and "{trial_summaries}" in P.REVIEW
    assert "terminal coding agent" in P.composer_prompt("t", "c")
    assert TA._module_lens("verification")["covers"]  # lens lookup used by the investigator


def _b3_rec(tid, ok, instr, idx=0):
    return {"task_id": tid, "success": ok, "steps": 5, "tokens": 50, "error": None, "cost": 0.0,
            "trajectory_path": traj(f"b3_{tid}_{idx}_{ok}", tid, instr)}


def test_b3_config_mapping_matches_h0():
    from baselines import b3_memo as B3
    ctl = B3.ConfigController(client=B3.ChatShim(None, "x"), model=B3.MODEL, api_config=B3.API)
    base = B3.base_config(ctl)
    # H0 values for every mapped knob, and no strategy text (H0's loop has none)
    assert base.D5["history_keep"] == 30 and base.D3["max_tokens"] == 2048 and base.D3["temperature"] == 0.0
    assert all(getattr(base, d)["strategy"] == "" for d in B3.DIMS)
    b = B3.to_bundle(base)
    assert b["context_mgmt"]["config"] == {"keep_turns": 30, "extra_system": ""}
    assert b["agent_loop"]["config"] == {"temperature": 0.0, "max_tokens": 2048}
    cfg = base.clone()
    cfg.D1["strategy"] = "verify before finishing"
    cfg.D3["temperature"] = 9
    got = B3.to_bundle(B3.clamp(cfg))
    assert "verify before finishing" in got["context_mgmt"]["config"]["extra_system"]
    assert got["agent_loop"]["config"]["temperature"] == 1.0  # clamped to [0, 1]
    assert base.D3["temperature"] == 0.0  # the clone did not alias the base


def test_b3_bm25_similarity_and_freeze():
    from baselines import b3_memo as B3
    ctl = B3.ConfigController(client=B3.ChatShim(None, "x"), model=B3.MODEL, api_config=B3.API)
    base = B3.base_config(ctl)
    bank = B3.BM25ExperienceBank()
    instrs = ["find the red book on the shelf", "wash the dirty plate in the sink", "open the blue box"]
    for i, ins in enumerate(instrs):
        bank.add_entry(B3.to_entry(_b3_rec(f"c{i}", i % 2 == 0, ins, i), i, base, base, "alfworld"))
    q = B3._tok("find the red book")
    self_sim = bank._cosine_similarity(q, q)
    near, other = bank._cosine_similarity(q, B3._tok(instrs[0])), bank._cosine_similarity(q, B3._tok(instrs[1]))
    assert abs(self_sim - 1.0) < 1e-9 and 0.0 <= other < near < self_sim
    assert bank._cosine_similarity([], B3._tok(instrs[0])) == 0.0
    # the reference top-k logic: successes and failures come back separately
    case = B3.BenchmarkCase(case_id="q", prompt="find the red book", expected_output="",
                            features=B3.case_features("find the red book", "alfworld"))
    sim = bank.retrieve_similar_cases_for_case(case, top_k_success=5, top_k_failure=5)
    assert sim.successful[0].case_id == "c0" and all(e.diagnosis.success for e in sim.successful)
    assert all(not e.diagnosis.success for e in sim.failed)
    bank.frozen = True
    try:
        bank.add_entry(B3.to_entry(_b3_rec("late", True, "late"), 9, base, base, "alfworld"))
    except RuntimeError:
        pass
    else:
        raise AssertionError("frozen bank accepted an entry")


def test_b3_distill_trigger_is_the_reference_one():
    from baselines import b3_memo as B3
    ctl = B3.ConfigController(client=B3.ChatShim(None, "x"), model=B3.MODEL, api_config=B3.API)
    base = B3.base_config(ctl)
    bank = B3.BM25ExperienceBank()
    fired = [bank.add_entry(B3.to_entry(_b3_rec("hard", False, "hard task", i), i, base, base, "alfworld",
                                        {"primary_dim": "D3", "analysis": "x"})) for i in range(3)]
    assert fired == [False, False, True]  # MIN_CONSECUTIVE_FAILURES=3 fires on the third consecutive failure
    bank2 = B3.BM25ExperienceBank()
    for i in range(B3.EVERY_N_ENTRIES):
        bank2.add_entry(B3.to_entry(_b3_rec(f"e{i}", True, f"easy {i}", i), 0, base, base, "alfworld"))
    assert bank2.should_distill(B3.EVERY_N_ENTRIES)


def test_b3_canary_and_adaptation_defaults():
    from baselines import b3_memo as B3
    assert B3.CANARY_MIN_REWARD_DELTA == -0.34 and B3.CANARY_MAX_BLOCKER_INCREASE == 0
    assert B3.MIN_CONSECUTIVE_FAILURES == 3 and B3.MAX_PATTERNS == 3 and B3.EVERY_N_ENTRIES == 5
    assert B3.TEST_TIME_CASE_ADAPTATION is True
    assert B3.norm_dim("d3 generation") == "D3" and B3.norm_dim("nothing") is None


def test_b1_pass_rates_and_frontier_format():
    import tempfile as tf
    from baselines import b1_freeform as B1
    per_task, avg = B1.compute_pass_rates({"a": [1.0, 0.0], "b": [1.0]})
    assert per_task == {"a": 0.5, "b": 1.0} and abs(avg - 2 / 3) < 1e-9  # flat: total passes / total trials
    with tf.TemporaryDirectory() as d:
        fr = Path(d) / "frontier_val.json"
        B1.update_frontier(fr, {"h0": ({"a": 0.0, "b": 1.0}, 0.5)})
        B1.update_frontier(fr, {"r1": ({"a": 1.0, "b": 1.0}, 1.0), "r2": ({"a": 1.0, "b": 0.0}, 0.5)})
        got = json.loads(fr.read_text(encoding="utf-8"))
        assert got["a"] == {"best_agent": "r1", "pass_rate": 1.0}  # ties keep the earlier agent
        assert got["b"] == {"best_agent": "h0", "pass_rate": 1.0}
        assert got["_best"] == {"agent": "r1", "avg_pass_rate": 1.0}
        summary = Path(d) / "evolution_summary.jsonl"
        B1.update_evolution_summary(summary, fr, 1, [{"name": "r1", "hypothesis": "h", "changes": "c"}],
                                    {"r1": ({"a": 1.0}, 1.0)}, {"r1": {"n_trials": 1}})
        row = json.loads(summary.read_text(encoding="utf-8").strip())
        assert row["agent"] == "r1" and row["rollout_metrics"] == {"n_trials": 1} and row["outcome"].startswith("100.0%")


def test_b1_trial_metrics_and_skill_text():
    from baselines import b1_freeform as B1
    recs = [{"task_id": "t", "steps": 4, "tokens": 100, "cost": 0.01}, {"task_id": "t", "steps": 6, "tokens": 50, "cost": None}]
    m = B1.summarize_trial_metrics(B1.trial_metrics_of(recs))
    assert m["n_trials"] == 2 and m["mean_turns"] == 5.0 and m["total_input_tokens"] == 150
    assert m["total_output_tokens"] is None  # llm.py does not split input and output tokens
    # the reference SKILL.md wording that must survive the change
    for phrase in ("CRITICAL CONSTRAINTS", "Anti-overfitting rules", "Never mention task names", "Mechanism-first",
                   "One mechanism per candidate", "STATE:", "HYPOTHESIS:", "CANDIDATE:"):
        assert phrase in B1.SKILL, phrase
    assert "AgentHarness" not in B1.SKILL and "Terminal-Bench" not in B1.SKILL.replace("meta-harness-terminal-bench-2", "")



def test_b3_canary_rules_are_the_reference_ones():
    from baselines import b3_memo as B3
    assert B3.CANARY_MAX_SUCCESS_DROP == -0.2

    def r(tid, ok, error=None):
        return {"task_id": tid, "success": ok, "error": error}
    # H0: K=3 rolls per task; t1 passes 2/3 (succeeded), t2 0/3; t3's rolls are all infra errors (blocker)
    ref = [r("t1", True), r("t1", True), r("t1", False), r("t2", False), r("t2", False), r("t2", False),
           r("t3", False, "x"), r("t3", False, "y"), r("t3", False, "z")]
    m = B3.canary_metrics(ref)
    assert m["cases_learning"] == 2 and m["blockers"] == 1 and m["success_rate"] == 0.5
    assert abs(m["mean_reward"] - 1 / 3) < 1e-9  # per-task mean, blockers excluded
    # the canary loses t1 (1 roll each): reward delta -1/3 passes rule 1 (-0.34) but rule 3 rejects it
    ok, why = B3.canary_check(B3.canary_metrics([r("t1", False), r("t2", False), r("t3", False, "e")]), m)
    assert not ok and "success rate dropped" in why
    # one more blocker than H0 is rejected; all blockers is rejected; equal is accepted
    ok, why = B3.canary_check(B3.canary_metrics([r("t1", True), r("t2", False, "e"), r("t3", False, "e")]), m)
    assert not ok and "blocker" in why
    assert not B3.canary_check(B3.canary_metrics([r("t1", False, "e")]), m)[0]
    assert B3.canary_check(B3.canary_metrics([r("t1", True), r("t2", False), r("t3", False, "e")]), m)[0]


def test_b3_adaptation_is_clamped_and_falls_back():
    from baselines import b3_memo as B3
    import llm as llm_mod
    ctl = B3.ConfigController(client=SimpleNamespace(), model=B3.MODEL, api_config=B3.API)
    base = B3.base_config(ctl)
    task = SimpleNamespace(task_id="t", instruction="do it")

    def run(adapt_fn):
        ctl.adapt_for_case = adapt_fn
        alog: list = []
        return B3.adapt_composer(ctl, B3.BM25ExperienceBank(), base, "alfworld", alog, True)(task, None, None), alog

    def wild(bank, case, cfg):
        c = cfg.clone()
        c.D3.update(temperature=7.0, max_tokens="lots")
        c.D5.update(history_keep=1)
        return SimpleNamespace(config=c)
    b, _ = run(wild)
    assert b["agent_loop"]["config"] == {"temperature": 1.0, "max_tokens": 2048}  # clamped; non-number -> base
    assert b["context_mgmt"]["config"]["keep_turns"] == 4

    def boom(*a):
        raise ValueError("bad json")
    b, alog = run(boom)
    assert b == B3.to_bundle(base) and "bad json" in alog[0]["error"]

    def broke(*a):
        try:
            raise llm_mod.BudgetExceeded("MAX_USD exhausted")
        except llm_mod.BudgetExceeded as e:
            raise RuntimeError("controller call failed") from e  # as call_with_retries would wrap it
    try:
        run(broke)
    except llm_mod.BudgetExceeded:
        pass
    else:
        raise AssertionError("budget exhaustion must stop the run")


def test_b3_ingest_skips_infra_errors():
    from baselines import b3_memo as B3
    ctl = B3.ConfigController(client=SimpleNamespace(), model=B3.MODEL, api_config=B3.API)
    base = B3.base_config(ctl)
    bank = B3.BM25ExperienceBank()
    recs = [{**_b3_rec(f"s{i}", True, f"task {i}", i), "error": None} for i in range(2)]
    recs.append({"task_id": "inf", "success": False, "steps": 0, "tokens": 0, "error": "RuntimeError: down",
                 "trajectory_path": None})
    B3.ingest(bank, recs, 0, base, base, "alfworld", client=None, distiller=None, log={})
    assert sorted(e.case_id for e in bank.entries) == ["s0", "s1"]


def test_b1_analyze_prompt_shows_code_and_tasks():
    from baselines import b1_freeform as B1
    assert "Read harness implementations" in B1.SKILL
    root = TMP / "b1cand"
    C.new_candidate(root, C.H0_ROOT)
    f = root / "variants" / "memory" / "default.py"
    f.write_text(f.read_text(encoding="utf-8") + "\n# CHANGED_LINE\n", encoding="utf-8")
    code = B1._pool_code([{"name": "h0", "root": C.H0_ROOT}, {"name": "r1", "root": root}])
    assert "### h0 (complete)" in code and "...[truncated]" not in code
    assert "### r1 (diff vs h0)" in code and "+# CHANGED_LINE" in code
    assert C.tree_text(C.H0_ROOT, None) == C.tree_text(C.H0_ROOT, 10**9)  # None: never truncated
    p = traj("b1task", "t", "put the apple in the fridge")
    assert "TASK: put the apple" in C.summarize_trajectory(p, task_chars=B1.TASK_CHARS)
    assert "TASK:" not in C.summarize_trajectory(p)  # B2/B3 default unchanged


def test_reply_files_restores_lost_arg_value_token():
    from baselines.proposer_io import reply_files, restore_special_tokens
    h0 = (C.H0_ROOT / "variants" / "tool_policy" / "default.py").read_text(encoding="utf-8")
    assert restore_special_tokens(h0) == h0
    lost = h0.replace("<arg_value>", '">')  # what the model emits for its own tool-call token
    assert restore_special_tokens(lost) == h0
    for ok in ('href="x">', 'x = "<a>">', 'd["k"]>1'):
        assert restore_special_tokens(ok) == ok
    reply = SimpleNamespace(content="### FILE: variants/tool_policy/default.py\n```python\n" + lost + "```\n")
    assert reply_files(reply)["variants/tool_policy/default.py"] == h0

def test_chatshim_forwards_reference_kwargs():
    from baselines.b3_memo import ChatShim

    class Spy:
        def chat(self, messages, tag="", temperature=None, max_tokens=None, fallback_no_reasoning=False):
            self.got = dict(temperature=temperature, max_tokens=max_tokens, tag=tag)
            return SimpleNamespace(content="ok")

    spy = Spy()
    shim = ChatShim(spy, "b3:test")
    out = shim.chat.completions.create(model="m", messages=[{"role": "user", "content": "hi"}],
                                       temperature=0.2, max_completion_tokens=1024)
    assert out.choices[0].message.content == "ok"
    assert spy.got == {"temperature": 0.2, "max_tokens": 1024, "tag": "b3:test"}
    try:
        shim.chat.completions.create(model="m", messages=[], response_format={"type": "json_object"})
    except TypeError as exc:
        assert "response_format" in str(exc)
    else:
        raise AssertionError("an unforwarded keyword must be refused, not dropped")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
