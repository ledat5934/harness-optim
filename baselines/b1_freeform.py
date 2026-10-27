"""B1: global free-form harness evolution, Meta-Harness style (stanford-iris-lab/meta-harness, MIT).

Reused from third_party/meta-harness/reference_examples/terminal_bench_2/meta_harness.py (copied, not imported: that
module imports claude_wrapper and dotenv at top level):
  compute_pass_rates, summarize_trial_metrics, update_frontier, update_evolution_summary, render_task_prompt,
  the pending_eval.json read/write, and the outer loop validate -> smoke -> benchmark -> frontier update.
  Changes are listed in docs/baseline_fidelity.md (section B1). In short: the paths are arguments instead of module
  globals; harbor_run / parse_job_results / parse_trial_metrics are replaced by C.evaluate and our records; the Claude
  Code proposer is replaced by two calls to our model (analysis, then implementation).

The proposer prompt is .claude/skills/meta-harness-terminal-bench-2/SKILL.md (MIT), with the Terminal-Bench /
AgentHarness parts replaced by the H0 slot contracts. Changes are listed in SKILL_CHANGES below and in the doc.

Simplified: the proposer cannot browse the filesystem, so the files it would read are rendered into its prompt. The
proposer may pick any candidate in the pool (H0 and every validated candidate) as its parent.
"""
from __future__ import annotations

import difflib
import json
import re
from pathlib import Path

from baselines import common as C
from baselines.proposer_io import apply_files, extract_json, field, gate_hint, reply_files

MAX_TRAJ_IN_PROMPT = 24  # the reference shows every candidate's jobs; bounded here to keep the prompt size fixed
TASK_CHARS = 1500  # task instruction shown at the top of each trajectory (the reference trace starts with it)

# ---------------------------------------------------------------- reference functions (copied, paths as arguments)


def compute_pass_rates(task_rewards: dict[str, list[float]]) -> tuple[dict[str, float], float]:
    """Pass rate per task and flat average (total passes / total trials, matching harbor's metric). Copied from
    meta_harness.compute_pass_rates."""
    per_task = {}
    total_passes = 0
    total_trials = 0
    for task, rewards in task_rewards.items():
        per_task[task] = sum(r > 0 for r in rewards) / len(rewards) if rewards else 0.0
        total_passes += sum(r > 0 for r in rewards)
        total_trials += len(rewards)
    avg = total_passes / total_trials if total_trials else 0.0
    return per_task, avg


def summarize_trial_metrics(trial_metrics: dict[str, list[dict]]) -> dict:
    """Aggregate per-trial metrics into a summary dict. Copied from meta_harness.summarize_trial_metrics."""
    all_costs = []
    all_input = []
    all_output = []
    all_cache = []
    all_turns = []
    per_task_summary = {}
    for task, trials in trial_metrics.items():
        task_costs = [t["cost_usd"] for t in trials if t["cost_usd"] is not None]
        task_turns = [t["n_turns"] for t in trials if t["n_turns"] is not None]
        per_task_summary[task] = {
            "mean_cost": round(sum(task_costs) / len(task_costs), 3) if task_costs else None,
            "mean_turns": round(sum(task_turns) / len(task_turns), 1) if task_turns else None,
            "n_trials": len(trials),
        }
        all_costs.extend(task_costs)
        all_turns.extend(task_turns)
        all_input.extend(t["n_input_tokens"] for t in trials if t["n_input_tokens"] is not None)
        all_output.extend(t["n_output_tokens"] for t in trials if t["n_output_tokens"] is not None)
        all_cache.extend(t["n_cache_tokens"] for t in trials if t["n_cache_tokens"] is not None)
    n_trials = sum(len(v) for v in trial_metrics.values())
    return {
        "n_trials": n_trials,
        "total_cost_usd": round(sum(all_costs), 2) if all_costs else None,
        "mean_cost_usd": round(sum(all_costs) / len(all_costs), 3) if all_costs else None,
        "total_input_tokens": sum(all_input) if all_input else None,
        "total_output_tokens": sum(all_output) if all_output else None,
        "total_cache_tokens": sum(all_cache) if all_cache else None,
        "mean_turns": round(sum(all_turns) / len(all_turns), 1) if all_turns else None,
        "per_task": per_task_summary,
    }


