"""Terminal-Bench 2.0 adapter (plain Docker, same task dirs and verifier as Harbor).

Task dirs come from `harbor download terminal-bench@2.0 --export -o data/tb2` (89 tasks). Each episode:
  reset    -> `docker run` the task's prebuilt image (task.toml [environment].docker_image, cpus, memory),
              `sleep infinity`, like Harbor's docker-compose-prebuilt.yaml; /logs/{agent,verifier} created.
  step     -> tool `bash(command, timeout_sec)`: one `docker exec bash -c` per call. The working directory
              persists between calls (a fresh process each time, so `export`s do not; write them to a file).
  evaluate -> copy tests/ to /tests, run /tests/test.sh as Harbor does (stdout to /logs/verifier/test-stdout.txt),
              reward = /logs/verifier/reward.txt (or reward.json "reward"); success = reward >= 1.
The agent wall-clock limit is task.toml [agent].timeout_sec (as in Harbor); steps are capped at MAX_STEPS.

Sandbox infra (same for every compared harness, see scripts/tb2_infra.sh): outbound TLS is re-terminated here,
so the sandbox CA is mounted read-only and the usual CA env vars point at it.
Splits: benchmarks/terminal_bench2/splits.json (scripts/make_tb2_splits.py: seeded shuffle, no hand-picking).
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import threading
import time
import tomllib
import uuid
from pathlib import Path

from benchmarks.common import BAD_ARGS, Result, StepResult, TaskSpec, run_with_env, tool_arg

BENCH = "terminal_bench2"
ROOT = Path(__file__).resolve().parents[2]
TASK_ROOT = Path(os.environ.get("TB2_TASK_ROOT", ROOT / "data" / "tb2" / "terminal-bench"))
SPLITS_FILE = Path(__file__).with_name("splits.json")
MAX_STEPS = int(os.environ.get("TB2_MAX_STEPS", "100"))
DEFAULT_CMD_TIMEOUT = 180
MAX_CMD_TIMEOUT = 1800
CA_HOST = os.environ.get("TB2_CA_FILE", "/root/.ccr/ca-bundle.crt")
CA_CT = "/usr/local/share/sandbox-proxy-ca.crt"
CA_VARS = ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "PIP_CERT", "NODE_EXTRA_CA_CERTS",
           "GIT_SSL_CAINFO")
MIN_FREE_GB = float(os.environ.get("TB2_MIN_FREE_GB", "3"))
CWD_FILE = "/tmp/.agent_cwd"

GUIDANCE = """You are an autonomous agent solving a task inside a Linux container, using a bash shell.
- Use the `bash` tool to run commands. Each call runs in a fresh bash process; the working directory persists
  between calls, environment variables do not (put them in a file and `source` it if you need them).
- Commands time out after `timeout_sec` (default 180 s, max 1800 s). Start long-running services in the background
  with `nohup ... > /tmp/x.log 2>&1 &` so the call returns.
