"""Harness composition: deterministic `compose(task) -> Harness`.

H0 = DEFAULT_BUNDLE (every slot -> "default"). This is the analogue of ModularRSI's StaticComposer.
A harness root may pin slot variants and configs in `bundle.json` ({"slot": {"name": ..., "config": {...}}}),
which works like ModularRSI's `active_bundle.json`: it is validated, partial, and falls back to the default bundle
when invalid. Per-task composers (B2's LLM composer, HarnessGraph) plug in through `composer=`, a callable
(task, registry, base_bundle) -> bundle. Its output is validated the same way.
"""
from __future__ import annotations

import copy
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from benchmarks.common import TaskSpec
from h0.protocols import SLOTS, LoopOutcome
from h0.registry import H0_ROOT, Registry, load_registry

log = logging.getLogger(__name__)

DEFAULT_BUNDLE: dict[str, dict] = {s: {"name": "default", "config": {}} for s in SLOTS}

SYSTEM_PROMPT = (
    "You are an autonomous agent that solves tasks by interacting with an environment through the provided "
    "tools. Work in a ReAct style: before every tool call, briefly state your reasoning about what you have "
    "learned and what to do next, then call exactly one tool. Base every decision on the observations you "
    "actually received; do not invent results."
)


@dataclass
class Harness:
    agent_loop: Any
    context_mgmt: Any
    tool_policy: Any
    memory: Any
    verifier: Any
    bundle: dict
    system_prompt: str = SYSTEM_PROMPT
    root: str = ""
    meta: dict = field(default_factory=dict)

    def run(self, task: TaskSpec, env, llm, rec) -> LoopOutcome:
        rec.note("harness", root=self.root, bundle=self.bundle, meta=self.meta)
        return self.agent_loop.run(task, env, self, llm, rec)


_REG_CACHE: dict[str, Registry] = {}


def get_registry(root: Path | str = H0_ROOT, fresh: bool = False) -> Registry:
    key = str(Path(root).resolve())
    if fresh or key not in _REG_CACHE:
        _REG_CACHE[key] = load_registry(root)
    return _REG_CACHE[key]


def validate_bundle(bundle: dict, reg: Registry, base: dict | None = None) -> dict:
    """Partial override onto `base` (default DEFAULT_BUNDLE). Raises ValueError on any invalid entry."""
    out = copy.deepcopy(base or DEFAULT_BUNDLE)
    for slot, spec in (bundle or {}).items():
        if slot not in SLOTS:
            raise ValueError(f"unknown slot {slot!r}")
        if isinstance(spec, str):
            spec = {"name": spec}
        if not isinstance(spec, dict) or "name" not in spec:
            raise ValueError(f"bundle entry for {slot} must have a name")
        if not reg.has(slot, spec["name"]):
            raise ValueError(f"no variant {slot}/{spec['name']}")
        cfg = spec.get("config", {})
        if not isinstance(cfg, dict):
            raise ValueError(f"config for {slot} must be an object")
        out[slot] = {"name": spec["name"], "config": cfg}
    return out


def root_bundle(root: Path | str, reg: Registry) -> dict:
    p = Path(root) / "bundle.json"
    if not p.exists():
        return copy.deepcopy(DEFAULT_BUNDLE)
    try:
        return validate_bundle(json.loads(p.read_text(encoding="utf-8")), reg)
    except Exception as e:
        log.warning("bundle.json invalid (%s); using DEFAULT_BUNDLE", e)
        return copy.deepcopy(DEFAULT_BUNDLE)


def build(bundle: dict, reg: Registry, system_prompt: str | None = None, meta: dict | None = None) -> Harness:
    objs = {s: reg.instantiate(s, bundle[s]["name"], bundle[s].get("config")) for s in SLOTS}
    sp = system_prompt
    if sp is None:
        p = reg.root / "system_prompt.txt"
        sp = p.read_text(encoding="utf-8").strip() if p.exists() else SYSTEM_PROMPT
    return Harness(**objs, bundle=copy.deepcopy(bundle), system_prompt=sp, root=str(reg.root), meta=meta or {})


def compose(task: TaskSpec | None = None, root: Path | str = H0_ROOT,
            composer: Callable[[TaskSpec, Registry, dict], dict] | None = None) -> Harness:
    """Deterministic for composer=None: the root's bundle (DEFAULT_BUNDLE for H0)."""
    reg = get_registry(root)
    base = root_bundle(root, reg)
    meta = {}
    if composer is not None and task is not None:
        try:
            chosen = composer(task, reg, base)
            base = validate_bundle(chosen, reg, base)
            meta["composer"] = "custom"
        except Exception as e:  # fall back to the root bundle, as ModularRSI's LLMComposer does
            meta["composer_error"] = f"{type(e).__name__}: {e}"
    return build(base, reg, meta=meta)


class LazyHarness:
    """Adapter-facing object: composes a fresh Harness per task (task-aware composers need the TaskSpec)."""

    def __init__(self, root: Path | str = H0_ROOT, composer=None, memory=None):
        self.root, self.composer, self.shared_memory = root, composer, memory
        self.last: Harness | None = None

    def run(self, task: TaskSpec, env, llm, rec) -> LoopOutcome:
        h = compose(task, self.root, self.composer)
        if self.shared_memory is not None:  # cross-episode memory object owned by the caller
            h.memory = self.shared_memory
        self.last = h
        return h.run(task, env, llm, rec)