def trial_metrics_of(recs: list[dict]) -> dict[str, list[dict]]:
    """Our episode records as the per-trial metric dicts summarize_trial_metrics expects. llm.py records only a total
    token count, so it goes to n_input_tokens and the output/cache fields stay empty (documented limitation)."""
    out: dict[str, list[dict]] = {}
    for r in recs:
        out.setdefault(r["task_id"], []).append({"cost_usd": r.get("cost"), "n_turns": r["steps"],
                                                 "n_input_tokens": r["tokens"], "n_output_tokens": None,
                                                 "n_cache_tokens": None})
    return out


def update_frontier(path: Path, candidates_results: dict[str, tuple[dict, float]]) -> None:
    """Frontier with the reference layout: {task: {"best_agent", "pass_rate"}, "_best": {"agent", "avg_pass_rate"}}.
    Copied from meta_harness.update_frontier; the path is an argument instead of a module global."""
    frontier = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for agent_name, (per_task, avg) in candidates_results.items():
        for task, rate in per_task.items():
            current_best = frontier.get(task, {}).get("pass_rate", -1)
            if rate > current_best:
                frontier[task] = {"best_agent": agent_name, "pass_rate": rate}
        current_best_avg = frontier.get("_best", {}).get("avg_pass_rate", -1)
        if avg > current_best_avg:
            frontier["_best"] = {"agent": agent_name, "avg_pass_rate": avg}
    path.write_text(json.dumps(frontier, indent=2), encoding="utf-8")


def update_evolution_summary(path: Path, frontier_path: Path, iteration: int, candidates: list[dict],
                             results: dict[str, tuple[dict, float]], metrics: dict | None = None) -> None:
    """Append one JSONL row per candidate. Copied from meta_harness.update_evolution_summary (paths as arguments)."""
    frontier = json.loads(frontier_path.read_text(encoding="utf-8")) if frontier_path.exists() else {}
    best_avg = frontier.get("_best", {}).get("avg_pass_rate", 0)
    metrics = metrics or {}
    with open(path, "a", encoding="utf-8") as f:
        for c in candidates:
            name = c["name"]
            per_task, avg = results.get(name, ({}, 0))
            row = {
                "iteration": iteration,
                "agent": name,
                "avg_pass_rate": round(avg, 3),
                "per_task": {k: round(v, 3) for k, v in per_task.items()},
                "hypothesis": c.get("hypothesis", ""),
                "changes": c.get("changes", ""),
                "delta": round(avg - best_avg, 3) if best_avg else None,
                "outcome": f"{avg:.1%} ({avg - best_avg:+.1%})" if avg > 0 else "failed",
            }
            if name in metrics:
                row["rollout_metrics"] = metrics[name]
            f.write(json.dumps(row) + "\n")


def render_task_prompt(bench: str, iteration: int, ws: Path, n_train: int, n_val: int, k: int, model: str) -> str:
    """Task prompt for the proposer. Adapted from meta_harness.render_task_prompt: the Terminal-Bench split line and
    the Claude Code wording are replaced by this benchmark's split and our file layout."""
    return (
        f"Run iteration {iteration} of the harness evolution loop ({bench}). Model: {model}.\n"
        f"Start from the parent you choose among the candidate pool below (H0 and every validated candidate).\n\n"
        f"## Eval split: {n_train} train tasks x {k} rolls (evidence), {n_val} validation tasks x 1 roll\n\n"
        f"Focus on harness changes that help the agent solve the tasks, not changes that help only one task.\n\n"
        f"## Run directories\n"
        f"All logs and results for this run are under `{ws}/`.\n"
        f"- `{ws / 'evolution_summary.jsonl'}` - past results\n"
        f"- `{ws / 'frontier_val.json'}` - frontier\n"
        f"- Write pending_eval.json to: `{ws / 'pending_eval.json'}`"
    )