- There is no interactive terminal: do not start editors or pagers; write files with heredocs or scripts.
- Explore before acting, verify your result yourself (run the program, check the files the task asks for).
- When the task is complete, call `finish`. The container is graded after you finish, by hidden tests."""

TOOLS = [
    {"type": "function", "function": {
        "name": "bash",
        "description": "Run a bash command in the task container. Returns combined stdout/stderr and the exit code.",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string", "description": "The bash command(s) to run."},
            "timeout_sec": {"type": "integer", "description": "Timeout in seconds (default 180, max 1800)."}},
            "required": ["command"]}}},
    {"type": "function", "function": {
        "name": "finish",
        "description": "Declare the task complete. The container is then graded.",
        "parameters": {"type": "object", "properties": {
            "summary": {"type": "string", "description": "One-line summary of what was done."}}}}},
]

_pull_lock = threading.Lock()
_pulled: set[str] = set()


def _docker(*args: str, timeout: float | None = None, input: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout, input=input,
                          errors="replace")


def list_tasks(split: str) -> list[str]:
    if split == "all":
        return sorted(p.name for p in TASK_ROOT.iterdir() if (p / "task.toml").exists())
    return list(json.loads(SPLITS_FILE.read_text(encoding="utf-8"))[split])


def task_config(task_id: str) -> dict:
    return tomllib.loads((TASK_ROOT / task_id / "task.toml").read_text(encoding="utf-8"))


def _free_gb(path: str = "/var/lib/docker") -> float:
    try:
        return shutil.disk_usage(path).free / 1e9
    except Exception:
        return 1e9


def _ensure_image(image: str) -> None:
    with _pull_lock:
        if _free_gb() < MIN_FREE_GB:
            _docker("image", "prune", "-a", "-f", timeout=600)  # images not used by a running container
            _pulled.clear()
        if image in _pulled or _docker("image", "inspect", image, timeout=60).returncode == 0:
            _pulled.add(image)
            return
        for attempt in range(3):
            p = _docker("pull", "-q", image, timeout=1800)
            if p.returncode == 0:
                _pulled.add(image)
                return
            time.sleep(10 * (attempt + 1))
        raise RuntimeError(f"docker pull failed: {p.stderr[-500:]}")


class TB2Env:
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.dir = TASK_ROOT / task_id
        self.cfg = task_config(task_id)
        self.name = f"hx_{uuid.uuid4().hex[:12]}"
        self.started = False
        self.t0 = None
        self.agent_timeout = float(self.cfg.get("agent", {}).get("timeout_sec", 900))
        self.counts = {"bash": 0, "timeouts": 0}
        self.finished = False

    # ---------------------------------------------------------------- lifecycle
    def _ca_args(self) -> list[str]:
        if not Path(CA_HOST).exists():
            return []
        out = ["-v", f"{CA_HOST}:{CA_CT}:ro"]
        for k in CA_VARS:
            out += ["-e", f"{k}={CA_CT}"]
        return out

    def reset(self) -> TaskSpec:
        env = self.cfg.get("environment", {})
        image = env["docker_image"]
        _ensure_image(image)
        args = ["run", "-d", "--name", self.name, "--label", "harness-optim=tb2"]
        if env.get("cpus"):
            args += ["--cpus", str(env["cpus"])]
        if env.get("memory"):
            args += ["--memory", str(env["memory"]).replace("G", "g").replace("M", "m")]
        args += self._ca_args() + [image, "sh", "-c", "sleep infinity"]
        p = _docker(*args, timeout=300)
        if p.returncode != 0:
            raise RuntimeError(f"docker run failed: {p.stderr[-500:]}")
        self.started = True
        _docker("exec", "-u", "root", self.name, "sh", "-c", "mkdir -p /logs/agent /logs/verifier && chmod 777 /logs "
                "/logs/agent /logs/verifier", timeout=60)
        self.t0 = time.time()
        instruction = (self.dir / "instruction.md").read_text(encoding="utf-8")
        first = self._exec("pwd; ls -la", 60)
        return TaskSpec(task_id=self.task_id, benchmark=BENCH, instruction=instruction,
                        initial_observation=f"$ pwd; ls -la\n{first}", tools=TOOLS, guidance=GUIDANCE,
                        finish_tool="finish", max_steps=MAX_STEPS,
                        meta={"agent_timeout_sec": self.agent_timeout,
                              "category": self.cfg.get("metadata", {}).get("category")})

    def close(self) -> None:
        if self.started:
            _docker("rm", "-f", self.name, timeout=120)
            self.started = False

    # ---------------------------------------------------------------- actions
    def _exec(self, command: str, timeout: int) -> str:
        wrapped = (f'cd "$(cat {CWD_FILE} 2>/dev/null || pwd)" 2>/dev/null; '
                   f'{command}\n__ec=$?; pwd > {CWD_FILE} 2>/dev/null; exit $__ec')
        inner = f"timeout -k 5 {timeout} bash -c {shlex.quote(wrapped)}"
        script = f"if command -v timeout >/dev/null 2>&1; then {inner}; else bash -c {shlex.quote(wrapped)}; fi"
        try:
            p = _docker("exec", self.name, "bash", "-c", script, timeout=timeout + 30)
        except subprocess.TimeoutExpired:
            self.counts["timeouts"] += 1
            return f"[command timed out after {timeout}s]"
        out = (p.stdout or "") + (p.stderr or "")
        if p.returncode == 124:
            self.counts["timeouts"] += 1
            return f"{out}\n[command timed out after {timeout}s]"
        return f"{out}\n[exit code {p.returncode}]"

    def step(self, tool: str, args: dict) -> StepResult:
        elapsed = time.time() - (self.t0 or time.time())
        if elapsed > self.agent_timeout:
            return StepResult(f"[agent time limit of {int(self.agent_timeout)}s reached; the task is graded now]",
                              done=True, info={"timeout": True})
        if tool == "finish":
            self.finished = True
            return StepResult("Task marked complete; it will be graded now.", done=True)
        if tool != "bash":
            return StepResult(f"Unknown tool '{tool}'. Use `bash` or `finish`.")
        cmd = tool_arg(args, "command", "cmd", "script", "keystrokes")
        if cmd is None:
            return StepResult(BAD_ARGS)
        try:
            to = int(args.get("timeout_sec") or DEFAULT_CMD_TIMEOUT)
        except (TypeError, ValueError):
            to = DEFAULT_CMD_TIMEOUT
        to = max(1, min(MAX_CMD_TIMEOUT, to, int(self.agent_timeout - elapsed) + 1))
        self.counts["bash"] += 1
        return StepResult(self._exec(str(cmd), to))

    # ---------------------------------------------------------------- grading
    def evaluate(self) -> tuple[bool, dict]:
        info = {"tool_counts": dict(self.counts), "finished": self.finished,
                "agent_wall_s": round(time.time() - (self.t0 or time.time()), 1)}
        tests = self.dir / "tests"
        p = _docker("cp", f"{tests}/.", f"{self.name}:/tests", timeout=300)
        if p.returncode != 0:
            _docker("exec", "-u", "root", self.name, "mkdir", "-p", "/tests", timeout=60)
            p = _docker("cp", f"{tests}/.", f"{self.name}:/tests", timeout=300)
            if p.returncode != 0:
                raise RuntimeError(f"copy tests failed: {p.stderr[-300:]}")
        vcfg = self.cfg.get("verifier", {})
        vt = int(float(vcfg.get("timeout_sec", 900)))
        envargs = []
        for k, v in (vcfg.get("env") or {}).items():
            envargs += ["-e", f"{k}={v}"]
        if Path(CA_HOST).exists():
            for k in CA_VARS:
                envargs += ["-e", f"{k}={CA_CT}"]
        _docker("exec", "-u", "root", self.name, "chmod", "+x", "/tests/test.sh", timeout=60)
        t0 = time.time()
        try:
            _docker("exec", *envargs, self.name, "bash", "-c",
                    "bash /tests/test.sh > /logs/verifier/test-stdout.txt 2>&1", timeout=vt + 60)
        except subprocess.TimeoutExpired:
            info["verifier_timeout"] = True
        info["verifier_wall_s"] = round(time.time() - t0, 1)
        r = _docker("exec", self.name, "sh", "-c", "cat /logs/verifier/reward.txt 2>/dev/null || "
                    "cat /logs/verifier/reward.json 2>/dev/null", timeout=60).stdout.strip()
        reward = 0.0
        try:
            reward = float(r)
        except ValueError:
            try:
                reward = float(json.loads(r).get("reward", 0))
            except Exception:
                info["reward_parse_error"] = r[:200]
        # Only aggregate counts are kept: the hidden tests' messages never reach the trajectory or any proposer.
        tail = _docker("exec", self.name, "sh", "-c", "tail -c 400 /logs/verifier/test-stdout.txt",
                       timeout=60).stdout
        counts = {k: int(n) for n, k in re.findall(r"(\d+) (passed|failed|error|errors)\b", tail)}
        info.update({"reward": reward, "tests": counts})
        return reward >= 1.0, info


def run_episode(task_id: str, harness, llm, split: str = "train", run_tag: str = "adhoc",
                max_steps: int | None = None) -> Result:
    return run_with_env(BENCH, task_id, lambda: TB2Env(task_id), harness, llm, run_tag=run_tag,
                        max_steps=max_steps)
