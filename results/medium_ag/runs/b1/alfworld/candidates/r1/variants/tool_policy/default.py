"""tool_policy/default: expose the env's native tools as-is; parse native tool calls with a text fallback.

- tools(task): the adapter's tool schemas, unchanged.
- parse(resp): native `tool_calls`. When the model replies in text, we also accept the text tool-call formats
  open models emit even when native tools are offered: a <tool_call>{json}</tool_call> block, a GLM-style
  <tool_call>name<arg_key>k</arg_key><arg_value>v</arg_value></tool_call> block, a Qwen-style
  <function=name><parameter=k>v</parameter></function> block, or a bare JSON object {"name": ..., "arguments": ...}
  (nested braces allowed). The arguments are JSON-decoded (also from a ```json fence or with trailing text);
  on a decode error the raw string is passed under "_raw" so the env reports the problem instead of us dropping it.
  Placement commands like 'put/place <obj> in/on/into/onto <recep>' are normalized to 'move <obj> to <recep>'.
  A plain-text reply in the BrowseComp answer format ("Exact Answer: ...") on a task with a finish tool is taken
  as that finish call with the whole reply as the answer, as the reference BrowseComp-Plus agent does.
- format_observation: the env's text, truncated to `max_obs_chars` (head+tail).
"""
from __future__ import annotations

import json
import re

from benchmarks.common import truncate
from h0.protocols import Action

_TC_BLOCK = re.compile(r"<tool_call>(.*?)(?:</tool_call>|$)", re.S)
_ARG_KV = re.compile(r"<arg_key>\s*(.*?)\s*</arg_key>\s*<arg_value>(.*?)</arg_value>", re.S)
_FN_BLOCK = re.compile(r"<function=([\w.\-]+)>(.*?)(?:</function>|$)", re.S)
_EXACT = re.compile(r"^\W*exact answer\W*:", re.I | re.M)
_PARAM = re.compile(r"<parameter=([\w.\-]+)>\s*(.*?)\s*</parameter>", re.S)
_PUT_PATTERN = re.compile(r"^\s*(?:put|place)\s+(.+?)\s+(?:in/on|into|onto|in|on)\s+(.+?)\s*$", re.I)


def _json_objects(text: str):
    """Every balanced top-level {...} in free text that decodes as JSON (strings with braces/escapes handled)."""
    i = text.find("{")
    while i != -1:
        depth, in_str, esc, end = 0, False, False, -1
        for j in range(i, len(text)):
            c = text[j]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            elif c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    end = j
                    break
        if end == -1:
            return
        try:
            yield json.loads(text[i:end + 1])
            i = text.find("{", end + 1)
        except json.JSONDecodeError:
            i = text.find("{", i + 1)


def _decode_args(raw):
    """Tool arguments -> dict. Accepts a dict, a JSON string, JSON inside a code fence or followed by extra text."""
    if isinstance(raw, dict):
        return raw
    raw = raw or "{}"
    try:
        args = json.loads(raw)
        if isinstance(args, str):  # double-encoded
            args = json.loads(args)
        if isinstance(args, dict):
            return args
    except (json.JSONDecodeError, TypeError):
        pass
    for obj in _json_objects(str(raw)):
        if isinstance(obj, dict):
            return obj
    return {"_raw": raw}


def _value(v: str):
    v = v.strip()
    try:
        return json.loads(v) if v[:1] in "[{" else v
    except json.JSONDecodeError:
        return v


def _normalize_command_str(s: str) -> str:
    cleaned = s.strip().strip("'\"").rstrip(".")
    m = _PUT_PATTERN.match(cleaned)
    if m:
        return f"move {m.group(1).strip()} to {m.group(2).strip()}"
    return s


def _normalize_val(v):
    if isinstance(v, str):
        return _normalize_command_str(v)
    if isinstance(v, dict):
        return {k: _normalize_val(val) for k, val in v.items()}
    if isinstance(v, list):
        return [_normalize_val(item) for item in v]
    return v


def _normalize_args(args: dict) -> dict:
    if not isinstance(args, dict):
        return args
    return {k: _normalize_val(v) for k, v in args.items()}


class NativeTools:
    def __init__(self, max_obs_chars: int = 8000, text_fallback: bool = True):
        self.max_obs_chars, self.text_fallback = max_obs_chars, text_fallback

    def tools(self, task):
        return task.tools

    def parse(self, resp, task):
        acts = []
        for tc in resp.tool_calls or []:
            fn = tc.get("function") or {}
            raw_args = fn.get("arguments") or "{}"
            args = _decode_args(raw_args)
            args = _normalize_args(args)
            acts.append(Action(tool=fn.get("name", ""), args=args, call_id=tc.get("id"),
                               raw={"function": {"name": fn.get("name", ""), "arguments": raw_args}}))
        names = {t["function"]["name"] for t in getattr(task, "tools", [])}
        for act in acts:
            if act.tool in ("put", "place") and act.tool not in names and "move" in names:
                act.tool = "move"
        if acts or not self.text_fallback:
            return acts
        for name, args in self._text_calls(resp.content or ""):
            args = _normalize_args(args)
            if name in ("put", "place") and name not in names and "move" in names:
                name = "move"
            if name in names:
                return [Action(tool=name, args=args, call_id=None, raw={"name": name, "arguments": args})]
        fin = getattr(task, "finish_tool", "")
        if fin in names and _EXACT.search(resp.content or ""):
            args = {"answer": resp.content.strip()}
            return [Action(tool=fin, args=args, call_id=None, raw={"name": fin, "arguments": args})]
        return []

    @staticmethod
    def _text_calls(txt: str):
        for body in _TC_BLOCK.findall(txt):
            body = body.strip()
            if body.startswith("{"):
                for d in _json_objects(body):
                    if isinstance(d, dict) and "name" in d:
                        yield str(d["name"]), _decode_args(d.get("arguments", d.get("parameters", {})))
            else:  # GLM style: name, then <arg_key>/<arg_value> pairs
                name = re.split(r"[\s<]", body, maxsplit=1)[0]
                yield name, {k: _value(v) for k, v in _ARG_KV.findall(body)}
        for name, body in _FN_BLOCK.findall(txt):
            yield name, {k: _value(v) for k, v in _PARAM.findall(body)}
        for d in _json_objects(txt):
            if isinstance(d, dict) and isinstance(d.get("name"), str) and ("arguments" in d or "parameters" in d):
                yield d["name"], _decode_args(d.get("arguments", d.get("parameters", {})))

    def format_observation(self, action, result, task):
        return truncate(result.observation, self.max_obs_chars)


def register(reg):
    reg.register("tool_policy", "default", lambda c: NativeTools(**c),
                 "Exposes the environment's native tools unchanged; parses native tool calls (text fallback: JSON, "
                 "<tool_call> JSON or GLM arg_key/arg_value, <function=...> blocks); normalizes placement commands; "
                 "observations truncated head+tail to 8000 chars.",
                 config_schema={"max_obs_chars": "int (default 8000)", "text_fallback": "bool (default true)"},
                 niche={"exposure": "all", "parse": "native+text", "obs": "truncate"})