# ---------------------------------------------------------------- proposer prompt
# SKILL.md text. Changed parts are listed in SKILL_CHANGES; everything else is the reference wording.
SKILL = """---
name: meta-harness-terminal-bench-2
description: Run one iteration of harness evolution for {bench}.
---

# Meta-Harness ({bench})

Run ONE iteration of agent scaffold evolution.

**You do NOT run benchmarks.** You analyze results + failed trajectories, propose harness variants, and implement them. The outer loop (`baselines/b1_freeform.py`) handles benchmarking.

## CRITICAL CONSTRAINTS

- You MUST produce 1 new harness variant every iteration
- Do NOT write "the frontier is optimal" or "stop iterating", or abort early.

### Anti-overfitting rules

- **No task-specific hints.** Do not hardcode knowledge about specific tasks. Agents must be general-purpose.
- **Never mention task names** in agent code, prompts, or comments. No references like "if task contains 'async'" or "for polyglot tasks." If your improvement only helps one task, it's too specific.
- **General guidance is OK.** Rules like "back up files before opening them with tools that modify on read" are fine -- they happen to help specific tasks but apply broadly. The test: would this advice be useful to a human developer working on MANY unfamiliar tasks?
- **If in doubt, make it more general.** "Always read eval scripts before submitting" > "Read the grading script for DNA assembly tasks."

## CONTEXT

You are evolving the **H0 harness** for {bench}. It has five slots (`agent_loop`, `context_mgmt`, `tool_policy`, `memory`, `verifier`), each a variant file under `variants/<slot>/`. The parent's files are shown in full in the prompt.

**The search space is arbitrary Python code inside the slot files.** You can override any slot method, add new variants, change the system prompt, or change how the bundle is composed -- anything that's expressible in Python is fair game. The only constraint is that each file keeps its `register(reg)` function and the slot Protocol below, so the harness still loads.

**Model: {model}.** Evaluation uses the protocol's train/val/test splits (fixed by the shared H0 seed).

**Key files to read:**

- `variants/<slot>/default.py` - the parent's implementation of each slot (shown in the prompt).

You should copy over one of the variants as a starting point. **You can rewrite or override ANY method.** Never import from other candidates. Copy any code you want to reuse.

Slot protocols (the contract to keep):

- `agent_loop.run(task, env, h, llm, rec) -> LoopOutcome` - main episode loop. `h` exposes `.context_mgmt`, `.tool_policy`, `.memory`, `.verifier`, `.system_prompt`.
- `context_mgmt.build(system, task, history, memory_notes) -> list[messages]` - what the model sees each turn.
- `tool_policy.tools(task)`, `.parse(resp, task) -> list[Action]`, `.format_observation(action, result, task) -> str` - the action surface and how results are shown.
- `memory.recall(task) -> str`, `.update(task, outcome, success, trajectory) -> None`.
- `verifier.check(task, action, state, env_done) -> Verdict(accept, feedback)` - whether a finish is accepted.
- `llm.chat(messages, tools=..., tag=...)` is the only LLM call path.

## CANDIDATE DESIGN

Each candidate is a set of files in its own directory: edited `variants/<slot>/default.py` files and/or new `variants/<slot>/<name>.py` files, optionally `system_prompt.txt`. Each new variant file must register itself with a `register(reg)` function, and its name must be snake_case.

**A new variant only runs if `bundle.json` selects it** (e.g. `{"agent_loop": "my_variant"}`; slots you leave out keep `default`). Otherwise edit `variants/<slot>/default.py` directly. Each episode builds a fresh harness and `memory.update` is never called by the harness, so nothing persists across episodes.

### What you can and cannot modify

- **CAN**: edit the files of your candidate freely; add new variant files.
- **CANNOT**: modify `h0/protocols.py`, `benchmarks/`, `baselines/`, the registry, or any file outside the candidate directory.

### Design principles

- Your primary goal is to improve the agent's success rate on the evaluation tasks.
- One mechanism per candidate. Each candidate tests exactly one hypothesis. If you're tempted to add "and also..." -- that's a second candidate.
- Mechanism-first. Identify a specific failure mode or hypothesis from trajectories, then design changes that target it. Never add changes speculatively.

## WORKFLOW

### Step 1: Analyze (1 model call)

You should:

1. Read state:
   - `frontier_val.json` - current best candidate per task (shown in the prompt)
   - `evolution_summary.jsonl` - what's been tried, what worked/didn't, plus `rollout_metrics` (shown in the prompt)
   - the candidate pool: every validated candidate, with its validation score. Pick ONE of them as the parent.
2. **Deep-read failed AND successful trajectories.** Most important step. They are shown in the prompt.
3. Read harness implementations: H0's slot files in full and every pool candidate as a diff against H0 (shown in the prompt)
4. Return:

```
STATE: <5-line summary: current scores, what's been tried, avg tokens/steps>

HYPOTHESIS: "<falsifiable claim about what will improve scores>"
CANDIDATE: name=<snake_case>, changes="<specific changes>", prediction="<expected pass rate improvement AND expected token/step impact>"
PARENT: <h0 or r<k> from the pool>
```

### Step 2: Implement (1 model call)

Implement the candidate you described, starting from the chosen parent's files. Make targeted changes. Return the COMPLETE content of every file you change, and nothing else the harness would need to load. The outer loop checks that the harness imports and runs a toy episode; if it fails, you will be shown the error and asked once more.

### Step 3: Write pending_eval.json

Write `pending_eval.json` to the path given in the task prompt:

```json
{
  "iteration": <N>,
  "candidates": [
    {
      "name": "<name>",
      "parent": "<h0 or r<k>>",
      "hypothesis": "<falsifiable claim>",
      "changes": "<what was changed>",
      "expected_efficiency": "<expected token/step impact>"
    }
  ]
}
```

Output: `CANDIDATES: <name1>`

## IMPORTANT NOTES

- **Each candidate has one name.** The candidate directory is named after the iteration (`r<k>`); the name you choose goes into pending_eval.json.
- **Keep every file loadable.** Only the standard library, `json`, `re`, `benchmarks.common` and `h0.protocols` may be imported.
- **Keep the slot Protocol signatures** listed above; `h0.compose` builds the bundle from `bundle.json` and the registry.
- The prompt is plain text: no tools are available to you, so everything you need is in the prompt."""

