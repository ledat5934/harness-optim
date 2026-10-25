"""Offline tests for the ModularRSI self-evo modules ported into B2: portfolio lanes, backlog and clustering, the routing
probe, and one dual-implementation round (one lane repaired, the other rebased). A scripted fake client answers every
tag; no API call, no episode.

  python tests/test_b2_port.py
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from baselines import b2_modular as B2  # noqa: E402
from baselines import common as C  # noqa: E402
from baselines.vendor.modularrsi import backlog as BL  # noqa: E402
from baselines.vendor.modularrsi import portfolio as PF  # noqa: E402
from baselines.vendor.modularrsi import proposals as PP  # noqa: E402
from baselines.vendor.modularrsi import routing_probe as RP  # noqa: E402
from h0.protocols import SLOTS  # noqa: E402
from h0.registry import load_registry  # noqa: E402

NAMES = {"agent_loop": "alpha_loop", "tool_policy": "beta_policy"}


def tmp(prefix: str) -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix))


def renamed(slot: str, name: str) -> str:
    """The H0 default for a slot, registered under a new name (a minimal, valid sibling variant)."""
    src = (C.H0_ROOT / "variants" / slot / "default.py").read_text(encoding="utf-8")
    code = src.replace(f'reg.register("{slot}", "default"', f'reg.register("{slot}", "{name}"')
    assert code != src
    return code


class FakeLLM:
    """Scripted endpoint. `composer_pick` forces the composer's choice; `route` is the routing object it emits."""

    def __init__(self, composer_pick: str | None = None, route: dict | None = None,
                 describe: str = "Pick when the loop must re-read state before retrying a stale step."):
        self.calls = Counter()
        self.review_seen = Counter()
        self.composer_pick = composer_pick
        self.route = route
        self.describe = describe

    def chat(self, messages, tools=None, tag="", **kw):
        prompt = messages[0]["content"]
        kind = tag.split(":")[1]
        self.calls[kind] += 1
        if kind == "implement":
            slot = re.search(r"slot `(\w+)`", prompt).group(1)
            content = f"### FILE: variants/{slot}/{NAMES[slot]}.py\n```python\n{renamed(slot, NAMES[slot])}\n```"
        elif kind == "review":
            slot = re.search(r"variants/(\w+)/\w+\.py", prompt).group(1)
            self.review_seen[slot] += 1
            if slot == "tool_policy" and self.review_seen[slot] == 1:  # the first build is flawed code, not a bad direction
                content = ('<review_verdict decision="reject" reject_class="implementation" '
                           'reason="parse() drops tool calls" repair_brief="keep parse() total over every tool call"/>')
            else:
                content = '<review_verdict decision="accept" reason="targets a visible failure"/>'
        elif kind == "composer":
            if self.composer_pick is not None:
                content = json.dumps({"agent_loop": self.composer_pick})
            else:  # select the non-default variant of every slot whose catalog has one
                out = {}
                for sec in re.split(r"\n## ", prompt)[1:]:
                    slot = sec.split()[0]
                    picks = [n for n in re.findall(r"^- (\w+):", sec, re.M) if n != "default"]
                    if slot in SLOTS and picks:
                        out[slot] = picks[0]
                content = json.dumps(out)
        elif kind == "route":
            content = "<routing>\n" + json.dumps(self.route) + "\n</routing>"
        elif kind == "describe":
            content = f"<description>{self.describe}</description>"
        else:
            content = ""
        return SimpleNamespace(content=content, cost=0.0, tool_calls=[])


def setup_ws():
    """A lineage with two lanes: an incumbent proposal on agent_loop, a novelty proposal on tool_policy."""
    ws = tmp("b2port_")
    recs = BL.ingest_step(ws, {"step": "r1", "findings": [
        {"task": "t1", "lens": "agent_loop", "is_culprit": True, "parse_status": "ok", "fixable_now": True,
         "suggested_change": "re-read state before retrying"},
        {"task": "t2", "lens": "tool_policy", "is_culprit": True, "parse_status": "ok", "fixable_now": True,
         "suggested_change": "parse every tool call"}]})
    p_inc = PP.create_proposal(ws, step="r1", lane="incumbent", action="modify", target_variant="agent_loop/default",
                               behavioral_delta="retry with the state re-read", causal_hypothesis="stale state",
                               finding_ids=[recs[0].finding_id], support_tasks=["t1"])
    p_nov = PP.create_proposal(ws, step="r1", lane="novelty", action="add", target_variant="",
                               behavioral_delta="parse all tool calls", causal_hypothesis="calls are dropped",
                               finding_ids=[recs[1].finding_id], support_tasks=["t2"])
    return ws, recs, p_inc, p_nov


BY_TASK = {"t1": [{"task_id": "t1", "extra": {"instruction": "fix the loop"}}],
           "t2": [{"task_id": "t2", "extra": {"instruction": "parse the calls"}}]}


def test_portfolio_one_pick_per_lane():
    ws, _, p_inc, p_nov = setup_ws()
    broad = PP.create_proposal(ws, step="r1", lane="incumbent", action="modify", target_variant="tool_policy/default",
                               behavioral_delta="x", finding_ids=[], support_tasks=["t3", "t4"])
    picks = PF.select_portfolio(ws, max_lanes=2, seed="s")
    assert sorted(p.lane for p in picks) == ["incumbent", "novelty"]
    inc = next(p for p in picks if p.lane == "incumbent")
    assert inc.proposal_id == broad.proposal_id  # two supporting tasks outrank one
    assert len(PF.select_portfolio(ws, max_lanes=1, seed="s")) == 1
    assert PF.select_portfolio(ws, max_lanes=0, seed="s") == []


