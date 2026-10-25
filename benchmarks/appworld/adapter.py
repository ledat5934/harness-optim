"""AppWorld adapter (in-process, default serverless mode).

Splits: train | dev for development/smoke; test_normal | test_challenge for final eval only.
RULE (AppWorld): never inspect or tune on test_* tasks. `list_tasks` returns test ids only when
explicitly asked, and nothing in this repo prints test-task instructions.
Data: `appworld install && appworld download data` under $APPWORLD_ROOT.

The agent gets one native tool, `execute_python(code)`, mirroring the public simplified ReAct code agent
(experiments/code/simplified/react_code_agent.py, Apache-2.0): code runs in AppWorld's stateful REPL with the
`apis` object, and the task ends when the agent calls `apis.supervisor.complete_task(...)`.
Success = `world.evaluate().success` (all unit tests pass).
"""
from __future__ import annotations

import builtins
import io
import json
import os
import pathlib
import re
from pathlib import Path

from benchmarks.common import BAD_ARGS, Result, StepResult, TaskSpec, run_with_env, tool_arg

BENCH = "appworld"
MAX_STEPS = 40
EXPERIMENT = os.environ.get("APPWORLD_EXPERIMENT", "harnessgraph_smoke")

# Condensed from experiments/prompts/react_code_agent/instructions.txt (AppWorld, Apache-2.0),
# adapted from "write ```python``` blocks" to the execute_python tool.
GUIDANCE = """You are a super intelligent AI Assistant whose job is to achieve my day-to-day tasks completely autonomously.
You interact with apps (e.g. spotify, venmo, gmail, phone, file_system, supervisor) through their APIs in a stateful
Python REPL, by calling the `execute_python` tool. Variables persist between calls. Three key APIs to discover more:
  print(apis.api_docs.show_app_descriptions())
  print(apis.api_docs.show_api_descriptions(app_name='spotify'))
  print(apis.api_docs.show_api_doc(app_name='spotify', api_name='login'))
General instructions:
- Act fully on your own. Never invent or guess values; look them up via APIs. Never leave placeholders.
- When I omit details, choose any valid value. Avoid collateral damage: only do what I explicitly ask.
App-specific instructions:
- All my personal information (biographical details, credentials, addresses, cards) is in the Supervisor app.
- References to friends/family/any person refer to people in my phone's contacts list.
- Get the current date/time from datetime.now() or the phone app's get_current_date_and_time API.
- All requests are in a single default time zone. For periods like "yesterday" use full ranges 00:00:00-23:59:59.
- "File system" means the file_system app, not the machine's OS. Do not use OS modules.
- Paginated APIs: always loop over page_index until all results are processed.
Code-operation instructions:
- Always look at API specifications (apis.api_docs.show_api_doc) before calling an API.
- Write small chunks of code, one chunk per step, and check that it works before irreversible changes.
- Use only the provided app APIs, not Python packages for those services. Use print() to see results.
Task-completion instructions:
- You must call apis.supervisor.complete_task() after completing the task. If an answer is needed, pass it as
  answer=<value> (minimal: just the entity/number, numbers as digits). If no answer is required, omit it.
- If you cannot find a way, call apis.supervisor.complete_task(status="fail")."""

TOOLS = [{"type": "function", "function": {
    "name": "execute_python",
    "description": "Execute Python code in the AppWorld REPL (the `apis` object is available). Returns stdout or the error.",
    "parameters": {"type": "object", "properties": {"code": {"type": "string", "description": "Python code to run."}},
                   "required": ["code"]}}}]

TEST_SPLITS = {"test_normal", "test_challenge"}

# AppWorld's in-process SafetyGuard patches builtins.open / io.open / pathlib.Path.open during execute(), and its
# disable() does not restore io.open (it is missing from DISALLOWED_MODULE_TO_FUNCTION_NAMES), so the read-only
# open leaks into the rest of the process. We snapshot the originals at import time and restore them after every
# AppWorld call. AppWorld episodes must run SEQUENTIALLY (workers=1): the guard and the freezegun clock are
# process-global.
_ORIG_OPEN = (builtins.open, io.open, pathlib.Path.open)
_ORIG_FUNCS: list[tuple[object, str, object]] = []