# Every change from the reference SKILL.md, for the fidelity document:
#  1. title and description: "Terminal Bench 2" -> the benchmark name
#  2. "The outer loop (`meta_harness.py`)" -> "(`baselines/b1_freeform.py`)"
#  3. CONTEXT: AgentHarness / agents/baseline_kira.py / Claude Opus 4.6 / 89-task TB2 / Harbor-subclass constraint ->
#     H0 slot files, protocol split, our model; "CANDIDATE DESIGN": a single agents/<name>.py file -> a set of slot files
#  4. Key methods of the Terminus2 subclass -> the five slot Protocols
#  5. "CANNOT modify meta_harness.py or claude_wrapper.py" -> the H0 contract files
#  6. Step 1/2: "Launch ONE Agent subagent" -> one model call each (no subagents); Step 1 adds PARENT (the pool choice);
#     Step 1.3 "Read agent implementations in `agents/*.py`" -> H0 in full plus each pool candidate as a diff vs H0
#  7. Step 3 JSON: import_path -> parent; `agents/<name>.py` notes removed
#  8. IMPORTANT NOTES: AgentHarness class name, async methods, litellm, prompt-template placeholders, 30KB limit removed;
#     the slot-contract and no-tools notes added
#  9. CANDIDATE DESIGN: how a new variant is selected (bundle.json) and that memory does not persist across episodes.
#     In the reference a candidate IS the new agent file (pending_eval import_path), so it always runs; in H0 a new
#     variant file is inert unless bundle.json selects it, which the first MEDIUM pass showed (B1's final harness on
#     BrowseComp-Plus and AppWorld was behaviourally H0).
SKILL_CHANGES = 9

ANALYSIS_FORMAT = """
## Output for Step 1 and Step 3 (plain text, then one JSON block)
STATE: <5-line summary>
HYPOTHESIS: "<falsifiable claim>"
CANDIDATE: name=<snake_case>, changes="<specific changes>", prediction="<expected effect on success and tokens>"
PARENT: <h0 or r<k>>
```json
{"iteration": <N>, "candidates": [{"name": "<name>", "parent": "<h0 or r<k>>", "hypothesis": "<claim>", "changes": "<what>", "expected_efficiency": "<token/step impact>"}]}
```
"""

IMPLEMENT_FORMAT = """
## Output (Step 2)
Output the COMPLETE content of every file you change, one block each:
### FILE: variants/<slot>/<name>.py
```python
<complete file>
```
(You may also emit `### FILE: system_prompt.txt` with a ```text block.)
A NEW variant file runs only if you also emit `### FILE: bundle.json` (a ```json block) selecting it, e.g.
{"agent_loop": "my_variant"}; or put the change in `variants/<slot>/default.py`.
Output nothing else that the harness would need."""


# ---------------------------------------------------------------- proposer (two calls) and gates
def _pool_listing(pool: list[dict]) -> str:
    return "\n".join(f"- {p['name']}: validation success={p['val']:.1%}" if p.get("val") is not None
                     else f"- {p['name']}: (reference seed)" for p in pool)


