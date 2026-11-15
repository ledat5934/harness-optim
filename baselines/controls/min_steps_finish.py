"""Control for "is the gain only from searching longer?": a verifier that refuses EVERY finish before a fixed step,
whatever the answer says, with a neutral message. It makes the seed harness spend about as many steps as an evolved
harness without any idea of *when* more search is needed. Not a candidate: it is never proposed or merged.
"""
from __future__ import annotations

from h0.protocols import Verdict


class MinStepsFinish:
    def __init__(self, base, min_step: int = 0):
        self.base, self.min_step = base, int(min_step)

    def check(self, task, action, state, env_done):
        if not env_done and action is not None and task.finish_tool and action.tool == task.finish_tool \
                and state.step < min(self.min_step, task.max_steps - 2):
            return Verdict(False, "This answer has not been established. Continue investigating and provide a "
                                  "supported answer.")
        return self.base.check(task, action, state, env_done)


def register(reg):
    reg.register("verifier", "control_min_steps_finish",
                 lambda c: MinStepsFinish(reg.instantiate("verifier", "default", {}), **c),
                 "CONTROL: refuse any finish before `min_step` steps (equal-cost comparison, not a candidate).",
                 config_schema={"min_step": "int"})