def _snapshot_guarded() -> None:
    """Snapshot every function AppWorld's guard may patch (taken from its own table) before any world exists."""
    if _ORIG_FUNCS:
        return
    try:
        from appworld.common.safety_guard import DISALLOWED_MODULE_TO_FUNCTION_NAMES, SafetyGuard
    except Exception:
        return
    for mod_name, fnames in DISALLOWED_MODULE_TO_FUNCTION_NAMES.items():
        try:
            mod = SafetyGuard.module_by_path(mod_name)
        except Exception:
            continue
        for fn in fnames:
            if hasattr(mod, fn):
                _ORIG_FUNCS.append((mod, fn, getattr(mod, fn)))


def _restore_io() -> None:
    builtins.open, io.open, pathlib.Path.open = _ORIG_OPEN
    for mod, fn, f in _ORIG_FUNCS:
        setattr(mod, fn, f)


def list_tasks(split: str) -> list[str]:
    from appworld import load_task_ids
    return list(load_task_ids(split))


class AppWorldEnv:
    def __init__(self, task_id: str, split: str):
        _snapshot_guarded()
        from appworld import AppWorld
        self.task_id, self.split = task_id, split
        self.world = AppWorld(task_id=task_id, experiment_name=EXPERIMENT)

    def reset(self) -> TaskSpec:
        t = self.world.task
        sup = t.supervisor
        sup_d = sup if isinstance(sup, dict) else getattr(sup, "__dict__", {})
        who = (f"My name is: {sup_d.get('first_name', '')} {sup_d.get('last_name', '')}. My personal email is "
               f"{sup_d.get('email', '')} and phone number is {sup_d.get('phone_number', '')}.")
        apps = json.dumps([{"name": k, "description": v} for k, v in t.app_descriptions.items()], indent=1)
        return TaskSpec(task_id=self.task_id, benchmark=BENCH, instruction=f"{who}\nTask: {t.instruction}",
                        initial_observation=f"Available apps:\n{apps}", tools=TOOLS, guidance=GUIDANCE,
                        finish_tool="", max_steps=MAX_STEPS, meta={"split": self.split})

    def step(self, tool: str, args: dict) -> StepResult:
        if tool != "execute_python":
            return StepResult(f"Unknown tool '{tool}'. Use `execute_python`.")
        code = tool_arg(args, "code", "python", "source")
        if code is None:
            return StepResult(BAD_ARGS)
        # a ```python fence inside the argument is a SyntaxError in the sandbox
        m = re.fullmatch(r"\s*```[a-zA-Z0-9]*[ \t]*\n(.*?)\n?\s*```\s*", str(code), re.S)
        code = m.group(1) if m else str(code)
        try:
            out = self.world.execute(code)
        finally:
            _restore_io()
        return StepResult(out, done=self.world.task_completed())

    def evaluate(self) -> tuple[bool, dict]:
        try:
            tracker = self.world.evaluate()
        finally:
            _restore_io()
        d = tracker.to_dict() if hasattr(tracker, "to_dict") else {}
        success = bool(d.get("success", getattr(tracker, "success", False)))
        # Keep only aggregate counts; test-case details for test splits are never stored.
        info = {"success": success, "num_tests": d.get("num_tests"),
                "passes": len(d.get("passes", []) or []), "failures": len(d.get("failures", []) or []),
                "task_completed": self.world.task_completed()}
        return success, info

    def close(self) -> None:
        try:
            self.world.close()
        finally:
            _restore_io()


def run_episode(task_id: str, harness, llm, split: str = "dev", run_tag: str = "adhoc",
                max_steps: int | None = None) -> Result:
    return run_with_env(BENCH, task_id, lambda: AppWorldEnv(task_id, split), harness, llm,
                        run_tag=run_tag, max_steps=max_steps)
