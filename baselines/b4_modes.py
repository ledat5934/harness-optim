"""B4 v4 (docs/idea_v3.md): LLM-discovered failure modes and the mechanism graph.

1. Failure modes are no longer only the six hand-written signal rules. Every sampled failed run gets an open
   hindsight label (a short, general description of what went wrong); an LLM then clusters the labels into a small
   registry of modes, reusing the names of earlier rounds. Each mode carries:
     - a definition (shown to the proposer),
     - its member runs (used to pick the targeted tasks when a candidate is screened),
     - an optional `signal_hint`: a precondition-DSL expression approximating the mode, so that unlabelled failures
       can be assigned too (evaluated on the saved trajectory signature),
     - `harness_fixable`: false when the cluster is model reasoning / task ambiguity / environment.
   The rule-based modes stay as features of each run (input to the clustering), not as the definition.
2. The mechanism graph: nodes are failure modes and mechanisms, edges carry the screening / val evidence
   (targets, helps, hurts, conflicts, in_set). It is derived from the append-only pool (the pool and ledger stay the
   source of truth, docs/idea_v2.md 3.4) and is shown to the proposer grouped by failure mode, together with the
   graphs of earlier runs (B4_GRAPH: comma-separated run roots, e.g. another seed or another model) so that a new
   proposal can build on what already helped a similar mode and avoid what hurt.
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path

from baselines.hg import runtime as R
from baselines.proposer_io import extract_json

CLUSTER = """You maintain a registry of FAILURE MODES of an AI agent, used to decide which scaffolding change to try.
Below are failed runs, each with an open hindsight label, the reviewer's cause, and rule-based behaviour tags
computed from the run (hedged_answer, early_stop, budget_exhausted, error_heavy, repetition, no_tool_call, other).

Existing modes from earlier rounds (reuse a name when the meaning is the same; keep names stable):
{registry}

Failed runs:
{runs}

Group the runs into at most {k} modes. A mode is a GENERAL behaviour pattern that recurs across tasks (never name
task entities, answers or ids). For each mode give:
- name: snake_case, 2-4 words
- definition: one sentence describing the observable behaviour
- members: list of run indices
- harness_fixable: false if the pattern is mainly the model's reasoning/knowledge, task ambiguity or environment
- signal_hint: OPTIONAL boolean expression over these run signals that approximates the mode (or ""):
{signals}
  functions n('<tool>'), min, max, abs. Tools: {tools}
