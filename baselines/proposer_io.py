"""Parsing helpers for LLM proposers that return whole files (plain text; no JSON-schema mode).

The parsers tolerate the formatting drift small models show (see the debug transcripts in results/debug/):
missing code fences, markdown bold around headers and labels, fences inside a file, ```json fences, trailing
commas, Python literals, and "true" / "0.8" / "high" given as strings.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

# "### FILE: path", also "## File: `path`", "**FILE:** path", "FILE: path" at the start of a line
FILE_HDR = re.compile(r"^[ \t]*(?:#{1,6}[ \t]*)?(?:\*\*)?[ \t]*FILE[ \t]*(?:\*\*)?[ \t]*:[ \t]*(?:\*\*)?[ \t]*"
                      r"(?P<path>[^\n]+?)[ \t]*$", re.M | re.I)
FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})[^\n]*$", re.M)
ALLOWED = re.compile(r"^(variants/(agent_loop|context_mgmt|tool_policy|memory|verifier)/[a-z0-9_]+\.py|system_prompt\.txt|bundle\.json)$")


def _clean_path(p: str) -> str:
    p = p.strip().strip("*").strip().strip("`'\"").strip()
    p = re.sub(r"\s*\(.*\)$", "", p).strip("`'\"")  # "variants/x/y.py (complete file)"
    while p.startswith(("./", "/")):
        p = p[2:] if p.startswith("./") else p[1:]
    return p


def _body(seg: str) -> str:
    """File content of one segment (the text between a FILE header and the next one). If the segment starts with a
    code fence, the content runs to the LAST bare closing fence of the same kind, so fences inside the file
    survive; otherwise it is the bare segment up to the first fence line, if any."""
    fences = list(FENCE.finditer(seg))
    if fences and not seg[: fences[0].start()].strip():
        tick = fences[0].group(1)[0]
        closers = [f for f in fences[1:] if f.group(1)[0] == tick and f.group(0).strip() == f.group(1)]
        end = closers[-1].start() if closers else len(seg)
        return seg[fences[0].end() + 1: end].rstrip("\n")
    if fences:
        seg = seg[: fences[0].start()]
    return seg.strip("\n").rstrip()


def _trim_python(body: str) -> str:
    """Unfenced code is often followed by a prose sentence: drop trailing lines until the file compiles."""
    try:
        compile(body, "<proposal>", "exec")
        return body
    except SyntaxError:
        pass
    lines = body.split("\n")
    for k in range(1, min(40, len(lines) - 1)):
        cand = "\n".join(lines[:-k])
        try:
            compile(cand, "<proposal>", "exec")
            return cand
        except SyntaxError:
            continue
    return body  # let the validation gate report the real error


def parse_files(text: str) -> dict[str, str]:
    out = {}
    text = text or ""
    hdrs = list(FILE_HDR.finditer(text))
    for i, m in enumerate(hdrs):
        seg = text[m.end(): hdrs[i + 1].start() if i + 1 < len(hdrs) else len(text)]
        body = _body(seg[1:] if seg.startswith("\n") else seg)
        path = _clean_path(m.group("path"))
        if path.endswith(".py"):
            body = _trim_python(body)
        if body.strip():
            out[path] = body.rstrip("\n") + "\n"
    return out


def reply_files(resp) -> dict[str, str]:
    """parse_files on an LLM reply. When the model's hidden reasoning contains a literal `<tool_call>` (it is copying a
    parser regex from default.py), the provider ends the `reasoning` field there and the rest of the thinking leaks
    into `content`, closed by `</think>` with the answer glued on the same line (`</think>### FILE: ...`). Only the
    text after the last `</think>` is the answer."""
    text = resp.content or ""
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[1]
    return parse_files(restore_special_tokens(text))


# The model cannot emit the literal `<arg_value>` (its own tool-call token): it comes back as `">`. H0's tool_policy
# parses GLM-style `<arg_key>k</arg_key><arg_value>v</arg_value>` text, so every copy of that file lost the token and
# broke the regex (unterminated string literal). Restored only right after `</arg_key>` (optionally a literal or
# real `\s*`) or in `<arg_key>/`, where `">` cannot be meant.
_ARG_VALUE_LOST = re.compile(r'(</arg_key>(?:\\s\*|\s*)|<arg_key>/)">')


def restore_special_tokens(text: str) -> str:
    return _ARG_VALUE_LOST.sub(r"\1<arg_value>", text)


def gate_hint(log: str) -> str:
    """Restates the existing no-cross-candidate-import rule when the gate failed on exactly that."""
    if "No module named 'variants'" in (log or ""):
        return ("\nNote: candidate files cannot import each other (`variants.*` is not importable). Copy the code you "
                "need from default.py into the new file.")
    return ""


def apply_files(root: Path, files: dict[str, str], allowed: re.Pattern = ALLOWED) -> tuple[list[str], list[str]]:
    written, rejected = [], []
    for rel, body in files.items():
        if not allowed.match(rel):
            rejected.append(rel)
            continue
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        written.append(rel)
    return written, rejected


def field(text: str, name: str) -> str:
    """Value of a 'NAME: value' line; tolerates markdown ('**NAME:** v', '## NAME: v', '- NAME: v')."""
    m = re.search(rf"^[ \t>*#\-]*{name}[ \t]*\**[ \t]*:[ \t]*\**[ \t]*(.+?)[ \t]*$", text or "", re.M | re.I)
    return m.group(1).strip().strip("*").strip() if m else ""


def _loads(s: str):
    """json.loads, then common repairs: trailing commas, Python literals (True/None/single quotes)."""
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    t = re.sub(r",(\s*[}\]])", r"\1", s)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    try:
        v = ast.literal_eval(t)
        return v if isinstance(v, (dict, list)) else None
    except (ValueError, SyntaxError, MemoryError, RecursionError):
        return None


def _balanced(text: str, start: int, opener: str, closer: str) -> int:
    """Index of the bracket closing text[start], or -1. Brackets inside "..." strings are skipped (escapes
    handled; a single quote opens a string only right after a JSON delimiter, so apostrophes in prose don't)."""
    depth, quote, esc = 0, None, False
    for i in range(start, len(text)):
        c = text[i]
        if quote:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == quote:
                quote = None
            continue
        if c == '"' or (c == "'" and text[i - 1:i] in ("{", "[", ",", ":", " ", "\n", "\t")):
            quote = c
        elif c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                return i
    return -1


def extract_json(text: str, prefer: str = "{"):
    """First balanced JSON object/array in free text (as ModularRSI/_extract_json does); ```json fences first.
    prefer="[" looks for an array first (otherwise the first object INSIDE an array would be returned)."""
    text = text or ""
    for src in re.findall(r"```[a-zA-Z]*[ \t]*\n(.*?)\n[ \t]*```", text, re.S) + [text]:
        v = _extract(src, prefer)
        if v is not None:
            return v
    return None


def _extract(text: str, prefer: str):
    order = (("{", "}"), ("[", "]")) if prefer == "{" else (("[", "]"), ("{", "}"))
    for opener, closer in order:
        start = text.find(opener)
        while start != -1:
            end = _balanced(text, start, opener, closer)
            if end != -1:
                v = _loads(text[start:end + 1])
                if v is not None:
                    return v
            start = text.find(opener, start + 1)
    return None


_SCALAR = re.compile(r'"(\w+)"\s*:\s*("(?:[^"\\]|\\.)*"|true|false|null|-?\d+(?:\.\d+)?)')


def salvage_fields(text: str) -> dict:
    """Scalar "key": value pairs from a JSON object that does not parse, typically one cut off by the output
    length limit ({"is_culprit": true, "confidence": 0.7, "mechanism": "...<end of output>). First value wins."""
    out = {}
    start = (text or "").find("{")
    for k, v in _SCALAR.findall(text[start:] if start != -1 else ""):
        if k not in out:
            try:
                out[k] = json.loads(v)
            except json.JSONDecodeError:
                continue
    return out


def as_bool(v) -> bool:
    """LLM booleans: true / "true" / "yes" / 1 (bool("false") would be True)."""
    if isinstance(v, str):
        return v.strip().lower() in ("true", "yes", "y", "1")
    return bool(v)


def as_float(v, default: float = 0.0) -> float:
    """LLM numbers: 0.8 / "0.8" / "80%" / "high"."""
    if isinstance(v, (bool, int, float)):
        return float(v)
    s = str(v or "").strip().lower()
    words = {"very high": 0.9, "high": 0.8, "medium": 0.5, "moderate": 0.5, "low": 0.2, "very low": 0.1}
    if s in words:
        return words[s]
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    if not m:
        return default
    return float(m.group(0)) / (100 if s.endswith("%") else 1)
