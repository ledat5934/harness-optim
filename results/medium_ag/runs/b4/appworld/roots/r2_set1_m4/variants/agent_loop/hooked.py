"""agent_loop/hooked: H0 ReAct loop with mechanism hooks (B4; engine in baselines/hg/runtime.py)."""
from baselines.hg.runtime import HookedLoop


def register(reg):
    reg.register("agent_loop", "hooked", lambda c: HookedLoop(**c),
                 "H0 ReAct loop plus declarative precondition->action mechanisms (guidance, inject, annotate_obs, "
                 "reject_finish).", config_schema={"mechanisms": "list of mechanism specs"})
