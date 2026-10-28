"""verifier/default: accept the first completion signal (agent's finish tool call, or env done).

This is the plain behaviour of the public reference agents: AppWorld ends at complete_task, BrowseComp-Plus at
the final answer, ALFWorld when the env reports the goal reached. The only check is a non-empty answer when a
finish tool carries one. Evolved variants can add evidence checks, as ModularRSI's verification lineage does.
"""
from __future__ import annotations

from h0.protocols import Verdict


class AcceptFirst:
    def __init__(self, require_answer: bool = True):
        self.require_answer = require_answer

    def check(self, task, action, state, env_done):
        if env_done:
            return Verdict(True)
        if self.require_answer and action is not None and "answer" in action.args \
                and not str(action.args.get("answer") or "").strip():
            return Verdict(False, "The final answer is empty. Provide a complete final answer.")
        return Verdict(True)


def register(reg):
    reg.register("verifier", "default", lambda c: AcceptFirst(**c),
                 "Accept the first completion signal (finish tool or env done); only rejects an empty answer.",
                 config_schema={"require_answer": "bool (default true)"},
                 niche={"evidence": "none", "confirm": "single"})
