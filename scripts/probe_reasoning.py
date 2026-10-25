"""Probe whether the model emits hidden reasoning and how OpenRouter's `reasoning` param affects it."""
import sys, pathlib, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import llm
llm.budget_banner("probe_reasoning")
c = llm.LLM()
q = [{"role": "user", "content": "Write a Python function that returns the n-th Fibonacci number. Reply with only the code."}]
for label, extra in [("default", None), ("effort_low", {"effort": "low"}), ("disabled", {"enabled": False}), ("max_tokens_256", {"max_tokens": 256})]:
    body_extra = {"reasoning": extra} if extra else {}
    orig = c._session.post
    def post(url, json=None, **kw):
        json = {**json, **body_extra}
        return orig(url, json=json, **kw)
    c._session.post = post
    r = c.chat(q, tag="probe_reasoning", max_tokens=3000)
    c._session.post = orig
    msg = r.message
    rs = msg.get("reasoning") or ""
    print(f"{label:15s} ct={r.completion_tokens} content_chars={len(r.content)} reasoning_chars={len(rs)} "
          f"finish={r.raw['choices'][0].get('finish_reason')} keys={sorted(msg.keys())} rt={(r.raw.get('usage') or {}).get('completion_tokens_details')}")
