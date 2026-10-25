"""Trivial agent used only to prove each benchmark pipeline end to end (Phase 2).

It is deliberately bare: the env's instruction plus tools, one native tool call per step, no context management,
no memory, no verifier. It stops at the finish tool, when the env reports done, or after a few steps.
It is NOT H0 (see h0/).
"""
from __future__ import annotations

import json

from benchmarks.common import TaskSpec, truncate


class TrivialAgent:
    def __init__(self, max_steps: int = 6):
        self.max_steps = max_steps

    def run(self, task: TaskSpec, env, llm, rec):
        msgs = [{"role": "system", "content": "You are an agent. Use the provided tools to solve the task."},
                {"role": "user", "content": f"{task.instruction}\n\nInitial observation:\n{truncate(task.initial_observation, 4000)}"}]
        for _ in range(min(self.max_steps, task.max_steps)):
            r = llm.chat(msgs, tools=task.tools, tag=f"trivial:{task.benchmark}")
            rec.llm(r)
            msgs.append(_assistant(r))
            if not r.tool_calls:
                msgs.append({"role": "user", "content": "Please call one of the tools."})
                continue
            done = False
            for tc in r.tool_calls:
                name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                sr = env.step(name, args)
                rec.step(name, args, sr.observation)
                msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": truncate(sr.observation, 4000)})
                done = done or sr.done
            if done:
                return {"stopped": "done"}
        return {"stopped": "max_steps"}


def _assistant(r) -> dict:
    m = {"role": "assistant", "content": r.content or ""}
    if r.tool_calls:
        m["tool_calls"] = [{"id": tc["id"], "type": "function", "function": tc["function"]} for tc in r.tool_calls]
    return m
