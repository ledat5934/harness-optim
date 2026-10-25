"""Uniform benchmark contract shared by all adapters.

Each adapter module `benchmarks/<name>/adapter.py` exposes

    list_tasks(split) -> list[str]
    run_episode(task_id, harness, llm, split=None, max_steps=None) -> Result

`run_episode` builds the benchmark Env, hands it to `harness.run(task, env, llm, rec)`, then asks the
Env for the ground-truth verdict. Harness code never sees the evaluator. Adapters own only the environment
interface, the tool schemas and the per-benchmark instruction text.
"""
from __future__ import annotations

import io
import json
import time
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

ROOT = Path(__file__).resolve().parents[1]
TRAJ_DIR = ROOT / "results" / "trajectories"
VERBOSE = False  # debug mode: print every agent step and keep the hidden reasoning in the trajectory


@dataclass
class Result:
    success: bool
    steps: int
    tokens: int
    cost: float
    trajectory_path: str
    error: str | None = None
    task_id: str = ""
    benchmark: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class TaskSpec:
    task_id: str
    benchmark: str
    instruction: str           # task text shown to the agent
    initial_observation: str   # first env observation
    tools: list[dict]          # native OpenAI function schemas exposed by the env
    guidance: str = ""         # benchmark-specific usage notes (from the public reference agents)
    finish_tool: str = "finish"
    max_steps: int = 30
    meta: dict = field(default_factory=dict)


@dataclass
class StepResult:
    observation: str
    done: bool = False
    info: dict = field(default_factory=dict)


class Env(Protocol):
    def reset(self) -> TaskSpec: ...
    def step(self, tool: str, args: dict) -> StepResult: ...
    def evaluate(self) -> tuple[bool, dict]: ...
    def close(self) -> None: ...


class Recorder:
    """Collects a JSON trajectory for one episode; also accumulates token/cost from LLM responses."""

    def __init__(self, benchmark: str, task_id: str, run_tag: str):
        self.benchmark, self.task_id, self.run_tag = benchmark, task_id, run_tag
        self.events: list[dict] = []
        self.tokens = 0
        self.cost = 0.0
        self.llm_calls = 0
        self.steps = 0
        self.t0 = time.time()

    def llm(self, resp, **kw):
        self.tokens += resp.prompt_tokens + resp.completion_tokens
        self.cost += resp.cost
        self.llm_calls += 1
        ev = {"type": "llm", "content": resp.content, "tool_calls": resp.tool_calls,
              "pt": resp.prompt_tokens, "ct": resp.completion_tokens, "cost": resp.cost, **kw}
        if VERBOSE:
            ev["reasoning"] = (getattr(resp, "message", None) or {}).get("reasoning")
            calls = [f"{c['function']['name']}({c['function'].get('arguments', '')[:200]})" for c in resp.tool_calls or []]
            print(f"    [{self.task_id[:40]}] THINK {truncate(resp.content, 400)!r} CALLS {calls}", flush=True)
        self.events.append(ev)

    def step(self, tool: str, args: dict, observation: str, **kw):
        self.steps += 1
        self.events.append({"type": "step", "n": self.steps, "tool": tool, "args": args,
                            "observation": observation, **kw})
        if VERBOSE:
            print(f"    [{self.task_id[:40]}] STEP {self.steps} {tool} -> {truncate(observation, 400)!r}", flush=True)

    def note(self, kind: str, **kw):
        self.events.append({"type": kind, **kw})
        if VERBOSE and kind != "task":
            print(f"    [{self.task_id[:40]}] {kind.upper()} {truncate(json.dumps(kw, default=str), 400)}", flush=True)

    def dump(self, extra: dict) -> str:
        d = TRAJ_DIR / self.benchmark / self.run_tag  # parent: benchmark, child: one run
        d.mkdir(parents=True, exist_ok=True)
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in self.task_id)[:150]
        p = d / f"{safe}.json"
        # io.open: AppWorld's safety guard patches builtins.open / Path.open process-wide during execute()
        with io.open(p, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"benchmark": self.benchmark, "task_id": self.task_id, "run_tag": self.run_tag,
                                 "wall_s": round(time.time() - self.t0, 2), "tokens": self.tokens,
                                 "cost": self.cost, "llm_calls": self.llm_calls, "steps": self.steps,
                                 **extra, "events": self.events}, indent=1, default=str))
        return str(p)


