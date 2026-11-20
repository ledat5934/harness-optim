"""verifier/unread_items: do not accept a first answer that rests only on shortened result lists.

Principle (precondition -> action):
  precondition  the agent calls the finish tool for the first time, at least `min_left` steps remain, and the task
                offers a tool that has never been called whose single required parameter is a field of the records
                the agent has been shown (a "read the full item" tool, found from the tool schemas)
  action        refuse the finish once and ask the agent to read the most relevant item in full before answering
Every other decision is delegated to the default verifier.
"""
from __future__ import annotations

import re

from h0.protocols import Verdict


def _shown_as_field(history, key: str) -> bool:
    """True when `key` is a field name of some record in a tool result (results may be cut, so no JSON parse)."""
    pat = re.compile(r'"%s"\s*:' % re.escape(key))
    return any(m.get("role") == "tool" and pat.search(m.get("content") or "") for m in history)


def _called(history) -> set:
    return {(tc.get("function") or {}).get("name") for m in history if m.get("role") == "assistant"
            for tc in m.get("tool_calls") or []}


class UnreadItems:
    def __init__(self, base, min_left: int = 3):
        self.base, self.min_left = base, min_left

    def check(self, task, action, state, env_done):
        v = self.base.check(task, action, state, env_done)
        if env_done or not v.accept or action is None or state.finish_attempts != 1:
            return v
        if task.max_steps - state.step < self.min_left:
            return v
        called = _called(state.history[:-1])  # the last assistant message is the finish call itself
        for t in task.tools:
            fn = t.get("function") or {}
            name = fn.get("name")
            if name == task.finish_tool or name in called:
                continue
            req = (fn.get("parameters") or {}).get("required") or []
            if len(req) != 1:
                continue
            if _shown_as_field(state.history, req[0]):
                return Verdict(False, f"You are answering from shortened results only. First call `{name}` with the "
                                      f"`{req[0]}` of the result most relevant to your answer, check the answer "
                                      f"against the full text, then finish.")
        return v


def register(reg):
    reg.register("verifier", "unread_items",
                 lambda c: UnreadItems(reg.instantiate("verifier", "default", {}), **c),
                 "Default verifier, plus: the first finish is refused once when a never-used tool could return, in "
                 "full, one of the records the agent has only seen in a result list.",
                 config_schema={"min_left": "int (default 3)"},
                 niche={"evidence": "read_full_item", "confirm": "single"})