def _pool_code(pool: list[dict]) -> str:
    """Step 1.3 (read the agent implementations): H0's files in full, every other pool candidate as a unified diff
    against H0, so the prompt grows with the size of the changes rather than with the pool."""
    h0 = next(p for p in pool if p["name"] == "h0")
    base = _files(h0["root"])
    parts = [f"### h0 (complete)\n{C.tree_text(h0['root'], None)}"]
    for p in pool:
        if p["name"] == "h0":
            continue
        files = _files(p["root"])
        diff = "".join("".join(difflib.unified_diff(base.get(f, "").splitlines(True), files.get(f, "").splitlines(True),
                                                    f"h0/{f}", f"{p['name']}/{f}"))
                       for f in sorted(set(base) | set(files)))
        parts.append(f"### {p['name']} (diff vs h0)\n{diff or '(identical to h0)'}")
    return "\n\n".join(parts)


def _files(root: Path) -> dict[str, str]:
    return {f.relative_to(root).as_posix(): f.read_text(encoding="utf-8")
            for f in sorted(list((root / "variants").rglob("*.py")) + [p for p in (root / "bundle.json",
                                                                                   root / "system_prompt.txt") if p.exists()])}


def _traces(evidence: list[dict]) -> str:
    return "\n\n".join(f"--- TRAJECTORY ({'PASS' if e['success'] else 'FAIL'}) {e['trajectory_path']}\n"
                       f"{C.summarize_trajectory(e['trajectory_path'], max_events=60, max_chars=600, task_chars=TASK_CHARS)}"
                       for e in evidence)


def analyze(bench: str, ws: Path, pool: list[dict], frontier: dict, evidence: list[dict], client, round_i: int,
            n_train: int, n_val: int, k: int) -> dict:
    """Step 1 + Step 3: one call that analyzes the state, picks a parent from the pool and writes pending_eval.json."""
    model = getattr(client, "model", "unknown")
    summary = ws / "evolution_summary.jsonl"
    listing = summary.read_text(encoding="utf-8").strip() if summary.exists() else ""
    prompt = (f"{SKILL.replace('{bench}', bench).replace('{model}', model)}\n\n"
              f"{render_task_prompt(bench, round_i, ws, n_train, n_val, k, model)}\n\n"
              f"## evolution_summary.jsonl\n{listing or '(empty)'}\n\n"
              f"## frontier_val.json\n{json.dumps(frontier, indent=1)}\n\n"
              f"## Candidate pool (choose ONE as PARENT)\n{_pool_listing(pool)}\n\n"
              f"## Harness implementations (H0 complete, other candidates as diffs vs H0)\n{_pool_code(pool)}\n\n"
              f"## Trajectories (PASS/FAIL labels are the real outcomes)\n{_traces(evidence)}\n"
              + ANALYSIS_FORMAT)
    r = client.chat([{"role": "user", "content": prompt}], tag=f"b1:analyze:{bench}", max_tokens=6000,
                    fallback_no_reasoning=True)
    (ws / f"analysis_r{round_i}.txt").write_text(r.content, encoding="utf-8")
    pending = extract_json(r.content)
    if not isinstance(pending, dict) or not isinstance(pending.get("candidates"), list) or not pending["candidates"]:
        return {"ok": False, "text": r.content}
    cand = dict(pending["candidates"][0])
    cand["name"] = re.sub(r"[^a-z0-9_]", "_", str(cand.get("name", f"r{round_i}")).lower()) or f"r{round_i}"
    names = {p["name"] for p in pool}
    parent = (field(r.content, "PARENT") or "").strip().strip("`")
    if parent not in names:
        parent = cand.get("parent") if cand.get("parent") in names else "h0"
    cand["parent"] = parent
    pending["candidates"] = [cand]
    (ws / "pending_eval.json").write_text(json.dumps(pending, indent=1), encoding="utf-8")
    return {"ok": True, "text": r.content, "candidate": cand}