def run_with_env(benchmark: str, task_id: str, make_env: Callable[[], Env], harness, llm,
                 run_tag: str = "adhoc", max_steps: int | None = None) -> Result:
    rec = Recorder(benchmark, task_id, run_tag)
    env = None
    success, err, info, outcome, instruction = False, None, {}, None, ""
    try:
        env = make_env()
        task = env.reset()
        instruction = task.instruction
        rec.note("task", instruction=task.instruction, max_steps=max_steps or task.max_steps)
        if max_steps:
            task.max_steps = max_steps
        outcome = harness.run(task, env, llm, rec)
        success, info = env.evaluate()
    except Exception as e:  # recorded, never masked: error is surfaced in Result.error
        err = f"{type(e).__name__}: {e}"
        rec.note("exception", error=err, tb=traceback.format_exc()[-3000:])
        # Budget exhaustion must stop the whole run, not just this episode.
        if type(e).__name__ == "BudgetExceeded":
            path = rec.dump({"success": False, "error": err})
            raise
    finally:
        if env is not None:
            try:
                env.close()
            except Exception:
                pass
    extra = {"success": success, "error": err, "eval_info": info,
             "outcome": asdict(outcome) if hasattr(outcome, "__dataclass_fields__") else outcome}
    path = rec.dump(extra)
    return Result(success=bool(success), steps=rec.steps, tokens=rec.tokens, cost=round(rec.cost, 8),
                  trajectory_path=path, error=err, task_id=task_id, benchmark=benchmark,
                  extra={"llm_calls": rec.llm_calls, "eval_info": info, "instruction": instruction[:2000]})


BAD_ARGS = ("Your tool-call arguments were not valid JSON (they may have been cut off by the output length limit). "
            "Re-send the call with valid JSON arguments; keep them shorter.")


def tool_arg(args: dict, key: str, *aliases: str):
    """args[key], else an alias, else the only string value (models sometimes rename the single argument).
    None when the call carried undecodable arguments ({"_raw": ...}, see tool_policy)."""
    if "_raw" in args:
        return None
    for k in (key, *aliases):
        if k in args:
            return args[k]
    strs = [v for v in args.values() if isinstance(v, str)]
    return strs[0] if len(strs) == 1 else ""


def truncate(text: str, limit: int = 6000) -> str:
    if text is None:
        return ""
    text = str(text)
    if len(text) <= limit:
        return text
    half = limit // 2
    return text[:half] + f"\n...[truncated {len(text) - limit} chars]...\n" + text[-half:]


SENSITIVE_EXTRA = ("instruction",)        # BrowseComp questions must not be published (canary)
SENSITIVE_EVAL = ("judge_raw",)           # judge output quotes the gold answer


def public_record(rec: dict) -> dict:
    """Copy of a result record that is safe to commit: no task text, no judge output (they stay in the local,
    git-ignored trajectory files)."""
    out = json.loads(json.dumps(rec, default=str))
    ex = out.get("extra") or {}
    for k in SENSITIVE_EXTRA:
        ex.pop(k, None)
    ev = ex.get("eval_info") or {}
    for k in SENSITIVE_EVAL:
        ev.pop(k, None)
    # per-case adapted prompts (B3) can quote the task text: keep only their length
    cm = ((out.get("bundle") or {}).get("context_mgmt") or {}).get("config") or {}
    if cm.get("extra_system"):
        cm["extra_system"] = f"<redacted: {len(cm['extra_system'])} chars>"
    return out


def instruction_of(rec: dict) -> str:
    """Task text for a record: in-memory field, else the 'task' event of its (local) trajectory."""
    ins = (rec.get("extra") or {}).get("instruction")
    if ins:
        return ins
    try:
        with io.open(rec["trajectory_path"], encoding="utf-8") as f:
            d = json.load(f)
        return next(e["instruction"] for e in d["events"] if e["type"] == "task")
    except Exception:
        return rec.get("task_id", "")


def append_jsonl(path: Path, rec: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with io.open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(public_record(rec), default=str) + "\n")
