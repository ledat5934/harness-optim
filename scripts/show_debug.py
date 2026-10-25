"""Render a debug run (scripts/run_baselines.py --debug) as one readable markdown transcript.

  python scripts/show_debug.py results/debug/b1_alfworld_20261019_120000
writes <dir>/transcript.md: every LLM call in order (tag, tokens, cost, the request messages, the hidden reasoning,
the reply and its tool calls), then the outcome of each episode. Agent calls resend the whole history each step, so
only the messages that are new since the previous call with the same tag are printed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _text(x) -> str:
    if x is None:
        return ""
    return x if isinstance(x, str) else json.dumps(x, ensure_ascii=False, indent=1)


def _block(title: str, body: str) -> list[str]:
    body = body.rstrip()
    if not body:
        return []
    return [f"**{title}**", "", "````text", body, "````", ""]


def _message(m: dict) -> list[str]:
    role = m.get("role", "?")
    out = _block(role + (f" (tool_call_id={m['tool_call_id']})" if m.get("tool_call_id") else ""), _text(m.get("content")))
    for tc in m.get("tool_calls") or []:
        fn = tc.get("function") or {}
        out += [f"- `{role}` tool call `{fn.get('name')}` {fn.get('arguments')}", ""]
    return out


def write(run_dir: Path | str) -> Path:
    run_dir = Path(run_dir)
    lines = [f"# Debug transcript: `{run_dir.name}`", ""]
    prev: dict[str, list] = {}
    calls = [json.loads(l) for l in (run_dir / "llm_full.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()] \
        if (run_dir / "llm_full.jsonl").exists() else []
    total = sum(c["cost"] for c in calls)
    lines += [f"{len(calls)} LLM calls, ${total:.5f} in total.", ""]
    for i, c in enumerate(calls, 1):
        req, resp = c["request"], c["response"]
        lines += [f"## [{i}] `{c['tag']}` · pt={c['pt']} ct={c['ct']} · ${c['cost']:.5f} · finish={c['finish_reason']} "
                  f"· {c.get('provider')}", ""]
        if req.get("tools"):
            lines += [f"tools offered: {req['tools']} · tool_choice={req.get('tool_choice')} · "
                      f"temperature={req.get('temperature')} · max_tokens={req.get('max_tokens')}", ""]
        msgs = req.get("messages") or []
        key = c["tag"].split(":noreason")[0]
        old = prev.get(key) or []
        if old and len(msgs) > len(old) and msgs[: len(old)] == old:
            lines += [f"_(… {len(old)} earlier messages, same as call with this tag above)_", ""]
            new = msgs[len(old):]
        else:
            new = msgs
        prev[key] = msgs + [{"role": "assistant", "content": resp.get("content"), "tool_calls": resp.get("tool_calls")}]
        lines += ["### request", ""]
        for m in new:
            lines += _message(m)
        lines += ["### reply", ""]
        lines += _block("hidden reasoning", _text(resp.get("reasoning")))
        lines += _block("content", _text(resp.get("content")))
        for tc in resp.get("tool_calls") or []:
            fn = tc.get("function") or {}
            lines += [f"- tool call `{fn.get('name')}` {fn.get('arguments')}", ""]
    lines += ["# Episodes", ""]
    for p in sorted((run_dir / "trajectories").rglob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        lines += [f"- `{p.relative_to(run_dir).as_posix()}`: success={d.get('success')} steps={d.get('steps')} "
                  f"tokens={d.get('tokens')} cost=${d.get('cost', 0):.5f} error={d.get('error')} "
                  f"eval={json.dumps(d.get('eval_info'), ensure_ascii=False)[:300]}"]
    out = run_dir / "transcript.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    print(write(sys.argv[1]))