def implement(bench: str, cand_dir: Path, parent_root: Path, cand: dict, client, round_i: int) -> dict:
    """Step 2: one call that writes the candidate's files, then the static gate, one repair call on failure."""
    parent_tree = C.tree_text(parent_root, None)  # uncut: H0 alone is ~19k chars
    base = (f"## Candidate\nname={cand['name']}\nHYPOTHESIS: {cand.get('hypothesis', '')}\n"
            f"CHANGES: {cand.get('changes', '')}\n\n## PARENT files (complete)\n{parent_tree}\n" + IMPLEMENT_FORMAT)
    prompt, meta = base, {"gate": "not run"}
    for attempt in range(2):
        C.new_candidate(cand_dir, parent_root, {"method": "b1", "round": round_i, "parent": parent_root.name})
        r = client.chat([{"role": "user", "content": prompt}], tag=f"b1:implement:{bench}", max_tokens=12000,
                        fallback_no_reasoning=True)
        (cand_dir.parent / f"{cand_dir.name}_implement_{attempt}.txt").write_text(r.content, encoding="utf-8")
        written, rejected = apply_files(cand_dir, reply_files(r))
        meta.update(written=written, rejected=rejected, attempt=attempt)
        if not written:
            meta["gate"] = "no FILE blocks parsed"
            prompt = base + "\n\nYour previous answer contained no valid ### FILE blocks. Output the files now."
            continue
        ok, log = C.static_gate(cand_dir)  # validate: import, registry, offline toy run (baselines/common.static_gate)
        unused = unselected_variants(cand_dir, written) if ok else []
        if unused:  # loads fine but the new code would never run: same repair path as a gate failure
            ok, log = False, (f"new variant(s) {unused} are not selected by bundle.json, so they would never run. "
                              "Emit `### FILE: bundle.json` selecting them, or move the change into default.py.")
        meta["gate"] = "ok" if ok else log[-600:]
        if ok:
            return {"ok": True, **meta}
        prompt = base + f"\n\nYour previous candidate FAILED validation:\n{log[-1200:]}{gate_hint(log)}\nFix it and output complete files."
    return {"ok": False, **meta}


_REGISTER = re.compile(r"""reg\.register\(\s*["'](\w+)["']\s*,\s*["'](\w+)["']""")


def unselected_variants(cand_dir: Path, written: list[str]) -> list[str]:
    """New (non-default) variants among the written files that bundle.json does not select: they would never run.
    An unreadable bundle.json counts as selecting nothing (h0.compose falls back to the default bundle)."""
    try:
        raw = json.loads((cand_dir / "bundle.json").read_text(encoding="utf-8")) if (cand_dir / "bundle.json").exists() else {}
        sel = {slot: (spec if isinstance(spec, str) else spec.get("name")) for slot, spec in raw.items()}
    except Exception:
        sel = {}
    out = []
    for rel in written:
        if not rel.endswith(".py"):
            continue
        regs = _REGISTER.findall((cand_dir / rel).read_text(encoding="utf-8"))
        if not regs and not rel.endswith("/default.py"):  # a variant file that registers nothing never runs
            out.append(f"{rel} (registers no variant)")
        # default.py may register extra names too: they run only when selected, like a new file's
        for slot, name in regs:
            if name != "default" and sel.get(slot) != name:
                out.append(f"{slot}/{name}")
    return out


def _reward(r: dict) -> float:
    return 1.0 if r["success"] else 0.0


