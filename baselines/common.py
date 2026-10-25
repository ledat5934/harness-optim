"""Shared infrastructure for the three baselines (B1/B2/B3) under one common protocol.

Common protocol (mirrors ModularRSI's reproduction protocol, scaled to smoke size):
  * same seed H0 (h0/), same model (llm.py), same train/val/test task ids per benchmark (protocol_tasks())
  * same number of evolution rounds and the same execution budget per round
  * no web search anywhere (proposers only see local files)
  * the evolved harness is frozen before test; test runs never write back into the method state

A *candidate* is a harness root directory: a copy of `h0/variants/**`, an optional `bundle.json` and
`system_prompt.txt`, and `meta.json`. All candidates run through the same `LazyHarness` + adapter path.
"""
from __future__ import annotations

import dataclasses
import hashlib
import importlib
import json
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import llm as llm_mod  # noqa: E402
from benchmarks.common import append_jsonl  # noqa: E402
from h0.compose import LazyHarness, get_registry  # noqa: E402
from h0.registry import H0_ROOT  # noqa: E402

OUT = ROOT / "results"          # per-method result jsonl files; redirected by run_baselines.py --debug
RUNS = OUT / "runs"

# ---------------------------------------------------------------- protocol
SMOKE = {"n_train": 5, "n_val": 3, "n_test": 3, "n_check": 2, "rounds": 1, "workers": 3,
         "k": 3}  # K same-harness rolls per train task (ModularRSI router default k=3)

# Test splits per benchmark. ALFWorld: unseen (valid_unseen). AppWorld: test_normal (no inspection, only
# aggregate success is recorded). BrowseComp-Plus: the held-out part of our decrypted subset.
SPLITS = {
    "alfworld": {"train": "train", "test": "unseen"},
    "appworld": {"train": "train", "val": "dev", "test": "test_normal"},
    "browsecomp_plus": {"train": "dev", "test": "test"},
}


def protocol_tasks(bench: str, cfg: dict = SMOKE) -> dict[str, tuple[str, list[str]]]:
    """Deterministic task ids for train/val/test. Returns {phase: (split, [ids])}."""
    ad = adapter(bench)
    s = SPLITS[bench]
    tr = ad.list_tasks(s["train"])
    if bench == "alfworld":
        # interleave the 6 ALFWorld task types (deterministic) so train/val/test cover different types
        pool = _interleave_types(tr)
        train, val = pool[: cfg["n_train"]], pool[cfg["n_train"]: cfg["n_train"] + cfg["n_val"]]
        test = _interleave_types(ad.list_tasks(s["test"]))[: cfg["n_test"]]
        return {"train": (s["train"], train), "val": (s["train"], val), "test": (s["test"], test)}
    if bench == "appworld":
        train = tr[: cfg["n_train"]]
        val = ad.list_tasks(s["val"])[: cfg["n_val"]]
        test = ad.list_tasks(s["test"])[: cfg["n_test"]]   # ids only; contents never inspected
        return {"train": (s["train"], train), "val": (s["val"], val), "test": (s["test"], test)}
    # browsecomp_plus: dev = first 10 of the subset -> 5 train + 3 val; test = held-out ids
    train, val = tr[: cfg["n_train"]], tr[cfg["n_train"]: cfg["n_train"] + cfg["n_val"]]
    test = ad.list_tasks(s["test"])[: cfg["n_test"]]
    return {"train": (s["train"], train), "val": (s["train"], val), "test": (s["test"], test)}


def _interleave_types(ids: list[str]) -> list[str]:
    """Round-robin over ALFWorld task types (prefix before the first '-'), taking evenly spaced games of each."""
    by: dict[str, list[str]] = {}
    for t in ids:
        by.setdefault(t.split("-")[0], []).append(t)
    types = sorted(by)
    out, i = [], 0
    while len(out) < len(ids) and i < 50:
        for ty in types:
            lst = by[ty]
            j = (i * 37) % len(lst)  # deterministic spread inside each type
            if lst[j] not in out:
                out.append(lst[j])
        i += 1
    return out


