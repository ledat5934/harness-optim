"""Shared OpenRouter (OpenAI-compatible) client for the HarnessGraph smoke harness.

Features
- retries with exponential backoff + per-call timeout
- per-call logging (prompt/completion tokens, cost read from `usage`, latency) to results/llm_calls.jsonl
- global, *persistent* budget guard: cumulative spend lives in results/spend.json (cross-run, cross-process,
  guarded by a lock file). Calls are refused once spend >= MAX_USD, and also once remaining < 20% of MAX_USD
  (the "stop and report" floor from TASK.md).
- concurrency cap (threading semaphore, LLM_CONCURRENCY, default 4)
- plain text + native tool-calling only (no JSON-schema structured output)

The API key is read from the environment / .env only. It is never logged.
"""
from __future__ import annotations

import io
import json
import os
import random
import re
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"
SPEND_FILE = RESULTS / "spend.json"
CALL_LOG = RESULTS / "llm_calls.jsonl"
FLOOR_FRACTION = 0.20
# Debug mode (scripts/run_baselines.py --debug): FULL_LOG gets every request's messages + the full reply
# (content, hidden reasoning, tool calls); VERBOSE prints one line per call. Off by default.
FULL_LOG: Path | None = None
VERBOSE = False


def _load_dotenv(path: Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()  # project .env wins over a stale system-wide var


_load_dotenv()


class BudgetExceeded(RuntimeError):
    """Raised when the persistent budget (or the 20% floor) would be crossed."""


class LLMError(RuntimeError):
    pass


# ---------------------------------------------------------------- persistent spend
@contextmanager
def _spend_lock(timeout: float = 30.0):
    lock = SPEND_FILE.with_suffix(".lock")
    RESULTS.mkdir(parents=True, exist_ok=True)
    # loop counter instead of time.time(): AppWorld freezes the clock (freezegun) inside its process
    waited = 0
    while True:
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if waited * 0.05 > timeout:  # stale lock (crashed process)
                try:
                    os.remove(lock)
                except FileNotFoundError:
                    pass
                waited = 0
            time.sleep(0.05)
            waited += 1
    try:
        yield
    finally:
        os.close(fd)
        try:
            os.remove(lock)
        except FileNotFoundError:
            pass


def _read_spend() -> dict:
    if SPEND_FILE.exists():
        with io.open(SPEND_FILE, encoding="utf-8") as f:
            return json.loads(f.read())
    return {"total_usd": 0.0, "calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "by_tag": {}}


def get_spend() -> dict:
    with _spend_lock():
        return _read_spend()


def _add_spend(cost: float, pt: int, ct: int, tag: str) -> dict:
    with _spend_lock():
        s = _read_spend()
        s["total_usd"] = round(s["total_usd"] + cost, 8)
        s["calls"] += 1
        s["prompt_tokens"] += pt
        s["completion_tokens"] += ct
        bt = s.setdefault("by_tag", {}).setdefault(tag, {"usd": 0.0, "calls": 0})
        bt["usd"] = round(bt["usd"] + cost, 8)
        bt["calls"] += 1
        s["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        tmp = SPEND_FILE.with_suffix(".tmp")
        # io.open, not builtins.open/Path.open: AppWorld's in-process safety guard patches those globally
        with io.open(tmp, "w", encoding="utf-8") as f:
            f.write(json.dumps(s, indent=2))
        os.replace(tmp, SPEND_FILE)
        return s


def max_usd() -> float:
    return float(os.environ.get("MAX_USD", "1.0"))


def remaining_usd() -> float:
    return max_usd() - get_spend()["total_usd"]


def budget_banner(script: str = "", exit_if_low: bool = True) -> float:
    """Print remaining budget; exit(3) if below the 20% floor (TASK.md rule)."""
    s = get_spend()
    rem = max_usd() - s["total_usd"]
    print(f"[budget] {script} spent=${s['total_usd']:.6f} of MAX_USD=${max_usd():.2f} "
          f"remaining=${rem:.6f} ({100 * rem / max_usd():.1f}%) calls={s['calls']}", flush=True)
    if exit_if_low and rem < FLOOR_FRACTION * max_usd():
        print("[budget] remaining < 20% of MAX_USD -> stopping, report to user.", flush=True)
        raise SystemExit(3)
    return rem


# ---------------------------------------------------------------- client
@dataclass
class LLMResponse:
    content: str
    tool_calls: list[dict]
    message: dict
    prompt_tokens: int
    completion_tokens: int
    cost: float
    latency_s: float
    raw: dict = field(repr=False, default_factory=dict)


class LLM:
    def __init__(self, model: str | None = None, base_url: str | None = None, timeout: float = 120.0,
                 max_retries: int = 5, concurrency: int | None = None, temperature: float = 0.0,
                 max_tokens: int = 2048):
        self.model = model or os.environ.get("LLM_MODEL", "inclusionai/ling-3.0-flash")
        self.base_url = (base_url or os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")).rstrip("/")
        self.api_key = os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise LLMError("OPENROUTER_API_KEY not set (put it in .env)")
        # long generations on slower gateway models (antigravity gemini flash: ~6k tokens in 75-120 s) outlast 120 s
        self.timeout = float(os.environ.get("LLM_TIMEOUT", timeout))
        # rate limits (HTTP 429) under many parallel processes outlast 5 retries (~30 s); LLM_MAX_RETRIES raises
        # the count (backoff 1, 2, 4, ... capped at 60 s, so 8 retries wait about 3 minutes in total)
        self.max_retries = int(os.environ.get("LLM_MAX_RETRIES", max_retries))
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._sem = threading.BoundedSemaphore(concurrency or int(os.environ.get("LLM_CONCURRENCY", "4")))
        self._session = requests.Session()

    def _check_budget(self):
        rem = remaining_usd()
        if rem <= 0:
            raise BudgetExceeded(f"MAX_USD={max_usd()} exhausted")
        if rem < FLOOR_FRACTION * max_usd():
            raise BudgetExceeded(f"remaining ${rem:.4f} < 20% floor of MAX_USD={max_usd()}")

    def chat(self, messages: list[dict], tools: list[dict] | None = None, tag: str = "untagged",
             temperature: float | None = None, max_tokens: int | None = None,
             tool_choice: Any = None, stop: list[str] | None = None, reasoning: dict | None = None,
             fallback_no_reasoning: bool = False) -> LLMResponse:
        """`reasoning` is passed to OpenRouter as-is. The model emits hidden reasoning; on long generation prompts
        it can spend the whole max_tokens budget there and return empty content (finish_reason=length). With
        `fallback_no_reasoning=True`, an empty reply (no content, no tool calls) or one cut at max_tokens is retried
        once with reasoning={"enabled": False} (a cut one with twice the budget); the retry is logged under tag "<tag>:noreason"."""
        r = self._chat(messages, tools, tag, temperature, max_tokens, tool_choice, stop, reasoning)
        finish = ((r.raw or {}).get("choices") or [{}])[0].get("finish_reason")
        empty = not (r.content or "").strip() and not r.tool_calls
        if fallback_no_reasoning and (empty or finish in ("length", "max_tokens")):
            # a reply cut at max_tokens is retried too: on gateways that hide reasoning (antigravity gemini) the
            # thinking eats the budget and only a fragment of the answer comes back, with finish_reason=max_tokens
            r = self._chat(messages, tools, tag + ":noreason", temperature,
                           max_tokens if empty else 2 * (max_tokens or self.max_tokens), tool_choice, stop,
                           {"enabled": False})
        return r

    def _chat(self, messages, tools, tag, temperature, max_tokens, tool_choice, stop, reasoning) -> LLMResponse:
        self._check_budget()
        body: dict[str, Any] = {
            "model": self.model,
            "messages": _valid_tool_args(messages),
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": max_tokens or self.max_tokens,
            "usage": {"include": True},  # OpenRouter usage accounting -> usage.cost
            "stream": False,  # 9router streams by default for some providers (antigravity) unless told not to
        }
        if tools:
            body["tools"] = tools
            if tool_choice is not None:
                if "openrouter.ai" not in self.base_url and isinstance(tool_choice, dict) \
                        and "function" in tool_choice:
                    # 9router forwards tool_choice to the Codex Responses API verbatim, which takes the flat form
                    # and silently ignores the nested chat-completions one
                    tool_choice = {"type": "function", "name": tool_choice["function"]["name"]}
                body["tool_choice"] = tool_choice
        if stop:
            body["stop"] = stop
        if reasoning is not None and "openrouter.ai" in self.base_url:
            body["reasoning"] = reasoning
        elif reasoning is not None:  # OpenAI-style gateways reject OpenRouter's `reasoning` object
            off = "low" if self.model.startswith("ag/") else "none"  # antigravity rejects "none"; "low" hides thinking
            body["reasoning_effort"] = off if reasoning.get("enabled") is False else reasoning.get("effort", "low")
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
                   "X-Title": "HarnessGraph-smoke"}
        last_err: str | None = None
        with self._sem:
            attempt = 0
            while attempt < self.max_retries:
                t0 = time.time()
                try:
                    r = self._session.post(f"{self.base_url}/chat/completions", json=body, headers=headers,
                                           timeout=self.timeout)
                    latency = time.time() - t0
                    wait = _quota_reset_s(r)
                    if wait is not None:  # subscription quota window exhausted: wait for the reset, keep the attempt
                        _log({"event": "quota_wait", "tag": tag, "sleep": wait, "error": r.text[:300]})
                        time.sleep(wait)
                        continue
                    if r.status_code in (408, 429, 500, 502, 503, 504, 520, 522, 524):  # 52x: provider-side (Cloudflare) errors
                        last_err = f"HTTP {r.status_code}: {r.text[:300]}"
                        raise _Retry()
                    if r.status_code != 200:
                        raise LLMError(f"HTTP {r.status_code}: {r.text[:500]}")
                    data = r.json()
                    if "error" in data:
                        last_err = f"API error: {str(data['error'])[:300]}"
                        raise _Retry()
                    if not data.get("choices"):
                        last_err = f"no choices: {str(data)[:300]}"
                        raise _Retry()
                    return self._finish(data, latency, tag, body)
                except (_Retry, requests.Timeout, requests.ConnectionError, json.JSONDecodeError) as e:
                    if not isinstance(e, _Retry):
                        last_err = f"{type(e).__name__}: {e}"
                    sleep = min(60, 2 ** attempt + random.random())
                    _log({"event": "retry", "tag": tag, "attempt": attempt, "error": last_err, "sleep": sleep})
                    time.sleep(sleep)
                    attempt += 1
        raise LLMError(f"failed after {self.max_retries} retries: {last_err}")

    def _finish(self, data: dict, latency: float, tag: str, body: dict | None = None) -> LLMResponse:
        usage = data.get("usage") or {}
        pt = int(usage.get("prompt_tokens") or 0)
        ct = int(usage.get("completion_tokens") or 0)
        cost = usage.get("cost")
        cost_source = "usage.cost"
        if cost is None and "openrouter.ai" not in self.base_url:
            # a subscription gateway (e.g. 9router -> Codex) bills no per-call price; usage is tracked in tokens
            cost, cost_source = 0.0, "unpriced_gateway"
        elif cost is None:  # never guess prices: look the generation up instead
            cost, cost_source = self._lookup_generation_cost(data.get("id")), "generation_endpoint"
        cost = float(cost or 0.0)
        s = _add_spend(cost, pt, ct, tag)
        msg = data["choices"][0]["message"]
        _log({"event": "call", "tag": tag, "model": data.get("model", self.model), "id": data.get("id"),
              "provider": data.get("provider"), "prompt_tokens": pt, "completion_tokens": ct, "cost": cost,
              "cost_source": cost_source, "latency_s": round(latency, 3),
              "finish_reason": data["choices"][0].get("finish_reason"), "cum_usd": s["total_usd"]})
        if FULL_LOG is not None:
            _log_full(tag, body or {}, data, msg, pt, ct, cost, latency)
        if VERBOSE:
            calls = [c.get("function", {}).get("name") for c in msg.get("tool_calls") or []]
            print(f"      [llm {tag}] pt={pt} ct={ct} ${cost:.5f} finish={data['choices'][0].get('finish_reason')} "
                  f"calls={calls} content={(msg.get('content') or '')[:160]!r}", flush=True)
        return LLMResponse(content=msg.get("content") or "", tool_calls=msg.get("tool_calls") or [], message=msg,
                           prompt_tokens=pt, completion_tokens=ct, cost=cost, latency_s=latency, raw=data)

    def _lookup_generation_cost(self, gen_id: str | None) -> float | None:
        if not gen_id:
            return None
        for _ in range(5):
            time.sleep(1.0)
            r = self._session.get(f"{self.base_url}/generation", params={"id": gen_id},
                                  headers={"Authorization": f"Bearer {self.api_key}"}, timeout=30)
            if r.status_code == 200:
                return (r.json().get("data") or {}).get("total_cost")
        return None


class _Retry(Exception):
    pass


_RESET = re.compile(r"(?:resets?_in_seconds|resets?_after_seconds)\W+(\d+)"
                    r"|reset (?:after|in) (?:(\d+)h\s*)?(?:(\d+)m\s*)?(?:(\d+)s)?", re.I)
_QUOTA = re.compile(r"usage.?limit|quota|rate.?limit", re.I)


def _quota_reset_s(r) -> float | None:
    """Seconds to wait when a subscription gateway (9router -> Codex) reports an exhausted usage window: an HTTP 429
    that names the quota and its reset time. Plain transient errors keep the normal retry path."""
    if r.status_code not in (429, 503) or not _QUOTA.search(r.text or ""):
        return None
    m = _RESET.search(r.text or "")
    if not m or not any(m.groups()):
        return 300.0
    secs = float(m.group(1)) if m.group(1) else \
        3600 * int(m.group(2) or 0) + 60 * int(m.group(3) or 0) + int(m.group(4) or 0)
    return min(6 * 3600.0, secs + 5)


def _valid_tool_args(messages: list[dict]) -> list[dict]:
    """Some OpenRouter upstreams (e.g. DeepInfra) reject a request whose history contains an assistant tool call
    with non-JSON `arguments` (HTTP 400), while others accept it. The model occasionally emits such arguments,
    and the harness echoes them back. Transport-level fix: wrap invalid arguments as {"_raw": "..."}. The
    harness's own messages are not modified (copies are sent)."""
    out = []
    for m in messages:
        tcs = m.get("tool_calls") if isinstance(m, dict) else None
        if tcs:
            fixed = []
            for tc in tcs:
                fn = dict(tc.get("function") or {})
                a = fn.get("arguments")
                if isinstance(a, str):
                    try:
                        json.loads(a or "{}")
                    except json.JSONDecodeError:
                        fn["arguments"] = json.dumps({"_raw": a})
                fixed.append({**tc, "function": fn})
            m = {**m, "tool_calls": fixed}
        out.append(m)
    return out


_log_lock = threading.Lock()


def _log_full(tag: str, body: dict, data: dict, msg: dict, pt: int, ct: int, cost: float, latency: float) -> None:
    """Debug only: the complete request messages and reply. The API key is in the headers, never in `body`."""
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "tag": tag, "model": data.get("model"),
           "provider": data.get("provider"), "pt": pt, "ct": ct, "cost": cost, "latency_s": round(latency, 3),
           "finish_reason": data["choices"][0].get("finish_reason"),
           "request": {"messages": body.get("messages"), "tools": [t["function"]["name"] for t in body.get("tools") or []],
                       "tool_choice": body.get("tool_choice"), "temperature": body.get("temperature"),
                       "max_tokens": body.get("max_tokens"), "reasoning": body.get("reasoning")},
           "response": {"content": msg.get("content"), "reasoning": msg.get("reasoning"),
                        "tool_calls": msg.get("tool_calls")}}
    FULL_LOG.parent.mkdir(parents=True, exist_ok=True)
    with _log_lock, io.open(FULL_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")


def _log(rec: dict) -> None:
    rec["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    RESULTS.mkdir(parents=True, exist_ok=True)
    with _log_lock, io.open(CALL_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
