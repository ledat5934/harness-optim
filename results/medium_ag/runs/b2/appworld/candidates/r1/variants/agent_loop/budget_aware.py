"""agent_loop/budget_aware: ReAct loop with universal step budget awareness.

Like agent_loop/default, but budget warning nudges are not restricted to tasks
with an explicit finish tool. When remaining steps fall below budget_nudge_steps,
the agent is alerted about the imminent cutoff and instructed to prioritize completing
core required actions and wrapping up immediately.
"""
from __future__ import annotations

from h0.protocols import Action, LoopOutcome, LoopState


class BudgetAwareReActLoop:
    def __init__(self, max_no_action: int = 3, temperature: float | None = None, max_tokens: int | None = None,
                 budget_nudge_steps: int = 5):
        self.max_no_action, self.temperature, self.max_tokens = max_no_action, temperature, max_tokens
        self.budget_nudge_steps = budget_nudge_steps

    def run(self, task, env, h, llm, rec) -> LoopOutcome:
        state = LoopState(step=0, history=[{"role": "user", "content": _first_user(task)}])
        notes = h.memory.recall(task)
        no_action = 0
        llm_calls = 0
        nudged = False
        while state.step < task.max_steps:
            tools = h.tool_policy.tools(task)
            remaining = task.max_steps - state.step
            # Budget awareness: warn the agent when nearing the step limit regardless of finish_tool.
            if self.budget_nudge_steps and remaining <= self.budget_nudge_steps and not nudged and state.step > 0:
                if task.finish_tool:
                    state.history.append({"role": "user", "content":
                                          f"Only {remaining} step(s) left. Call `{task.finish_tool}` now with your best "
                                          f"final answer based on the evidence gathered so far."})
                else:
                    state.history.append({"role": "user", "content":
                                          f"Only {remaining} step(s) left before the step budget is exhausted. "
                                          f"Prioritize completing all required remaining actions and finish the task immediately."})
                nudged = True
            tool_choice = None
            if task.finish_tool and self.budget_nudge_steps and remaining == 1:
                only = [t for t in tools if t["function"]["name"] == task.finish_tool]
                if only:  # last step: offer and force the finish tool (native tool_choice, not JSON mode)
                    tools = only
                    tool_choice = {"type": "function", "function": {"name": task.finish_tool}}
            msgs = h.context_mgmt.build(h.system_prompt, task, state.history, notes)
            resp = llm.chat(msgs, tools=tools, tag=f"h:{task.benchmark}", tool_choice=tool_choice,
                            temperature=self.temperature, max_tokens=self.max_tokens)
            llm_calls += 1
            rec.llm(resp, step=state.step)
            actions = h.tool_policy.parse(resp, task)
            state.history.append(_assistant_msg(resp, actions))
            if not actions:
                no_action += 1
                if no_action >= self.max_no_action:
                    return LoopOutcome("no_progress", state.step, llm_calls=llm_calls)
                state.history.append({"role": "user", "content":
                                      "You did not call a tool. Continue by calling exactly one tool."})
                continue
            no_action = 0
            act = actions[0]
            offered = {t["function"]["name"] for t in tools}
            if act.tool not in offered:  # never execute a tool that was not offered this step
                for a in actions:
                    _tool_reply(state, a, f"Tool '{a.tool}' is not available now. Available: {sorted(offered)}.")
                state.step += 1
                continue
            # answer any extra native calls so the message history stays valid; only one action per step
            for extra in actions[1:]:
                if extra.call_id:
                    state.history.append({"role": "tool", "tool_call_id": extra.call_id,
                                          "content": "Ignored: only one tool call is executed per step."})
            if task.finish_tool and act.tool == task.finish_tool:
                state.finish_attempts += 1
                v = h.verifier.check(task, act, state, env_done=False)
                if not v.accept:
                    _tool_reply(state, act, f"Not accepted yet: {v.feedback}")
                    rec.note("verifier_reject", feedback=v.feedback, step=state.step)
                    state.step += 1
                    continue
                sr = env.step(act.tool, act.args)
                state.step += 1
                rec.step(act.tool, act.args, sr.observation)
                return LoopOutcome("finish", state.step, final_answer=str(act.args.get("answer", "")),
                                   llm_calls=llm_calls)
            sr = env.step(act.tool, act.args)
            state.step += 1
            obs = h.tool_policy.format_observation(act, sr, task)
            state.last_observation = obs
            rec.step(act.tool, act.args, sr.observation)
            _tool_reply(state, act, obs)
            if sr.done:
                v = h.verifier.check(task, act, state, env_done=True)
                if v.accept:
                    return LoopOutcome("done", state.step, llm_calls=llm_calls)
                state.history.append({"role": "user", "content": f"Verifier: {v.feedback}"})
        return LoopOutcome("max_steps", state.step, llm_calls=llm_calls)


def _first_user(task) -> str:
    parts = [task.instruction]
    if task.initial_observation:
        parts.append(f"Initial observation:\n{task.initial_observation}")
    return "\n\n".join(parts)


def _assistant_msg(resp, actions) -> dict:
    m = {"role": "assistant", "content": resp.content or ""}
    native = [a for a in actions if a.call_id]
    if native:
        m["tool_calls"] = [{"id": a.call_id, "type": "function", "function": a.raw["function"]} for a in native]
    return m


def _tool_reply(state, act: Action, text: str) -> None:
    if act.call_id:
        state.history.append({"role": "tool", "tool_call_id": act.call_id, "content": text})
    else:  # text-fallback action: feed the observation back as a user turn
        state.history.append({"role": "user", "content": f"Observation:\n{text}"})


def register(reg):
    reg.register("agent_loop", "budget_aware", lambda c: BudgetAwareReActLoop(**c),
                 "ReAct loop with universal step budget awareness: prompts the agent to prioritize and execute "
                 "remaining required actions when remaining steps fall to budget_nudge_steps, whether a finish_tool "
                 "is present or task completion is handled via environment actions.",
                 config_schema={"max_no_action": "int (default 3)", "temperature": "float|None (client default 0.0)",
                                "max_tokens": "int|None (client default 2048)",
                                "budget_nudge_steps": "int (default 5; step threshold to warn agent of remaining budget; 0 disables)"},
                 niche={"planning": "budget_aware", "recovery": "nudge", "parallel": "single"})