def adapter(bench: str):
    return importlib.import_module(f"benchmarks.{bench}.adapter")


# ---------------------------------------------------------------- candidates
def new_candidate(dest: Path, parent: Path = H0_ROOT, meta: dict | None = None) -> Path:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    shutil.copytree(parent / "variants", dest / "variants",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for f in ("bundle.json", "system_prompt.txt"):
        if (parent / f).exists():
            shutil.copy2(parent / f, dest / f)
    (dest / "meta.json").write_text(json.dumps({"parent": str(parent), **(meta or {})}, indent=1))
    return dest


def tree_text(root: Path, max_chars: int | None = 60000) -> str:
    """All source of a harness root as one text blob (for proposers). max_chars=None: never truncated."""
    parts = []
    for f in sorted(list((root / "variants").rglob("*.py")) + [p for p in (root / "bundle.json",
                                                                          root / "system_prompt.txt") if p.exists()]):
        parts.append(f"### FILE: {f.relative_to(root).as_posix()}\n{f.read_text(encoding='utf-8')}")
    s = "\n\n".join(parts)
    return s if max_chars is None or len(s) <= max_chars else s[:max_chars] + "\n...[truncated]"


def tree_hash(root: Path) -> str:
    h = hashlib.sha256()
    for f in sorted((root / "variants").rglob("*.py")):
        h.update(f.relative_to(root).as_posix().encode())
        h.update(f.read_bytes())
    for f in ("bundle.json", "system_prompt.txt"):
        if (root / f).exists():
            h.update(f.encode())
            h.update((root / f).read_bytes())
    return h.hexdigest()[:12]


# ---------------------------------------------------------------- gates
def static_gate(root: Path) -> tuple[bool, str]:
    """Tier 1-3 of ModularRSI's smoke gate: syntax, isolated import + registry load, all 5 slots have
    'default' (or bundle-pinned) variants, offline toy-env run in a fresh subprocess."""
    code = f"""
import sys; sys.path.insert(0, {str(ROOT)!r})
from h0.registry import load_registry
from h0.compose import root_bundle, build, validate_bundle
from h0.protocols import SLOTS
reg = load_registry({str(root)!r})
assert not reg.load_errors, reg.load_errors
b = root_bundle({str(root)!r}, reg)
h = build(b, reg)
sys.path.insert(0, {str(ROOT / 'tests')!r})
import test_h0_offline as t
from benchmarks.common import run_with_env
from h0.compose import LazyHarness
llm = t.FakeLLM([t.FakeResp('', [t.tc(1,'inc',{{}})]), t.FakeResp('', [t.tc(2,'inc',{{}})])] + [t.FakeResp('', [t.tc(9,'inc',{{}})])]*20)
r = run_with_env('toy','t1', lambda: t.ToyEnv(), LazyHarness({str(root)!r}), llm, run_tag='gate')
assert r.error is None, r.error
print('GATE_OK')
"""
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    ok = p.returncode == 0 and "GATE_OK" in p.stdout
    return ok, (p.stdout + p.stderr)[-1500:]


# ---------------------------------------------------------------- evaluation
def evaluate(bench: str, split: str, task_ids: list[str], root: Path | str, client, run_tag: str,
             out_jsonl: Path, composer=None, memory=None, workers: int = 3, label: dict | None = None,
             harness_factory: Callable[[], Any] | None = None) -> list[dict]:
    ad = adapter(bench)

    def one(tid):
        h = harness_factory() if harness_factory else LazyHarness(root, composer=composer, memory=memory)
        t0 = time.time()
        r = ad.run_episode(tid, h, client, split=split, run_tag=run_tag)
        rec = {**dataclasses.asdict(r), "split": split, "run_tag": run_tag, "root": str(root),
               "wall_s": round(time.time() - t0, 1), **(label or {})}
        if getattr(h, "last", None) is not None:
            rec["bundle"] = h.last.bundle
            rec["composer_meta"] = h.last.meta
        append_jsonl(out_jsonl, rec)
        print(f"    [{run_tag}] {tid[:60]:60s} ok={r.success} steps={r.steps} tok={r.tokens} "
              f"${r.cost:.5f} err={(r.error or '')[:80]}", flush=True)
        return rec

    if bench == "appworld" or workers <= 1:
        # AppWorld: signal-based timeouts need the main thread, and its safety guard / frozen clock are
        # process-global, so its episodes run sequentially.
        return [one(t) for t in task_ids]
    with ThreadPoolExecutor(max_workers=min(4, workers)) as ex:
        return list(ex.map(one, task_ids))


def better(v: float, tok: int, inc_v: float, inc_tok: int) -> bool:
    """Common selection rule for all baselines: correctness first, tokens as tiebreaker (MemoHarness-style)."""
    return v > inc_v or (v == inc_v and tok < inc_tok)


def score(recs: list[dict]) -> float:
    return sum(1 for r in recs if r["success"]) / max(1, len(recs))


def traj_stats(path: str) -> dict:
    """Turns and repeated-command ratio of one trajectory (ModularRSI router: n_episodes, repeated_command_ratio)."""
    try:
        ev = json.loads(Path(path).read_text(encoding="utf-8")).get("events", [])
    except Exception:
        return {"steps": 0, "repeat_ratio": 0.0}
    cmds = [json.dumps([e.get("tool"), e.get("args")], sort_keys=True, default=str) for e in ev if e["type"] == "step"]
    seen, rep = set(), 0
    for c in cmds:
        rep += c in seen
        seen.add(c)
    return {"steps": len(cmds), "repeat_ratio": rep / len(cmds) if cmds else 0.0}


def summarize_trajectory(path: str, max_events: int = 40, max_chars: int = 400, show_outcome: bool = True,
                         task_chars: int = 0) -> str:
    """Digest of one trajectory for proposers: last events, errors, tool observations. show_outcome=False hides
    the pass/fail verdict (reward-blind review, ModularRSI review gate). task_chars > 0 adds the first task_chars
    characters of the task instruction (B1; B2/B3 keep the default 0)."""
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as e:
        return f"(unreadable trajectory: {e})"
    ev = d.get("events", [])
    outcome = f"success={d.get('success')} " if show_outcome else ""
    lines = [f"task={d.get('task_id')} {outcome}steps={d.get('steps')} "
             f"tokens={d.get('tokens')} stopped={(d.get('outcome') or {}).get('stopped') if isinstance(d.get('outcome'), dict) else d.get('outcome')} error={d.get('error')}"]
    task_ev = next((e for e in ev if e["type"] == "task"), None)
    if task_chars > 0 and task_ev:
        lines.append(f"TASK: {str(task_ev.get('instruction', ''))[:task_chars]}")
    first_user = next((e for e in ev if e["type"] == "harness"), None)
    if first_user:
        lines.append(f"bundle={json.dumps(first_user.get('bundle'))[:300]}")
    body = [e for e in ev if e["type"] in ("llm", "step", "verifier_reject", "exception")]
    if len(body) > max_events:
        lines.append(f"... ({len(body) - max_events} earlier events omitted)")
        body = body[-max_events:]
    for e in body:
        if e["type"] == "llm":
            calls = [f"{c['function']['name']}({c['function'].get('arguments', '')[:120]})" for c in (e.get("tool_calls") or [])]
            lines.append(f"  THINK: {(e.get('content') or '')[:max_chars]!r} CALLS: {calls}")
        elif e["type"] == "step":
            lines.append(f"  OBS[{e['tool']}]: {str(e.get('observation'))[:max_chars]!r}")
        else:
            lines.append(f"  {e['type'].upper()}: {str(e.get('feedback') or e.get('error'))[:max_chars]}")
    return "\n".join(lines)


def budget_check(where: str):
    return llm_mod.budget_banner(where)