def test_backlog_keeps_non_fixable_culprits_and_routes_only_fixable():
    ws = tmp("b2port_bl_")
    client = FakeLLM(route={"lane": "incumbent", "action": "modify", "target_variant": "memory/default",
                            "behavioral_delta": "recall the failed step", "rationale": "memory/default is the only variant"})
    recs = BL.ingest_step(ws, {"step": "r1", "findings": [
        {"task": "t1", "lens": "memory", "is_culprit": True, "parse_status": "ok", "fixable_now": True,
         "suggested_change": "recall the failed step"},
        {"task": "t2", "lens": "agent_loop", "is_culprit": True, "parse_status": "ok", "fixable_now": False,
         "suggested_change": "needs a kernel change"}]})
    rd = {}
    B2.route_and_cluster(client, "dry", ws, "r1", recs, load_registry(C.H0_ROOT), rd)
    rows = [json.loads(l) for l in (ws / "backlog" / "findings.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {r["finding_id"] for r in rows} == {r.finding_id for r in recs}  # both culprits in the backlog
    assert any(r["raw_finding"]["fixable_now"] is False for r in rows)
    assert client.calls["route"] == 1  # only the fixable one is routed
    assert PP.proposal_of_finding(ws, recs[1].finding_id) is None
    assert PP.proposal_of_finding(ws, recs[0].finding_id) is not None
    assert [r["decision"] for r in rd["clustering"]] == ["created"]


def _tree_with_variant(slot: str) -> Path:
    tree = tmp("b2port_route_") / "tree"
    C.new_candidate(tree, C.H0_ROOT)
    (tree / "variants" / slot / f"{NAMES[slot]}.py").write_text(renamed(slot, NAMES[slot]), encoding="utf-8")
    return tree


def test_routing_probe_with_no_selection_is_unproven():
    tree = _tree_with_variant("agent_loop")
    client = FakeLLM(composer_pick="default")  # the composer never picks the new variant
    res = asyncio.run(B2.routing_check(client, "dry", tree, "agent_loop", NAMES["agent_loop"], ["t1"], BY_TASK))
    assert res.verdict == RP.VERDICT_UNPROVEN and res.picks == {"t1": "default"}


def test_routing_diagnosis_rewrites_description_once_and_does_not_gate():
    tree = _tree_with_variant("agent_loop")
    client = FakeLLM(composer_pick="default")
    diag = asyncio.run(B2.routing_diagnosis(client, "dry", tree, "agent_loop", NAMES["agent_loop"], "finding text",
                                            ["t1"], BY_TASK))
    assert diag["first"] == RP.VERDICT_UNPROVEN and diag["rewritten"] is True
    assert diag["final"] == RP.VERDICT_UNPROVEN  # still unselected, but the lane is not rejected for it
    assert client.calls["describe"] == 1  # one rewrite, no further rounds
    desc = next(i.description for i in load_registry(tree).infos("agent_loop") if i.name == NAMES["agent_loop"])
    assert desc == "Pick when the loop must re-read state before retrying a stale step."


def test_routing_diagnosis_skips_the_rewrite_when_the_variant_is_selected():
    tree = _tree_with_variant("agent_loop")
    client = FakeLLM()  # the composer selects the non-default variant
    diag = asyncio.run(B2.routing_diagnosis(client, "dry", tree, "agent_loop", NAMES["agent_loop"], "finding text",
                                            ["t1"], BY_TASK))
    assert diag["first"] == RP.VERDICT_PROVEN and not diag["rewritten"] and client.calls["describe"] == 0


def test_set_description_replaces_only_the_register_description():
    src = renamed("agent_loop", NAMES["agent_loop"])
    out = B2._set_description(src, 'a "quoted" criterion')
    assert out is not None and out.count("reg.register(") == src.count("reg.register(")
    assert B2._set_description(src, "") is None
    assert B2._set_description("x = 1\n", "anything") is None


def test_dual_implement_repairs_one_lane_and_rebases_the_other():
    ws, recs, p_inc, p_nov = setup_ws()
    client = FakeLLM()
    picks = PF.select_portfolio(ws, max_lanes=2, seed="s")
    lens_of = {r.finding_id: r.lens for r in recs}
    outcomes = B2.dual_implement(client, "dry", ws, "r1", picks, C.H0_ROOT, lens_of, [], BY_TASK)
    by = {o.proposal_id: o for o in outcomes}
    assert by[p_inc.proposal_id].result.passed and by[p_nov.proposal_id].result.passed
    assert by[p_nov.proposal_id].retry and not by[p_inc.proposal_id].retry  # the novelty lane was repaired
    assert client.calls["implement"] == 3  # agent_loop once; tool_policy twice (first build + repair)
    assert client.review_seen["tool_policy"] == 2

    cand = C.new_candidate(tmp("b2port_cand_") / "cand", C.H0_ROOT)
    merged, failed = B2.merge_lanes(client, "dry", C.H0_ROOT, cand, outcomes, [], BY_TASK, tmp("b2port_work_"))
    assert failed == {}, failed
    assert [m["variant"] for m in merged] == [NAMES["agent_loop"], NAMES["tool_policy"]]
    assert [m["rebased"] for m in merged] == [False, True]  # the second lane is rebased onto the first
    assert (cand / "variants/agent_loop" / f"{NAMES['agent_loop']}.py").exists()
    assert (cand / "variants/tool_policy" / f"{NAMES['tool_policy']}.py").exists()

    B2.close_lanes(ws, "r1", outcomes, {m["proposal"] for m in merged}, True, failed)
    assert PP.get_proposal(ws, p_inc.proposal_id).state == PP.PROMOTED
    assert PP.get_proposal(ws, p_nov.proposal_id).state == PP.PROMOTED


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
