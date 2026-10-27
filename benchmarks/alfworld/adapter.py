"""ALFWorld (TextWorld, text-only) adapter.

Splits: train | seen (= valid_seen, in-distribution eval) | unseen (= valid_unseen, out-of-distribution eval).
Data: `alfworld-download` → $ALFWORLD_DATA (default ~/.cache/alfworld). TEXT mode only; THOR/vision is never loaded.
Task id = game directory relative to $ALFWORLD_DATA/json_2.1.1/<split>/, e.g.
  "pick_and_place_simple-Book-None-Desk-308/trial_T20190908_...".
Success = TextWorld `won` flag after the episode.
"""
from __future__ import annotations

import glob
import os
import threading
from pathlib import Path

from benchmarks.common import BAD_ARGS, Result, StepResult, TaskSpec, run_with_env, tool_arg

BENCH = "alfworld"
SPLIT_DIRS = {"train": "train", "seen": "valid_seen", "unseen": "valid_unseen",
              "valid_seen": "valid_seen", "valid_unseen": "valid_unseen"}
MAX_STEPS = 50  # ReAct (Yao et al. 2023) ALFWorld budget
# TextWorld's PDDL logic uses one module-global TatSu parser that is not thread-safe
# ("IndexError: pop from empty list" under concurrent loads). All TextWorld calls are serialized; LLM calls,
# which dominate wall time, still run concurrently.
_TW_LOCK = threading.Lock()

# Guidance follows the plain ReAct ALFWorld setup: free-form text commands, the env answers
# "Nothing happens." for invalid ones. We expose the admissible-command list through a tool, which is
# standard in ALFWorld text agents and keeps the harness honest (no hidden PDDL state).
GUIDANCE = (
    "You are in a simulated household (ALFWorld, text mode). Interact using the `act` tool with one text "
    "command per call, e.g. 'go to countertop 1', 'take apple 1 from countertop 1', 'open fridge 1', "
    "'put apple 1 in/on fridge 1', 'heat apple 1 with microwave 1', 'cool X with fridge 1', 'clean X with "
    "sinkbasin 1', 'use desklamp 1', 'examine X', 'inventory', 'look'. If a command is invalid the "
    "environment replies 'Nothing happens.'. Call `admissible_commands` to see the currently valid commands. "
    "The episode ends automatically when the goal is achieved."
)

TOOLS = [
    {"type": "function", "function": {
        "name": "act", "description": "Execute one text command in the household environment.",
        "parameters": {"type": "object", "properties": {"command": {"type": "string",
                       "description": "A single text command, e.g. 'go to cabinet 1'."}},
                       "required": ["command"]}}},
    {"type": "function", "function": {
        "name": "admissible_commands", "description": "List the commands that are valid in the current state.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
]


def data_root() -> Path:
    return Path(os.environ.get("ALFWORLD_DATA", os.path.expanduser("~/.cache/alfworld")))


def _game_files(split: str) -> list[Path]:
    root = data_root() / "json_2.1.1" / SPLIT_DIRS[split]
    out = []
    for gf in sorted(glob.glob(str(root / "*" / "*" / "game.tw-pddl"))):
        d = Path(gf).parent
        # Same filters as alfworld.agents.environment.alfred_tw_env.AlfredTWEnv.collect_game_files:
        # need traj_data.json, and the "movable"/"Sliced" task variants are excluded.
        if not (d / "traj_data.json").exists():
            continue
        if "movable" in str(d) or "Sliced" in str(d):
            continue
        out.append(d)
    return out


def list_tasks(split: str) -> list[str]:
    root = data_root() / "json_2.1.1" / SPLIT_DIRS[split]
    return [str(d.relative_to(root)).replace(os.sep, "/") for d in _game_files(split)]


class AlfworldEnv:
    def __init__(self, task_id: str, split: str):
        import textworld
        import textworld.gym
        from alfworld.agents.environment.alfred_tw_env import AlfredDemangler, AlfredInfos

        self.task_id, self.split = task_id, split
        gamefile = str(data_root() / "json_2.1.1" / SPLIT_DIRS[split] / task_id / "game.tw-pddl")
        infos = textworld.EnvInfos(won=True, admissible_commands=True, extras=["gamefile"])
        with _TW_LOCK:
            env_id = textworld.gym.register_game(gamefile, infos, max_episode_steps=MAX_STEPS + 10,
                                                 wrappers=[AlfredDemangler(), AlfredInfos])
        with _TW_LOCK:
            _install_lib_pool()
            self.env = textworld.gym.make(env_id)
        self.won = False
        self.admissible: list[str] = []

    def reset(self) -> TaskSpec:
        with _TW_LOCK:
            obs, info = self.env.reset()
        self.admissible = list(info.get("admissible_commands") or [])
        # The initial observation contains the room description and "Your task is to: ...".
        goal = obs.split("Your task is to:")[-1].strip() if "Your task is to:" in obs else obs
        return TaskSpec(task_id=self.task_id, benchmark=BENCH, instruction=f"Your task is to: {goal}",
                        initial_observation=obs, tools=TOOLS, guidance=GUIDANCE, finish_tool="",
                        max_steps=MAX_STEPS, meta={"split": self.split})

    def step(self, tool: str, args: dict) -> StepResult:
        if tool == "admissible_commands":
            return StepResult("Valid commands:\n" + "\n".join(self.admissible))
        if tool != "act":
            return StepResult(f"Unknown tool '{tool}'. Use `act` or `admissible_commands`.")
        cmd = tool_arg(args, "command", "action", "cmd")
        if cmd is None:
            return StepResult(BAD_ARGS)
        cmd = str(cmd).strip()
        with _TW_LOCK:
            obs, score, done, info = self.env.step(cmd)
        self.won = bool(info.get("won")) or self.won
        self.admissible = list(info.get("admissible_commands") or [])
        return StepResult(obs, done=bool(done) or self.won, info={"won": self.won})

    def evaluate(self) -> tuple[bool, dict]:
        return self.won, {"won": self.won}

    def close(self) -> None:
        with _TW_LOCK:
            _release_downward_libs(self.env)
            self.env.close()


_LIB_POOL: list = []


def _pooled_load_lib():
    """Stand-in for fast_downward.load_lib: PddlEnv loads a private temp copy of libdownward.so (32 MB) per env
    and never unloads it, so the deleted copy stays mapped and holds disk until the process exits; long runs hit
    ENOSPC. Copies are recycled through a pool instead (dlclose segfaults at exit when a game is reloaded)."""
    return _LIB_POOL.pop() if _LIB_POOL else _orig_load_lib()


def _install_lib_pool() -> None:
    global _orig_load_lib
    import fast_downward
    if fast_downward.load_lib is not _pooled_load_lib:
        _orig_load_lib = fast_downward.load_lib
        fast_downward.load_lib = _pooled_load_lib


def _release_downward_libs(env) -> None:
    for e in getattr(getattr(env, "batch_env", None), "envs", None) or []:
        while e is not None:
            lib = getattr(e, "downward_lib", None)
            if lib is not None:
                e.downward_lib = None
                lib.cleanup()
                _LIB_POOL.append(lib)
                break
            e = getattr(e, "_wrapped_env", None)


def run_episode(task_id: str, harness, llm, split: str = "train", run_tag: str = "adhoc",
                max_steps: int | None = None) -> Result:
    return run_with_env(BENCH, task_id, lambda: AlfworldEnv(task_id, split), harness, llm,
                        run_tag=run_tag, max_steps=max_steps)
