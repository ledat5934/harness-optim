"""Slot Protocols for H0, the shared seed harness.

Modelled on ModularRSI's `terminus_2_modular/protocols.py`: five slots, one module per slot, composed into a
bundle by a Composer. The slots are renamed to the thesis slots, and the interfaces are synchronous and
benchmark-agnostic:

  agent_loop   : main think -> act -> observe coordinator (ModularRSI AgentLoop)
  context_mgmt : builds the message list sent to the LLM each step (ModularRSI ContextMgmt; MemoHarness D1 and
                 the within-episode part of D5)
  tool_policy  : which tools are exposed, how LLM output becomes actions, and how env results become observation
                 text (ModularRSI ToolSet + Observation; MemoHarness D2/D6)
  memory       : cross-episode knowledge recalled into context and updated after episodes (MemoHarness D5,
                 cross-episode part). Frozen at test time.
  verifier     : completion check: accept or reject a finish/done signal (ModularRSI VerificationLoop; D6)

The benchmark side is only `benchmarks.common.{TaskSpec, Env, StepResult}`. Slots never import adapters.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from benchmarks.common import StepResult, TaskSpec


@dataclass
class Action:
    tool: str
    args: dict
    call_id: str | None = None   # native tool_call id, when present
    raw: Any = None


@dataclass
class LoopState:
    step: int
    history: list[dict]               # OpenAI-format message history (excluding system)
    last_observation: str = ""
    finish_attempts: int = 0
    notes: dict = field(default_factory=dict)  # free scratch space for variants


@dataclass
class Verdict:
    accept: bool
    feedback: str = ""                # shown to the agent when rejected


@dataclass
class LoopOutcome:
    stopped: str                      # "done" | "finish" | "max_steps" | "no_progress" | "error"
    steps: int
    final_answer: str | None = None
    llm_calls: int = 0


@runtime_checkable
class ContextMgmt(Protocol):
    def build(self, system: str, task: TaskSpec, history: list[dict], memory_notes: str) -> list[dict]: ...


@runtime_checkable
class ToolPolicy(Protocol):
    def tools(self, task: TaskSpec) -> list[dict]: ...
    def parse(self, resp: Any, task: TaskSpec) -> list[Action]: ...
    def format_observation(self, action: Action, result: StepResult, task: TaskSpec) -> str: ...


@runtime_checkable
class Memory(Protocol):
    def recall(self, task: TaskSpec) -> str: ...
    def update(self, task: TaskSpec, outcome: LoopOutcome, success: bool | None, trajectory: dict | None) -> None: ...


@runtime_checkable
class Verifier(Protocol):
    def check(self, task: TaskSpec, action: Action | None, state: LoopState, env_done: bool) -> Verdict: ...


@runtime_checkable
class AgentLoop(Protocol):
    def run(self, task: TaskSpec, env: Any, h: Any, llm: Any, rec: Any) -> LoopOutcome: ...


SLOTS = ("agent_loop", "context_mgmt", "tool_policy", "memory", "verifier")
