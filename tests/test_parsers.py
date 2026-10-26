"""Offline tests for the tolerant LLM-output parsers (no API calls). Cases are shapes seen in real runs.

  python tests/test_parsers.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from baselines.b2_modular import _composer_choice  # noqa: E402
from baselines.b3_memo import API, MODEL, _diagnoses, base_config, clamp, norm_dim  # noqa: E402
from baselines.vendor.memoharness.controllers.llm_controller import LLMController  # noqa: E402
from baselines.proposer_io import (as_bool, as_float, extract_json, field, gate_hint, parse_files, reply_files,  # noqa: E402
                                   salvage_fields)
from benchmarks.common import tool_arg  # noqa: E402
from h0.variants.tool_policy.default import NativeTools  # noqa: E402

PY = 'def register(reg):\n    x = {"a": 1}\n    return x\n'


def test_parse_files_fenced_and_unfenced():
    fenced = f"STATE: s\n### FILE: variants/memory/default.py\n```python\n{PY}```\nDone."
    assert parse_files(fenced) == {"variants/memory/default.py": PY}
    bare = f"HYPOTHESIS: h\n### FILE: variants/memory/default.py\n{PY}\nThis change adds a nudge.\n"
    assert parse_files(bare) == {"variants/memory/default.py": PY}  # trailing prose trimmed
    bold = f"**FILE:** `variants/verifier/default.py` (complete file)\n```python\n{PY}```"
    assert list(parse_files(bold)) == ["variants/verifier/default.py"]


def test_parse_files_inner_fence_and_two_files():
    inner = 'P = """use\n```\ncode\n```\n"""\n'
    t = f"### FILE: variants/a/default.py\n```python\n{inner}```\n\n## File: system_prompt.txt\n```text\nBe brief.\n```\n"
    out = parse_files(t)
    assert out["variants/a/default.py"] == inner and out["system_prompt.txt"] == "Be brief.\n"


def test_field_markdown():
    assert field("**HYPOTHESIS:** more steps help", "HYPOTHESIS") == "more steps help"
    assert field("## CANDIDATE: name=x", "CANDIDATE") == "name=x"


def test_extract_json_variants():
    assert extract_json('x {"a": "say \\"hi\\" {not a brace}", "b": 2} y') == {"a": 'say "hi" {not a brace}', "b": 2}
    assert extract_json('```json\n{"a": [1, 2,],}\n```') == {"a": [1, 2]}
    assert extract_json("{'is_culprit': True, 'confidence': None}") == {"is_culprit": True, "confidence": None}
    assert extract_json('It\'s here: [{"x": 1}]', prefer="[") == [{"x": 1}]


def test_salvage_and_coercion():
    cut = '{"is_culprit": true, "confidence": 0.65, "mechanism": "NoMemory provides zero cross-episode knowledge tr'
    assert extract_json(cut) is None
    assert salvage_fields(cut) == {"is_culprit": True, "confidence": 0.65}
    assert as_bool("false") is False and as_bool("Yes") is True
    assert as_float("high") == 0.8 and as_float("70%") == 0.7 and as_float("0.4") == 0.4


def test_composer_and_b3_shapes():
    assert _composer_choice({"memory": {"name": "notes"}}) == {"memory": "notes"}
    assert _composer_choice({"choices": [{"slot": "verifier", "variant": "strict"}]}) == {"verifier": "strict"}
    assert norm_dim("d3 Generation") == "D3" and norm_dim("dimension 4") == "D4" and norm_dim("none") is None
    ids = ["look_at_obj-Alarm-308/trial_T1", "pick_two-Cd-101/trial_T2"]
    d = _diagnoses([{"case_id": "look_at_obj-Alarm-308", "primary_dim": "D2"}, {"case": "case pick_two-Cd-101/trial_T2"}], ids)
    assert d[ids[0]]["primary_dim"] == "D2" and ids[1] in d
    ctl = LLMController(client=None, model=MODEL, api_config=API)  # the reference parser/stabilizer
    cfg = clamp(ctl._build_harness_config({"D3": {"max_tokens": "3000", "temperature": 5}}, base_config(ctl)))
    assert cfg.D3["max_tokens"] == 3000 and cfg.D3["temperature"] == 1.0  # reference parser, then range guard


class _Resp:
    def __init__(self, content="", tool_calls=None):
        self.content, self.tool_calls = content, tool_calls or []


class _Task:
    def __init__(self, names, finish=""):
        self.tools = [{"function": {"name": n}} for n in names]
        self.finish_tool = finish


def test_tool_policy_text_formats():
    tp, t = NativeTools(), _Task(["search", "finish"], "finish")
    glm = "<tool_call>search\n<arg_key>query</arg_key>\n<arg_value>Diamond Jenness 1915</arg_value>\n</tool_call>"
    a = tp.parse(_Resp(glm), t)[0]
    assert (a.tool, a.args) == ("search", {"query": "Diamond Jenness 1915"})
    qwen = "<function=search>\n<parameter=query>\nfoo bar\n</parameter>\n</function>"
    assert tp.parse(_Resp(qwen), t)[0].args == {"query": "foo bar"}
    nested = 'call {"name": "search", "arguments": {"query": "a {b}", "opts": {"k": 5}}}'
    assert tp.parse(_Resp(nested), t)[0].args == {"query": "a {b}", "opts": {"k": 5}}
    final = "Explanation: because X.\nExact Answer: Rona\nConfidence: 80%"
    a = tp.parse(_Resp(final), t)[0]
    assert a.tool == "finish" and "Exact Answer: Rona" in a.args["answer"]
    assert tp.parse(_Resp("Let me try picking up the lamp."), _Task(["act"])) == []


def test_tool_policy_native_args():
    tp, t = NativeTools(), _Task(["act"])
    tc = lambda a: {"id": "1", "function": {"name": "act", "arguments": a}}  # noqa: E731
    assert tp.parse(_Resp(tool_calls=[tc('```json\n{"command": "look"}\n```')]), t)[0].args == {"command": "look"}
    assert tp.parse(_Resp(tool_calls=[tc('"{\\"command\\": \\"look\\"}"')]), t)[0].args == {"command": "look"}
    assert "_raw" in tp.parse(_Resp(tool_calls=[tc('{"command": "lo')]), t)[0].args


def test_tool_arg():
    assert tool_arg({"action": "look"}, "command", "action") == "look"
    assert tool_arg({"cmd_text": "look"}, "command") == "look"
    assert tool_arg({"_raw": "{bad"}, "command") is None


def test_reply_files_rejoins_split_at_tool_call():
    """Shape of a real ling-3.0-flash reply (B1 debug run 20261025_175825): reasoning stopped at a literal
    `<tool_call>`, the rest of the thinking leaked into content, and the answer follows `</think>` on the same line.
    The leaked thinking also contains a draft file that must not be used."""
    class R:
        def __init__(self, content):
            self.content = content
    content = ('<tool_call>(.*?)", re.S)\n\nDraft:\n```python\nOLD = 1\n```\nLet me output it.</think>'
               '### FILE: variants/tool_policy/state.py\n```python\nimport re\n_TC = re.compile(r"<tool_call>(.*?)")\n```')
    files = reply_files(R(content))
    assert list(files) == ["variants/tool_policy/state.py"]
    assert "OLD" not in files["variants/tool_policy/state.py"] and "_TC = re.compile" in files["variants/tool_policy/state.py"]
    ok = "### FILE: variants/memory/x.py\n```python\nX = 1\n```"
    assert list(reply_files(R(ok))) == ["variants/memory/x.py"]  # no </think>: unchanged
    assert reply_files(R("thinking only</think>")) == {}


def test_gate_hint():
    assert "Copy the code" in gate_hint("x.py: ModuleNotFoundError: No module named 'variants'")
    assert gate_hint("SyntaxError: invalid syntax") == ""


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