Answer ONLY with JSON: {{"modes": [{{"name": "...", "definition": "...", "members": [0, 3], "harness_fixable": true,
"signal_hint": "..."}}]}}"""

MAX_MODES = 6


def discover_modes(client, bench: str, labelled: list[dict], registry: dict, tools: set[str],
                   ask_json) -> dict:
    """labelled rows: {task_id, path, label, why, cause, rule_modes}. Returns the updated registry
    {name: {definition, harness_fixable, signal_hint, members: [task_id], rounds: n}}."""
    if not labelled:
        return registry
    runs = "\n".join(f"[{i}] label={x['label']!r} cause={x['cause']} why={x['why']!r} tags={x['rule_modes']}"
                     for i, x in enumerate(labelled))
    reg = "\n".join(f"- {n}: {m['definition']}" for n, m in registry.items()) or "(none yet)"
    d = ask_json(client, CLUSTER.format(registry=reg, runs=runs, k=MAX_MODES, tools=sorted(tools),
                                        signals="\n".join(f"  {k}: {v}" for k, v in R.SIGNALS.items())),
                 f"b4:{bench}:cluster", 2500)
    new = {}
    for m in (d.get("modes") or [])[:MAX_MODES]:
        if not isinstance(m, dict):
            continue
        name = re.sub(r"[^a-z0-9_]", "_", str(m.get("name") or "").lower()).strip("_")[:40]
        if not name:
            continue
        hint = str(m.get("signal_hint") or "").strip()
        try:
            if hint:
                R.compile_pre(hint)
        except Exception:
            hint = ""
        idx = [i for i in (m.get("members") or []) if isinstance(i, int) and 0 <= i < len(labelled)]
        new[name] = {"definition": str(m.get("definition") or "")[:300], "harness_fixable": m.get("harness_fixable") is not False,
                     "signal_hint": hint, "members": sorted({labelled[i]["task_id"] for i in idx}),
                     "rounds": registry.get(name, {}).get("rounds", 0) + 1}
    if not new:  # clustering failed: keep the old registry rather than lose the targets
        return registry
    for n, m in registry.items():  # modes not seen this round stay known (for the graph), with no current members
        if n not in new:
            new[n] = {**m, "members": []}
    return new


def mode_tasks(registry: dict, fails: list[dict], sigs: dict) -> dict[str, set[str]]:
    """mode -> failed train task ids: labelled members, plus unlabelled failures matched by the signal hint."""
    out = {}
    for n, m in registry.items():
        ts = set(m.get("members") or [])
        if m.get("signal_hint") and ts:  # only extend modes that are present this round
            code = R.compile_pre(m["signal_hint"])
            ts |= {x["task_id"] for x in fails if R.eval_pre_sig(code, sigs.get(x.get("trajectory_path"), {}))}
        out[n] = ts
    return out


# ---------------------------------------------------------------- graph
def build_graph(pool: list[dict], registry: dict, model: str | None = None) -> dict:
    nodes = {f"mode:{n}": {"type": "mode", "definition": m["definition"], "fixable": m["harness_fixable"]}
             for n, m in registry.items()}
    edges = []
    for c in pool:
        if not c.get("kind"):
            continue
        nid = f"mech:{c['id']}"
        nodes[nid] = {"type": "mechanism", "kind": c["kind"], "name": c.get("mechanism"),
                      "precondition": c.get("precondition"), "text": str(c.get("text", ""))[:200], "status": c["status"]}
        ev = c.get("evidence") or {}
        fm = c.get("failure_mode")
        if fm:
            rel = ("in_set" if c["status"] == "in_set" else "helps" if c["status"] == "admitted"
                   else "hurts" if (ev.get("dS") or 0) < 0 or (ev.get("dT") or 0) < 0 else "tried")
            edges.append({"src": nid, "dst": f"mode:{fm}", "rel": rel, "dT": ev.get("dT"), "dS": ev.get("dS"),
                          "fired": ev.get("fired"), "reason": c.get("reason")})
        for other in c.get("conflicts") or []:
            for o in other:
                edges.append({"src": nid, "dst": f"mech:{o}", "rel": "conflicts"})
    return {"model": model, "nodes": nodes, "edges": edges}


def graph_view(g: dict, max_rows: int = 40) -> str:
    by_mode: dict[str, list[str]] = {}
    for e in g["edges"]:
        if e["rel"] == "conflicts":
            continue
        m = g["nodes"].get(e["src"], {})
        by_mode.setdefault(e["dst"], []).append(
            f"    {e['rel']}: {m.get('kind')} '{m.get('name')}' when `{m.get('precondition')}` "
            f"(dT={e.get('dT')} dS={e.get('dS')} fired={e.get('fired')})")
    rows = []
    for mode, lines in by_mode.items():
        rows.append(f"- {mode}: {g['nodes'].get(mode, {}).get('definition', '')}")
        rows += lines[:6]
    conf = [f"{e['src']}x{e['dst']}" for e in g["edges"] if e["rel"] == "conflicts"]
    if conf:
        rows.append("- conflicting pairs (merged set lost on val): " + ", ".join(sorted(set(conf))[:10]))
    return "\n".join(rows[:max_rows]) or "(empty)"


def prior_graphs(bench: str) -> str:
    """Graphs of earlier runs (B4_GRAPH), e.g. another seed or another model, as proposer evidence."""
    out = []
    for d in filter(None, os.environ.get("B4_GRAPH", "").split(",")):
        p = Path(d) / bench / "graph.json"
        if p.exists():
            g = json.loads(p.read_text())
            out.append(f"## from {Path(d).name} (model {g.get('model')})\n{graph_view(g, 25)}")
    return "\n".join(out) or "(none)"


def mode_counts(registry: dict, mt: dict[str, set[str]], frozen: set[str]) -> dict:
    return {n: {"failed_tasks": len(mt.get(n, ())), "definition": registry[n]["definition"]}
            for n in registry if registry[n]["harness_fixable"] and mt.get(n) and n not in frozen}


__all__ = ["discover_modes", "mode_tasks", "build_graph", "graph_view", "prior_graphs", "mode_counts", "Counter"]
