"""Phase 0 smoke test: one plain call + one native tool-call through OpenRouter."""
import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import llm

llm.budget_banner("smoke_llm")
c = llm.LLM(max_tokens=256)
r = c.chat([{"role": "user", "content": "Reply with exactly: pong"}], tag="smoke_plain")
print(f"[plain] content={r.content!r} pt={r.prompt_tokens} ct={r.completion_tokens} cost=${r.cost:.6f} latency={r.latency_s:.2f}s")
tools = [{"type": "function", "function": {"name": "add", "description": "Add two integers.",
          "parameters": {"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
                         "required": ["a", "b"]}}}]
r = c.chat([{"role": "user", "content": "What is 17 + 25? Use the add tool."}], tools=tools, tag="smoke_tool")
print(f"[tool] tool_calls={json.dumps(r.tool_calls)} content={r.content[:80]!r} cost=${r.cost:.6f} latency={r.latency_s:.2f}s")
assert r.tool_calls and r.tool_calls[0]["function"]["name"] == "add", "tool-calling failed"
args = json.loads(r.tool_calls[0]["function"]["arguments"])
msgs = [{"role": "user", "content": "What is 17 + 25? Use the add tool."}, r.message,
        {"role": "tool", "tool_call_id": r.tool_calls[0]["id"], "content": str(args["a"] + args["b"])}]
r2 = c.chat(msgs, tools=tools, tag="smoke_tool")
print(f"[tool-roundtrip] content={r2.content[:120]!r} cost=${r2.cost:.6f} latency={r2.latency_s:.2f}s")
llm.budget_banner("smoke_llm(end)")
