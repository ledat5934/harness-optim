"""Variant registry, auto-discovered from `<root>/variants/<slot>/*.py` (ModularRSI `library.py` pattern).

Each variant file defines `register(reg)` and calls
    reg.register(slot, name, factory, description, config_schema={...}, niche={...})
where `factory(config: dict) -> slot object`. A *harness root* is any directory containing `variants/` (and
optionally `bundle.json`). The seed lives at `h0/`. Evolved candidates are copies of that tree elsewhere, loaded in
path mode with unique module names so two roots never collide.
"""
from __future__ import annotations

import importlib.util
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from h0.protocols import SLOTS

log = logging.getLogger(__name__)
H0_ROOT = Path(__file__).resolve().parent


@dataclass
class VariantInfo:
    slot: str
    name: str
    description: str
    config_schema: dict = field(default_factory=dict)
    niche: dict = field(default_factory=dict)
    source: str = ""


@dataclass
class Registry:
    root: Path
    _reg: dict[str, dict[str, tuple[Callable[[dict], Any], VariantInfo]]] = field(default_factory=dict)
    load_errors: list[str] = field(default_factory=list)

    def register(self, slot: str, name: str, factory: Callable[[dict], Any], description: str,
                 config_schema: dict | None = None, niche: dict | None = None) -> None:
        if slot not in SLOTS:
            raise ValueError(f"unknown slot {slot!r}; valid: {SLOTS}")
        self._reg.setdefault(slot, {})[name] = (factory, VariantInfo(slot, name, description, config_schema or {},
                                                                     niche or {}, getattr(self, "_cur", "")))

    def instantiate(self, slot: str, name: str, config: dict | None = None) -> Any:
        if name not in self._reg.get(slot, {}):
            raise KeyError(f"no variant {slot}/{name}; available: {sorted(self._reg.get(slot, {}))}")
        return self._reg[slot][name][0](dict(config or {}))

    def infos(self, slot: str | None = None) -> list[VariantInfo]:
        return [i for s, d in self._reg.items() if slot in (None, s) for _, i in d.values()]

    def has(self, slot: str, name: str) -> bool:
        return name in self._reg.get(slot, {})


_counter = 0


def load_registry(root: Path | str = H0_ROOT) -> Registry:
    global _counter
    root = Path(root).resolve()
    reg = Registry(root=root)
    vdir = root / "variants"
    if not vdir.is_dir():
        raise FileNotFoundError(f"{vdir} not found")
    for slot_dir in sorted(p for p in vdir.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))):
        for f in sorted(slot_dir.glob("*.py")):
            if f.name.startswith("_"):
                continue
            _counter += 1
            modname = f"_hg_variant_{_counter}_{slot_dir.name}_{f.stem}"
            spec = importlib.util.spec_from_file_location(modname, f)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[modname] = mod
            try:
                spec.loader.exec_module(mod)
                reg._cur = f.relative_to(root).as_posix()
                if callable(getattr(mod, "register", None)):
                    mod.register(reg)
            except Exception as e:  # a broken variant must not take down the library; recorded for gates
                reg.load_errors.append(f"{f.relative_to(root).as_posix()}: {type(e).__name__}: {e}")
                log.warning("variant load failed %s: %s", f, e)
                sys.modules.pop(modname, None)
    return reg
