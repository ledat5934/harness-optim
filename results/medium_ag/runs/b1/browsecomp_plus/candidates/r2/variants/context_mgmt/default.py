"""context_mgmt/default: system prompt + guidance + memory notes, pinned task message, sliding window.

Keeps the first user message (task) pinned and the most recent `keep_turns` assistant turns, together with the
tool/user replies that belong to them, so native tool-call pairing is never broken. When older turns are
dropped, a one-line marker says how many were elided. Each tool observation is also capped at `max_obs_chars`
inside the context. This matches the simplified AppWorld agent's `trimmed_messages` (drop the oldest
non-instruction messages when too long) and MemoHarness's stabilized default (sliding window that pins the
instruction).
"""
from __future__ import annotations

_DEFAULT_EXTRA_SYSTEM = (
    "Effective exploration and information retrieval guidelines:\n"
    "- Query formulation: Use concise key entities and specific search terms. Avoid wrapping full sentences in quotes, stuffing more than 2-3 constraints into a single query, or repeating failed query formulations.\n"
    "- Anti-stagnation & pivoting: If search results are repetitive, empty, or unhelpful, do not dwell on the same phrasing. Immediately pivot to an orthogonal clue, alternative keyword, or intermediate entity.\n"
    "- Multi-hop decomposition: Break down complex questions step-by-step. Identify intermediate entities or facts first.\n"
    "- Thorough inspection: When search snippets or listings offer relevant leads or document IDs, inspect the full document or content (e.g. using get_document if available) to extract complete, verified details.\n"
    "- Precision: Double-check answers against evidence before submitting final answers."
)


class SlidingWindow:
    def __init__(self, keep_turns: int = 30, max_obs_chars: int = 6000, extra_system: str = _DEFAULT_EXTRA_SYSTEM):
        self.keep_turns, self.max_obs_chars, self.extra_system = keep_turns, max_obs_chars, extra_system

    def build(self, system, task, history, memory_notes):
        sys_parts = [system]
        if task.guidance:
            sys_parts.append(task.guidance)
        if self.extra_system:
            sys_parts.append(self.extra_system)
        if memory_notes:
            sys_parts.append("Notes from previous experience:\n" + memory_notes)
        msgs = [{"role": "system", "content": "\n\n".join(sys_parts)}]
        if not history:
            return msgs
        head, rest = history[0], history[1:]
        # group: an assistant message followed by its tool/user replies
        groups, cur = [], []
        for m in rest:
            if m["role"] == "assistant" and cur:
                groups.append(cur)
                cur = []
            cur.append(m)
        if cur:
            groups.append(cur)
        dropped = max(0, len(groups) - self.keep_turns)
        kept = groups[dropped:]
        msgs.append(head)
        if dropped:
            msgs.append({"role": "user", "content": f"[{dropped} earlier steps omitted from context]"})
        for g in kept:
            for m in g:
                if m["role"] == "tool" and len(m.get("content") or "") > self.max_obs_chars:
                    c = m["content"]
                    m = {**m, "content": c[: self.max_obs_chars] + f"\n...[truncated {len(c) - self.max_obs_chars} chars]"}
                msgs.append(m)
        return msgs


def register(reg):
    reg.register("context_mgmt", "default", lambda c: SlidingWindow(**c),
                 "System prompt + benchmark guidance + memory notes; task message pinned; sliding window over "
                 "the last 30 assistant turns (tool pairs kept intact); observations capped at 6000 chars.",
                 config_schema={"keep_turns": "int (default 30)", "max_obs_chars": "int (default 6000)",
                                "extra_system": "str appended to the system prompt (default search/retrieval guidelines)"},
                 niche={"strategy": "sliding_window", "summarize": "no"})