# ---------------------------------------------------------------- run
def run(bench: str, shared: dict, client, cfg=C.SMOKE, tag: str = "smoke") -> dict:
    """shared: {'tasks': protocol_tasks, 'h0_train': [...recs], 'h0_val': [...recs]} computed once for all methods."""
    ws = C.RUNS / "b1" / bench
    ws.mkdir(parents=True, exist_ok=True)
    out = C.OUT / f"b1_{bench}.jsonl"
    frontier_path, summary_path = ws / "frontier_val.json", ws / "evolution_summary.jsonl"
    tasks = shared["tasks"]
    k = cfg["k"]
    n_train, n_val = len(tasks["train"][1]), len(tasks["val"][1])
    best, best_val, best_tok = C.H0_ROOT, C.score(shared["h0_val"]), sum(r["tokens"] for r in shared["h0_val"])
    h0_per_task, h0_avg = compute_pass_rates({r["task_id"]: [_reward(r)] for r in shared["h0_val"]})
    frontier_path.unlink(missing_ok=True)
    summary_path.unlink(missing_ok=True)
    update_frontier(frontier_path, {"h0": (h0_per_task, h0_avg)})
    update_evolution_summary(summary_path, frontier_path, 0, [{"name": "h0", "hypothesis": "seed", "changes": ""}],
                             {"h0": (h0_per_task, h0_avg)}, {"h0": summarize_trial_metrics(trial_metrics_of(shared["h0_val"]))})
    pool = [{"name": "h0", "root": C.H0_ROOT, "val": best_val}]
    evidence = list(shared["h0_train"])  # every round sees the H0 train rolls and the accumulated candidate rollouts
    log = {"method": "b1", "bench": bench, "rounds": []}
    for ri in range(1, cfg["rounds"] + 1):
        C.budget_check(f"b1[{bench}] round {ri}")
        rd = {"round": ri}
        frontier = json.loads(frontier_path.read_text(encoding="utf-8"))
        # propose: step 1 + 3 (analysis, parent choice, pending_eval.json), then step 2 (implementation)
        an = analyze(bench, ws, pool, frontier, evidence[-MAX_TRAJ_IN_PROMPT:], client, ri, n_train, n_val, k)
        if not an["ok"]:
            rd["result"] = "proposer returned no candidate"
            log["rounds"].append(rd)
            update_evolution_summary(summary_path, frontier_path, ri, [{"name": f"r{ri}"}], {})
            continue
        cand = an["candidate"]
        parent = next(p for p in pool if p["name"] == cand["parent"])
        rd.update(candidate=cand["name"], parent=parent["name"], hypothesis=cand.get("hypothesis"),
                  changes=cand.get("changes"))
        cand_dir = ws / "candidates" / f"r{ri}"
        impl = implement(bench, cand_dir, parent["root"], cand, client, ri)
        rd["implement"] = {k2: impl[k2] for k2 in ("ok", "written", "gate") if k2 in impl}
        if not impl["ok"]:
            rd["result"] = "rejected at validation"
            log["rounds"].append(rd)
            update_evolution_summary(summary_path, frontier_path, ri, [{**cand, "name": f"r{ri}"}], {})
            continue
        # smoke: execute on cfg["n_check"] train tasks (crash check, reference smoke_test)
        sm = C.evaluate(bench, tasks["train"][0], tasks["train"][1][:cfg["n_check"]], cand_dir, client,
                        f"b1_{bench}_r{ri}_smoke", out, workers=cfg["workers"],
                        label={"method": "b1", "phase": "smoke", "round": ri})
        crashed = [r for r in sm if r["error"]]
        if crashed:
            rd.update(result="smoke crash", smoke_errors=[r["error"] for r in crashed])
            log["rounds"].append(rd)
            update_evolution_summary(summary_path, frontier_path, ri, [{**cand, "name": f"r{ri}"}], {})
            continue
        # benchmark: validation tasks (shared protocol)
        val = C.evaluate(bench, tasks["val"][0], tasks["val"][1], cand_dir, client, f"b1_{bench}_r{ri}_val", out,
                         workers=cfg["workers"], label={"method": "b1", "phase": "val", "round": ri})
        v, tok = C.score(val), sum(r["tokens"] for r in val)
        per_task, avg = compute_pass_rates({r["task_id"]: [_reward(r)] for r in val})
        update_frontier(frontier_path, {f"r{ri}": (per_task, avg)})
        update_evolution_summary(summary_path, frontier_path, ri, [{**cand, "name": f"r{ri}"}], {f"r{ri}": (per_task, avg)},
                                 {f"r{ri}": summarize_trial_metrics(trial_metrics_of(val))})
        pool.append({"name": f"r{ri}", "root": cand_dir, "val": v})
        evidence += sm + val
        rd.update(val=v, smoke=C.score(sm), tokens_val=tok)
        if C.better(v, tok, best_val, best_tok):  # shared selection rule (correctness first, tokens tiebreak)
            best, best_val, best_tok = cand_dir, v, tok
            rd["result"] = "new incumbent"
        else:
            rd["result"] = "kept incumbent"
        log["rounds"].append(rd)
    # ---- freeze and test
    log["final"] = str(best)
    (ws / "final.json").write_text(json.dumps({"final_root": str(best), "val": best_val}, indent=1))
    C.budget_check(f"b1[{bench}] test")
    test = C.evaluate(bench, tasks["test"][0], tasks["test"][1], best, client, f"b1_{bench}_test", out,
                      workers=cfg["workers"], label={"method": "b1", "phase": "test"})
    log["test"] = {"success": C.score(test), "n": len(test)}
    (ws / "log.json").write_text(json.dumps(log, indent=1, default=str))
    return {"log": log, "test": test}
