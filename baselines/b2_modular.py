"""B2: ModularRSI's self-evolution loop on H0, with the reference modules vendored under baselines/vendor/modularrsi/.

Vendored (CC BY-NC 4.0, research use only; cite Wu et al. 2026, arXiv 2609.14857). Each file's header lists its changes:
  router.py, trajectory_analysis.py, review_verdict.py, prompts.py   K-roll bucketing, lenses, verdict tag, prompts
  backlog.py                  append-only findings ledger (the backlog)
  routing.py                  per-finding routing: lane and action, validated before use
  clustering.py               a routed finding becomes a new proposal, or links to an open one
  proposals.py                proposal state machine (open, selected, attempted, promoted, rejected, taboo)
  portfolio.py                at most one proposal per lane (incumbent, novelty)
  dual_implement.py           two mutually blind lanes, each in its own staging tree
  rebase.py, promotion.py     the second lane is rebased onto the first; which gate results survive the move
  routing_probe.py            does the composer select the new variant on a train task
  confirm.py                  paired regression statistics
  lease.py, dispositions.py   window lease journal and disposition ledger

One round (ModularRSI's epoch, text-only: no tool calls, no Harbor):
  1. route_batch: K=3 rolls of the same harness per train task; the reference buckets. Infra errors are reward=None.
  2. Contrast investigation per slot: is this module the culprit, and is the fix within it (fixable_now).
  3. Every finding goes into the backlog (findings.jsonl), fixable or not.
  4. Every fixable culprit is routed (one call, validated) and clustered into a proposal: new, or linked to an open one.
  5. select_portfolio: at most MAX_LANES proposals, one per lane.
  6. dual_implement: each lane builds its change in its own staging tree: static gate, reviewer, routing probe.
     A reviewer's implementation reject gets one repair pass in the same round.
  7. Promotion: the first passing lane is merged; the second is rebased onto it and its tree-wide gates re-run.
  8. Integration static gate and the 2-task execution (sanity crash) check; a candidate that clears every gate is
     promoted (the reference compares no reward). A new variant must also pass the niche-dedup gate (step 6).
  9. The next window's evidence: K rolls of the current library (task-aware composer) on a fresh batch of
     cfg["n_val"] // K train tasks, rotating through the train set. Test runs use the frozen library.
"""
from __future__ import annotations

import ast
import asyncio
import difflib
import hashlib
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

from baselines import common as C
from baselines.proposer_io import apply_files, as_bool, extract_json, gate_hint, reply_files
from baselines.vendor.modularrsi import backlog as BL
from baselines.vendor.modularrsi import clustering as CL
from baselines.vendor.modularrsi import confirm as CF
from baselines.vendor.modularrsi import dispositions as DS
from baselines.vendor.modularrsi import dual_implement as DI
from baselines.vendor.modularrsi import lease as LS
from baselines.vendor.modularrsi import niche as NI
from baselines.vendor.modularrsi import portfolio as PF
from baselines.vendor.modularrsi import prompts as P
from baselines.vendor.modularrsi import promotion as PR
from baselines.vendor.modularrsi import proposals as PP
from baselines.vendor.modularrsi import rebase as RB
from baselines.vendor.modularrsi import routing as RT
from baselines.vendor.modularrsi import routing_probe as RP
from baselines.vendor.modularrsi import trajectory_analysis as TA
from baselines.vendor.modularrsi.review_verdict import _normalize, validate_attrs
from baselines.vendor.modularrsi.router import Ledger, RouterConfig, route_batch
from baselines.vendor.modularrsi.trajectory_analysis import TrialSummary
from benchmarks.common import instruction_of
from h0.compose import root_bundle
from h0.protocols import SLOTS
from h0.registry import load_registry

MAX_DIAG = 10       # diagnosed tasks per round (ModularRSI investigates the whole batch; capped for budget)
MAX_LANES = 2       # the portfolio's default lane ceiling: one incumbent lane and one novelty lane

# Our slot -> ModularRSI lens key (trajectory_analysis._MODULE_LENS). memory has no entry and falls back to the generic lens.
LENS_KEY = {"agent_loop": "agent_loop", "tool_policy": "tools", "context_mgmt": "context_mgmt",
            "verifier": "verification", "memory": "memory"}

# Text of the implementer prompt. Not in the reference's public prompt set: our own wording, see fidelity doc.
IMPLEMENT = """Implement ONE new variant for the agent-harness slot `{slot}`, as a NEW file. The library is additive:
do not modify default.py; write a sibling file with a new snake_case variant name.

Finding to address (general mechanism, never task-specific):
{finding}

Slot protocol (must keep exactly):
{proto}

Existing default implementation of the slot (copy and modify it):
```python
{code}
```

Rules: same imports style (stdlib, json, re, `benchmarks.common`, `h0.protocols` only); the file must end with
`def register(reg): reg.register("{slot}", "<name>", lambda c: <Class>(**c), "<one-line DESCRIPTION of when this
variant helps>", config_schema={{...}}, niche={{...}})`. The DESCRIPTION is what a per-task composer reads to decide
when to select the variant, so state the situations it is for. Never mention task names, ids, or entities.
NICHE names the cell your variant occupies (axis: value pairs); it must differ from every existing variant's cell:
{niches}

Output exactly one file block:
### FILE: variants/{slot}/<name>.py
```python
<complete file>
```"""

FIX = ("\n\nYour previous answer FAILED the validation gate:\n{glog}\n"
       "Fix it (only stdlib, json, re, benchmarks.common, h0.protocols imports) and output the complete file.")

REPAIR = ("\n\nA reviewer rejected the previous implementation for this code defect (fix ONLY this, keep the mechanism):\n"
          "{brief}")

# Same-intervention judge for clustering. Our wording: the reference's judge lives in online_evo, which is not vendored.
SAME_PROMPT = """Decide whether two candidate interventions on the agent's `{slot}` module describe the SAME behavioural change.
Same means the same mechanism at the same place in the module, not merely the same symptom or the same task.

# Candidate A (the new finding)
Action: {action}
Target variant: {target}
Behavioural delta: {delta}
Causal hypothesis: {why}

# Candidate B (an open proposal)
Action: {p_action}
Target variant: {p_target}
Behavioural delta: {p_delta}
Causal hypothesis: {p_why}

Answer with one JSON object and nothing else:
{{"same": true or false, "reason": "<one sentence>"}}"""

PROTO = {
    "agent_loop": "run(self, task, env, h, llm, rec) -> LoopOutcome   # h.context_mgmt/.tool_policy/.memory/.verifier/.system_prompt",
    "context_mgmt": "build(self, system, task, history, memory_notes) -> list[dict] (OpenAI messages; keep tool-call pairs intact)",
    "tool_policy": "tools(self, task) -> list[dict]; parse(self, resp, task) -> list[Action]; format_observation(self, action, result, task) -> str",
    "memory": ("recall(self, task) -> str; update(self, task, outcome, success, trajectory) -> None   # NOTE: every "
               "episode builds a fresh harness and update() is never called, so nothing persists across episodes"),
    "verifier": "check(self, task, action, state, env_done) -> Verdict(accept: bool, feedback: str)",
}

_VERDICT_TAG = re.compile(r"<review_verdict\b([^>]*)>")
_ATTR = re.compile(r'(\w+)\s*=\s*"([^"]*)"')


# ---------------------------------------------------------------- records -> TrialSummary
def _stats(rec: dict) -> dict:
    """steps and repeat_ratio from the trajectory; infra-error records have no trajectory to read."""
    if rec.get("error") or not rec.get("trajectory_path"):
        return {"steps": 0, "repeat_ratio": 0.0}
    return C.traj_stats(rec["trajectory_path"])


def to_summary(rec: dict, idx: int) -> TrialSummary:
    """Our per-episode record as ModularRSI's TrialSummary. An infra/harness error is reward=None, which the router
    treats as 'no verdict' (not a fail), exactly like a harbor exception."""
    err = rec.get("error")
    return TrialSummary(
        task_name=rec["task_id"],
        trial_name=f"{rec['task_id']}#{idx}",
        reward=None if err else (1.0 if rec["success"] else 0.0),
        exception_type=str(err).split(":", 1)[0] if err else None,
        exception_message=str(err) if err else None,
        n_episodes=rec["steps"],
        n_input_tokens=rec.get("tokens", 0),
        n_output_tokens=0,
        repeated_command_ratio=rec["repeat_ratio"],
        trial_dir=None,
        bundle=None,
    )


def _instr(rec: dict) -> str:
    return instruction_of(rec)[:800]


def _render(rec: dict, **kw) -> str:
    return C.summarize_trajectory(rec["trajectory_path"], max_chars=800, **kw)


# ---------------------------------------------------------------- evidence
def _blind_evidence(pairs: list[dict]) -> str:
    """Reviewer evidence: the trajectories with NO outcome, rolls unlabelled (reward-blind review)."""
    out = []
    for p in pairs:
        out.append(f"## task {p['task']}\nTask: {_instr(p['fail'])}")
        for i, r in enumerate(p["rolls"], 1):
            out.append(f"ROLL {i}:\n{C.summarize_trajectory(r['trajectory_path'], show_outcome=False)}")
    return "\n\n".join(out) or "(no diagnosed tasks in the batch)"


# ---------------------------------------------------------------- investigation
def _finding(text: str, slot: str, tid: str) -> dict:
    """The reference's <contrast_finding> parser. Only PARSE_OK / PARSE_SALVAGED carry a verdict; otherwise the
    finding is not a culprit, and 'parse' says why."""
    blocks = TA._CONTRAST_FINDING_RE.findall(text or "")
    if not blocks:
        f, status = None, TA.PARSE_FAILED
    else:
        f, status = TA.loads_finding_block(blocks[-1])
    f = dict(f or {})
    has_verdict = status in (TA.PARSE_OK, TA.PARSE_SALVAGED)
    f.update(slot=slot, task=tid, parse=status,
             is_culprit=has_verdict and as_bool(f.get("is_culprit")),
             fixable_now=has_verdict and as_bool(f.get("fixable_now")))
    return f


def investigate(client, bench: str, slot: str, pairs: list[dict], code: str) -> list[dict]:
    lens = TA._module_lens(LENS_KEY[slot])
    out = []
    for p in pairs:
        fail, passing = p["fail"], p["pass"]
        if passing is not None:
            pass_block, pass_origin = _render(passing), ""
        else:
            pass_block = ("(no passing roll available this epoch — diagnose the failure alone: "
                          f"what in `{slot}` kept it from finishing?)")
            pass_origin = " — NONE this epoch"
        prompt = P.CONTRAST_INVESTIGATION.format(
            locked=slot, covers=lens["covers"], yardstick=lens["yardstick"], probes=lens["probes"],
            task=_instr(fail) or p["task"], pass_origin=pass_origin, pass_block=pass_block,
            fail_block=_render(fail), evidence_field=P.CONTRAST_DIVERGENCE_FIELD)
        prompt += f"\n# Current `{slot}` module code (read inline; the reference reads it with tools)\n```python\n{code[:6000]}\n```\n"
        r = client.chat([{"role": "user", "content": prompt}], tag=f"b2:investigate:{bench}", max_tokens=2000,
                        fallback_no_reasoning=True)
        out.append(_finding(r.content, slot, p["task"]))
    return out


def investigate_efficiency(client, bench: str, slot: str, items: list[dict]) -> list[dict]:
    out = []
    for p in items:
        prompt = P.EFFICIENCY_INVESTIGATION.format(
            locked=slot, task=_instr(p["fail"]) or p["task"],
            roll_block="## Wasteful roll (passed)\n" + _render(p["fail"]))
        r = client.chat([{"role": "user", "content": prompt}], tag=f"b2:efficiency:{bench}", max_tokens=2000,
                        fallback_no_reasoning=True)
        out.append(_finding(r.content, slot, p["task"]))
    return out


# ---------------------------------------------------------------- verdict
def parse_verdict(text: str) -> dict | None:
    """The last <review_verdict> tag that passes the reference validate_attrs. A quoted template with 'accept|reject'
    fails validation and is ignored."""
    found = []
    for m in _VERDICT_TAG.finditer(text or ""):
        attrs = {k: v for k, v in _ATTR.findall(m.group(1))}
        if validate_attrs(attrs) is None:
            found.append(_normalize(attrs))
    return found[-1] if found else None


# ---------------------------------------------------------------- routing and clustering (steps 3-4)
def _entries(reg) -> list[SimpleNamespace]:
    """Our H0 variants in the archive view clustering reads. Every H0 variant is live, so no successor mapping occurs."""
    return [SimpleNamespace(type=i.slot, name=i.name, status="active", parent_ids=[]) for i in reg.infos()]


def route_finding(client, bench: str, rec: BL.FindingRecord, reg) -> tuple[CL.Routing | None, str, bool]:
    """ModularRSI's routing step for one finding: one call, validated by routing.validate_routing.
    Returns (routing, reason, retryable). A reply cut off at the token ceiling is retryable, not a verdict."""
    slot = rec.lens
    active = [(f"{slot}/{i.name}", i.description) for i in reg.infos(slot)]
    prompt = RT.build_routing_instruction(finding=rec.raw_finding, locked_type=slot, active_variants=active)
    r = client.chat([{"role": "user", "content": prompt}], tag=f"b2:route:{bench}", max_tokens=1500,
                    fallback_no_reasoning=True)
    raw = RT.parse_routing(r.content)
    if raw is None:
        cut = RT.looks_truncated(r.content)
        return None, ("reply cut off at the token ceiling" if cut else "no <routing> block"), cut
    try:
        d = RT.validate_routing(raw, active_quals=[q for q, _ in active], locked_type=slot)
    except RT.InvalidRouting as exc:
        return None, str(exc), False
    return CL.Routing(lane=d.lane, action=d.action, target_variant=d.target_variant,
                      behavioral_delta=d.behavioral_delta, causal_hypothesis=d.causal_hypothesis,
                      rationale=d.rationale, dismissals=d.dismissals, other_module=d.other_module), "", False


class Judge:
    """ClusterHooks: the two semantic judgements clustering needs.

    same_intervention is one call per open candidate of the same module. successor_covers is never reached in B2,
    because no H0 variant is retired (resolve_live_variant maps only retired variants)."""

    def __init__(self, client, bench: str, lens_of: dict[str, str]):
        self.client, self.bench, self.lens_of = client, bench, lens_of

    def same_intervention(self, finding, routing, proposal):
        if not proposal.finding_ids or self.lens_of.get(proposal.finding_ids[0]) != finding.lens:
            return False, "different module"
        prompt = SAME_PROMPT.format(
            slot=finding.lens, action=routing.action, target=routing.target_variant or "(new)",
            delta=routing.behavioral_delta, why=routing.causal_hypothesis,
            p_action=proposal.action, p_target=proposal.target_variant or "(new)",
            p_delta=proposal.behavioral_delta, p_why=proposal.causal_hypothesis)
        r = self.client.chat([{"role": "user", "content": prompt}], tag=f"b2:same:{self.bench}", max_tokens=300,
                             fallback_no_reasoning=True)
        obj = extract_json(r.content)
        if not isinstance(obj, dict) or not isinstance(obj.get("same"), bool):
            return None, "judge reply had no boolean 'same'"
        return obj["same"], str(obj.get("reason", ""))[:300]

    def successor_covers(self, finding, successor_qual):
        return False, "not reachable in B2: no retired H0 variant"


def route_and_cluster(client, bench: str, ws: Path, step: str, recs: list[BL.FindingRecord], reg, rd: dict,
                      lens_of: dict[str, str] | None = None) -> None:
    """Steps 3-4. Non-fixable culprits stay in the backlog (findings.jsonl) and are not routed."""
    judge = Judge(client, bench, lens_of if lens_of is not None else {r.finding_id: r.lens for r in recs})
    entries = _entries(reg)
    rows = []
    for rec in recs:
        if not (rec.is_culprit and rec.raw_finding.get("fixable_now")):
            continue
        routing, reason, retryable = route_finding(client, bench, rec, reg)
        if routing is None:
            DS.record(ws, finding_id=rec.finding_id, kind=DS.RETRYABLE if retryable else DS.INVALID,
                      step=step, reason=reason)
            rows.append({"finding": rec.finding_id, "decision": "retryable" if retryable else "invalid_routing",
                         "reason": reason[:200]})
            continue
        out = CL.cluster_finding(ws, finding=rec, routing=routing, hooks=judge, step=step, archive_entries=entries)
        rows.append({"finding": rec.finding_id, "lane": routing.lane, "decision": out.decision,
                     "proposal": out.proposal_id, "reason": out.reason[:200]})
    rd["clustering"] = rows


# ---------------------------------------------------------------- implementation (steps 6-7)
def _implement(client, bench: str, slot: str, proposal: str, stage: Path, extra: str = "") -> dict:
    """One implementer call in its own staging tree; up to 2 attempts (the static gate's log is fed back)."""
    # additive library: never the default, and never an existing variant's file (reusing a promoted variant's name
    # would silently replace it, and the failure path below would delete it)
    taken = sorted(p.stem for p in (stage / "variants" / slot).glob("*.py"))
    allowed = re.compile(rf"^variants/{slot}/(?!(?:{'|'.join(map(re.escape, taken))})\.py$)[a-z0-9_]+\.py$")
    code = (stage / "variants" / slot / "default.py").read_text(encoding="utf-8")
    prompt = IMPLEMENT.format(slot=slot, finding=proposal + extra, proto=PROTO[slot], code=code,
                              niches=_niches(stage, slot))
    glog = "not run"
    for attempt in range(2):
        r = client.chat([{"role": "user", "content": prompt}], tag=f"b2:implement:{bench}", max_tokens=6000,
                        fallback_no_reasoning=True)
        written, _ = apply_files(stage, reply_files(r), allowed)
        if not written:
            glog = ("no ### FILE block for an allowed path was found in the answer (a NEW file "
                    f"variants/{slot}/<name>.py; names already taken: {taken})")
        else:
            ok, glog = C.static_gate(stage)
            if ok:  # activation precondition: the new variant must register
                reg = load_registry(stage)
                names = [i.name for i in reg.infos(slot) if i.source in written]
                if names and not reg.load_errors:
                    return {"written": written, "names": names, "gate": "ok", "attempts": attempt + 1}
                glog = f"variant not registered: {reg.load_errors}"
        for w in written:
            (stage / w).unlink(missing_ok=True)
        prompt += FIX.format(glog=glog[-1200:]) + gate_hint(glog)
    return {"written": [], "names": [], "gate": f"failed: {glog[-300:]}", "attempts": 2}


def _review(client, bench: str, slot: str, stage: Path, written: str, proposal: str, pairs: list[dict]) -> dict:
    code = (stage / written).read_text(encoding="utf-8")
    diff = "\n".join(difflib.unified_diff([], code.splitlines(), fromfile="/dev/null", tofile=written, lineterm=""))
    prompt = P.REVIEW.format(diff_text=diff[:8000] or "(empty)", intent=proposal.strip() or "(no intent stated)",
                             trial_summaries=_blind_evidence(pairs)[:20000])
    r = None
    for _ in range(2):  # the verdict must be a validated tag; one retry, then the reply is unusable
        r = client.chat([{"role": "user", "content": prompt}], tag=f"b2:review:{bench}", max_tokens=1500,
                        fallback_no_reasoning=True)
        v = parse_verdict(r.content)
        if v:
            return {**v, "raw": r.content.strip()[-300:]}
    return {"decision": "reject", "reject_class": "proposal", "reason": "no valid verdict tag from the reviewer",
            "repair_brief": "", "raw": r.content.strip()[-300:]}


def _prepare(parent: Path, dest: Path) -> Path:
    """A lane's private staging tree: a copy of the parent's variants (dual_implement's `prepare` hook; the reference
    copies its own modules/ directory here)."""
    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    shutil.copytree(Path(parent) / "variants", dest / "variants",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for f in ("bundle.json", "system_prompt.txt"):
        if (Path(parent) / f).exists():
            shutil.copy2(Path(parent) / f, dest / f)
    return dest


def _brief_text(brief: DI.LaneBrief) -> str:
    """The proposal and ALL of its supporting findings, as the implementer reads them. The reference's brief text is
    written for a tool-using editor, so only its content (never its tool instructions) is used here."""
    p = brief.proposal
    ev = "\n\n".join(f"### finding `{f.finding_id}` (task {f.task})\n"
                     f"```json\n{json.dumps(f.raw_finding, indent=2, ensure_ascii=False)[:DI.MAX_FINDING_CHARS]}\n```"
                     for f in brief.findings)
    miss = (f"\n({len(brief.missing_finding_ids)} supporting finding(s) could not be read back from the ledger: "
            f"{', '.join(brief.missing_finding_ids)})") if brief.missing_finding_ids else ""
    return (f"Lane: {p.lane}; action: {p.action}; target variant: {p.target_variant or '(new variant)'}\n"
            f"Behavioural delta: {p.behavioral_delta}\nCausal hypothesis: {p.causal_hypothesis}\n"
            f"Evidence ({len(brief.findings)} finding(s)):\n{ev or '(none)'}{miss}")


async def routing_check(client, bench: str, tree: Path, slot: str, name: str, train_ids: list[str],
                        by_task: dict) -> RP.RoutingProbeResult:
    """Routing probe: does the composer, built on this tree, select the new variant on some train task?"""
    reg = load_registry(tree)
    base = root_bundle(tree, reg)
    composer = llm_composer_factory(client, bench, [])

    async def choose(instruction: str) -> str | None:
        chosen = composer(SimpleNamespace(task_id="probe", instruction=instruction), reg, base)
        return (chosen.get(slot) or {}).get("name")

    instructions = {t: _instr(by_task[t][0]) for t in train_ids}
    return await RP.probe_routing(target_variant=name, tasks=train_ids, instructions=instructions, choose=choose)


DESCRIBE = """A variant of the `{slot}` slot was built for this change:
{finding}

Its current registry description is:
{description}

The composer chooses a variant from the descriptions alone, and it did not choose this variant for any intended task.
Rewrite the description once. It must state a selection criterion (when to pick this variant, in terms of the task
situation). Do not name a task family, and do not state a runtime property in place of a criterion.
Reply with exactly one line: <description>...</description>"""


def _set_description(src: str, text: str) -> str | None:
    """`src` with the description (4th argument of `reg.register`) replaced, or None when no such call or text exists."""
    if not text:
        return None
    raw = src.encode("utf-8")
    starts = [0]
    for ln in raw.splitlines(keepends=True):
        starts.append(starts[-1] + len(ln))
    for node in ast.walk(ast.parse(src)):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "register"
                and len(node.args) >= 4 and isinstance(node.args[3], ast.Constant)
                and isinstance(node.args[3].value, str)):
            arg = node.args[3]
            head = raw[:starts[arg.lineno - 1] + arg.col_offset]
            tail = raw[starts[arg.end_lineno - 1] + arg.end_col_offset:]
            return (head + json.dumps(text, ensure_ascii=False).encode("utf-8") + tail).decode("utf-8")
    return None


def _describe_variant(client, bench: str, stage: Path, slot: str, name: str, finding: str) -> bool:
    """One description rewrite for a variant the composer never selected. The file is kept only if the static gate
    still passes; otherwise it is restored and False is returned."""
    info = next((i for i in load_registry(stage).infos(slot) if i.name == name), None)
    if info is None:
        return False
    path = stage / info.source
    old = path.read_text(encoding="utf-8")
    prompt = DESCRIBE.format(slot=slot, finding=finding[:1500], description=info.description)
    r = client.chat([{"role": "user", "content": prompt}], tag=f"b2:describe:{bench}", max_tokens=400,
                    fallback_no_reasoning=True)
    m = re.search(r"<description>(.*?)</description>", r.content or "", re.S)
    new = _set_description(old, " ".join(m.group(1).split()) if m else "")
    if new is None:
        return False
    path.write_text(new, encoding="utf-8")
    ok, _ = C.static_gate(stage)
    if not ok:
        path.write_text(old, encoding="utf-8")
    return ok


async def routing_diagnosis(client, bench: str, stage: Path, slot: str, name: str, finding: str, train_ids: list[str],
                            by_task: dict) -> dict:
    """Routing is a diagnostic, not a promotion gate. Probe once; if no intended task selects the variant, rewrite its
    description once and probe again. Both verdicts are recorded and neither one rejects the lane."""
    first = await routing_check(client, bench, stage, slot, name, train_ids, by_task)
    diag = {"first": first.verdict, "first_picks": first.picks, "rewritten": False,
            "final": first.verdict, "final_picks": first.picks}
    if first.verdict != RP.VERDICT_UNPROVEN:
        return diag
    diag["rewritten"] = _describe_variant(client, bench, stage, slot, name, finding)
    if diag["rewritten"]:
        second = await routing_check(client, bench, stage, slot, name, train_ids, by_task)
        diag.update(final=second.verdict, final_picks=second.picks)
    return diag


def niche_reject(stage: Path, slot: str, name: str) -> str | None:
    """Reference S5 niche-dedup gate (online_evo._niche_dedup_reject) on the H0 registry: a new variant must declare a
    NICHE, and must not land in the cell of another active variant of its slot (our implementer never declares
    SUPERSEDES, so any collision is a near-duplicate). Best-effort like the reference: an error passes."""
    try:
        infos = load_registry(stage).infos(slot)
        new = next(i for i in infos if i.name == name)
        key = NI.niche_key(slot, new.niche)
        if not key:
            return (f"{slot}/{name} declares no NICHE — every new variant must name its cell "
                    "(niche={axis: value} in register)")
        clash = sorted(i.name for i in infos if i.name != name and NI.niche_key(slot, i.niche) == key)
        if clash:
            return f"{slot}/{name} lands in the occupied niche cell {dict(key)} of {clash} without superseding it"
    except Exception:
        return None
    return None


def _niches(root: Path, slot: str) -> str:
    try:
        return "\n".join(f"- {i.name}: {i.niche}" for i in load_registry(root).infos(slot)) or "- (none)"
    except Exception:
        return "- (unknown)"


async def _lane_check(client, bench: str, brief: DI.LaneBrief, lens_of: dict[str, str], pairs: list[dict],
                      by_task: dict, repair: dict[str, str]) -> DI.LaneResult:
    """One lane's gates: implementation and reviewer. Routing is recorded as a diagnosis, never as a rejection."""
    p = brief.proposal
    slot = lens_of.get(p.finding_ids[0]) if p.finding_ids else None
    if slot is None:
        return DI.LaneResult(passed=False, detail={"reject": "implementation", "reason": "proposal has no lens"})
    stage = Path(brief.staging_dir)
    text = _brief_text(brief)
    extra = REPAIR.format(brief=repair[brief.proposal_id]) if brief.proposal_id in repair else ""
    impl = _implement(client, bench, slot, text, stage, extra)
    if impl["gate"] != "ok":
        return DI.LaneResult(passed=False, detail={"reject": "implementation", "reason": impl["gate"]})
    written = impl["written"][0]
    nr = niche_reject(stage, slot, impl["names"][0])  # reference order: smoke -> niche dedup -> review
    if nr is not None:
        return DI.LaneResult(passed=False, detail={"reject": "implementation", "reason": nr})
    rv = _review(client, bench, slot, stage, written, text, pairs)
    if rv["decision"] != "accept":
        return DI.LaneResult(passed=False, detail={"reject": rv["reject_class"], "reason": rv["reason"],
                                                   "repair_brief": rv["repair_brief"]})
    name = impl["names"][0]
    routing = await routing_diagnosis(client, bench, stage, slot, name, text, sorted(by_task), by_task)
    diff = hashlib.sha1((stage / written).read_bytes()).hexdigest()  # after any description rewrite
    return DI.LaneResult(passed=True, diff_hash=diff, detail={"slot": slot, "variant": name, "written": impl["written"],
                                                              "text": text, "reject": None, "routing": routing})


def _lane_runner(client, bench: str, lens_of: dict, pairs: list[dict], by_task: dict, repair: dict[str, str]):
    async def run_lane(brief: DI.LaneBrief) -> DI.LaneResult:
        return await _lane_check(client, bench, brief, lens_of, pairs, by_task, repair)
    return run_lane


def implement_picks(client, bench: str, ws: Path, step: str, picks: list, inc_root: Path, lens_of: dict,
                    pairs: list[dict], by_task: dict, repair: dict[str, str] | None = None) -> list[DI.LaneOutcome]:
    return asyncio.run(DI.implement_lanes(
        ws, picks, parent_dir=Path(inc_root), step=step,
        run_lane=_lane_runner(client, bench, lens_of, pairs, by_task, repair or {}),
        prepare=_prepare, repair_briefs=repair or {}))


def dual_implement(client, bench: str, ws: Path, step: str, picks: list, inc_root: Path, lens_of: dict,
                   pairs: list[dict], by_task: dict) -> list[DI.LaneOutcome]:
    """Step 6: both lanes, then one repair pass for lanes whose reviewer named a code defect."""
    outcomes = implement_picks(client, bench, ws, step, picks, inc_root, lens_of, pairs, by_task)
    repair = {o.proposal_id: o.result.detail["repair_brief"] for o in outcomes
              if o.result and not o.result.passed and o.result.detail.get("repair_brief")}
    if repair:
        for pid in repair:  # ATTEMPTED -> REJECTED_IMPLEMENTATION: the direction keeps its retry
            PP.transition(ws, pid, step=step, to=PP.REJECTED_IMPLEMENTATION, reason="reviewer: code defect, repair pass")
        retry = [p for p in picks if p.proposal_id in repair]
        second = {o.proposal_id: o for o in implement_picks(client, bench, ws, step, retry, inc_root, lens_of,
                                                             pairs, by_task, repair)}
        outcomes = [second.get(o.proposal_id, o) for o in outcomes]
    return outcomes


def merge_lanes(client, bench: str, inc_root: Path, cand: Path, outcomes: list[DI.LaneOutcome], pairs: list[dict],
                by_task: dict, work: Path) -> tuple[list[dict], dict[str, str]]:
    """Step 7: promote the first passing lane onto the candidate; rebase the second onto it and re-run its tree-wide gates.
    Returns (merged, failed) where failed maps proposal_id -> reason."""
    by_pid = {o.proposal_id: o for o in outcomes}
    merged, failed = [], {}
    for st in PR.plan_promotions(DI.to_candidates(outcomes)):
        o = by_pid[st.proposal_id]
        det = o.result.detail
        slot, name, written = det["slot"], det["variant"], det["written"]
        if not st.rebase_required:
            for w in written:
                shutil.copy2(o.staging_dir / w, cand / w)
            merged.append({"proposal": st.proposal_id, "slot": slot, "variant": name, "rebased": False})
            continue
        rb = RB.rebase_onto(staging=o.staging_dir, old_parent=inc_root, new_parent=cand,
                            dest=work / f"rebase_{st.proposal_id}")
        if rb.conflicts:
            failed[st.proposal_id] = f"rebase conflict on {rb.conflicts}"
            continue
        if rb.absorbed:  # the promoted lane already made exactly this change
            merged.append({"proposal": st.proposal_id, "slot": slot, "variant": name, "rebased": True, "absorbed": True})
            continue
        reusable, _ = PR.gates_after_rebase(rb.diff_hash_before, rb.diff_hash_after)
        ok, glog = C.static_gate(rb.dest)
        if not ok:
            failed[st.proposal_id] = f"rebased tree failed the static gate: {glog[-200:]}"
            continue
        if "review" not in reusable:
            rv = _review(client, bench, slot, rb.dest, written[0], det["text"], pairs)
            if rv["decision"] != "accept":
                failed[st.proposal_id] = f"rebased tree rejected on review: {rv['reason'][:200]}"
                continue
        shutil.rmtree(cand)
        shutil.copytree(rb.dest, cand)
        merged.append({"proposal": st.proposal_id, "slot": slot, "variant": name, "rebased": True,
                       "reusable_gates": list(reusable), "routing": det.get("routing")})
    return merged, failed


def close_lanes(ws: Path, step: str, outcomes: list[DI.LaneOutcome], merged_ids: set[str], promoted: bool,
                failed: dict[str, str]) -> None:
    """Move every attempted proposal to the state its outcome earned. Lanes never attempted are already OPEN."""
    for o in outcomes:
        if not o.attempted:
            continue
        cur = PP.get_proposal(ws, o.proposal_id)
        if cur is None or cur.state != PP.ATTEMPTED:
            continue
        det = o.result.detail if o.result else {}
        if o.proposal_id in merged_ids and promoted:
            to, why = PP.PROMOTED, "promoted"
        elif o.result and o.result.passed:
            to, why = PP.REJECTED_IMPLEMENTATION, failed.get(o.proposal_id, "passed gates, not promoted")
        elif det.get("reject") == "proposal":
            to, why = PP.REJECTED_PROPOSAL, det.get("reason", "reviewer: wrong direction")
        else:
            to, why = PP.REJECTED_IMPLEMENTATION, det.get("reason") or o.error or "implementation rejected"
        PP.transition(ws, o.proposal_id, step=step, to=to, reason=str(why)[:300])


def confirm_check(val: list[dict], comp_log: list, merged: list[dict]) -> list[dict]:
    """Step 8, confirm: paired regression of each merged variant against default, on the validation rolls.
    With one roll per task a task never has both variants, so this check cannot fire at smoke scale (see fidelity doc)."""
    chosen = {e["task"]: e["chosen"] for e in comp_log}
    samples = []
    for r in val:
        ch = chosen.get(r["task_id"], {})
        bundle = {s: (ch.get(s) or {}).get("name") or "default" for s in SLOTS}
        reward = None if r.get("error") else (1.0 if r["success"] else 0.0)
        samples.append((r["task_id"], bundle, reward))
    out = []
    for m in merged:
        out += CF.find_regressions(samples, m["slot"], "default", candidates=[m["variant"]], min_shared=3, margin=0.34)
    return out


# ---------------------------------------------------------------- composer
def _composer_choice(obj) -> dict[str, str]:
    """{slot: variant} from the composer reply. Also accepts {slot: {"name": v}}, {"choices"/"bundle": {...}}
    and [{"slot": s, "variant": v}, ...]."""
    if isinstance(obj, dict):
        for k in ("choices", "bundle", "selection", "composition"):
            if isinstance(obj.get(k), (dict, list)):
                obj = obj[k]
                break
    if isinstance(obj, list):
        obj = {str(d.get("slot")): d.get("variant") or d.get("name") for d in obj if isinstance(d, dict)}
    if not isinstance(obj, dict):
        return {}
    out = {}
    for s, v in obj.items():
        if isinstance(v, dict):
            v = v.get("name") or v.get("variant")
        if isinstance(v, str) and v.strip():
            out[str(s).strip()] = v.strip().strip("`")
    return out


def llm_composer_factory(client, bench: str, log: list):
    def composer(task, reg, base):
        multi = {s: reg.infos(s) for s in SLOTS if len(reg.infos(s)) > 1}
        if not multi:
            return base
        catalog = "\n".join(f"\n## {s}  (default: {base[s]['name']})\n" + "\n".join(f"- {i.name}: {i.description}" for i in infos)
                            for s, infos in multi.items())
        prompt = P.composer_prompt(task.instruction[:2000], catalog)
        r = client.chat([{"role": "user", "content": prompt}], tag=f"b2:composer:{bench}", max_tokens=1000,
                        fallback_no_reasoning=True)
        chosen = {s: {"name": n} for s, n in _composer_choice(extract_json(r.content)).items()
                  if s in multi and reg.has(s, n)}
        log.append({"task": task.task_id, "chosen": chosen, "raw": r.content[:200]})
        return chosen
    return composer


# ---------------------------------------------------------------- run
def run(bench: str, shared: dict, client, cfg=C.SMOKE, tag: str = "smoke") -> dict:
    ws = C.RUNS / "b2" / bench
    ws.mkdir(parents=True, exist_ok=True)
    for d in ("backlog", "staging", "work"):  # per-run state: a backlog from an earlier run would leak old proposal ids
        shutil.rmtree(ws / d, ignore_errors=True)
    out = C.OUT / f"b2_{bench}.jsonl"
    tasks = shared["tasks"]
    rcfg = RouterConfig(k=cfg["k"])
    ledger = Ledger.load(ws)  # persisted to <ws>/router_ledger.json
    inc_root, inc_composer = C.H0_ROOT, False
    log = {"method": "b2", "bench": bench, "k": cfg["k"], "rounds": []}
    evidence = shared["h0_train"]  # window 1: the shared H0 evidence, K rolls on every train task
    train_ids = tasks["train"][1]
    per_batch = max(1, cfg["n_val"] // cfg["k"])  # the shared per-round budget: n_val episodes = per_batch tasks x K
    batches: list[list[str]] = []
    lens_of: dict[str, str] = {}  # finding id -> slot, over every round's backlog rows

    def next_evidence(ri: int) -> list[dict]:
        """Reference windows: the next window learns from K rolls of the CURRENT library on a fresh batch of train
        tasks (rotating through the train set). Not run after the last round."""
        nonlocal evidence
        if ri >= cfg["rounds"]:
            return evidence
        start = ((ri - 1) * per_batch) % len(train_ids)
        batch = (train_ids + train_ids)[start: start + per_batch]
        batches.append(batch)
        recs = []
        for k in range(1, cfg["k"] + 1):
            recs += C.evaluate(bench, tasks["train"][0], batch, inc_root, client, f"b2_{bench}_r{ri}_evid{k}", out,
                               composer=llm_composer_factory(client, bench, []) if inc_composer else None,
                               workers=cfg["workers"], label={"method": "b2", "phase": "evidence", "round": ri, "roll": k})
        return recs
    for ri in range(1, cfg["rounds"] + 1):
        C.budget_check(f"b2[{bench}] round {ri}")
        step = f"r{ri}"
        rd = {"round": ri}
        rd["recovered"] = [{"proposal": x.proposal_id, "action": x.action} for x in LS.recover(ws, step=step)]
        train = [{**r, **_stats(r)} for r in evidence]
        summaries, rec_of, by_task = [], {}, defaultdict(list)
        for i, rec in enumerate(train):
            s = to_summary(rec, i)
            summaries.append(s)
            rec_of[s.trial_name] = rec
            by_task[rec["task_id"]].append(rec)
        res = route_batch(summaries, ledger=ledger, epoch=ri - 1, cfg=rcfg, history_pass_lookup=None)
        rd["buckets"] = {b: t for b, t in res.buckets.items() if t}
        pairs = [{"task": d.task, "bucket": d.bucket, "fail": rec_of[d.contrast_fail.trial_name],
                  "pass": rec_of[d.contrast_pass.trial_name] if d.contrast_pass else None,
                  "rolls": by_task[d.task]} for d in res.diagnose[:MAX_DIAG]]
        eff = [{"task": e.task, "fail": rec_of[e.contrast_fail.trial_name], "pass": None, "rolls": by_task[e.task]}
               for e in res.efficiency[:MAX_DIAG]]
        rd["pair_tasks"] = [p["task"] for p in pairs]
        rd["efficiency_tasks"] = [p["task"] for p in eff]

        findings, eff_findings = {}, {}
        for slot in SLOTS:
            code = (inc_root / "variants" / slot / "default.py").read_text(encoding="utf-8")
            if pairs:
                findings[slot] = investigate(client, bench, slot, pairs, code)
        # reference: the efficiency investigator runs only when the contrast pass found no culprit
        if eff and not any(f["is_culprit"] for fs in findings.values() for f in fs):
            for slot in SLOTS:
                eff_findings[slot] = investigate_efficiency(client, bench, slot, eff)
        rd["findings"] = {s: [{k: f.get(k) for k in ("task", "parse", "is_culprit", "fixable_now", "suggested_change")}
                              for f in fs] for s, fs in findings.items()}
        rd["efficiency_findings"] = {s: [{k: f.get(k) for k in ("task", "parse", "is_culprit", "fixable_now")}
                                         for f in fs] for s, fs in eff_findings.items()}

        # step 3: every contrast finding into the backlog, as the reference's ledger rows
        payload = [{**f, "lens": f["slot"], "parse_status": f["parse"]}
                   for s in SLOTS for f in findings.get(s, [])]
        recs = BL.ingest_step(ws, {"step": step, "findings": payload})
        rd["backlog_rows"] = len(recs)
        lens_of.update({r.finding_id: r.lens for r in recs})  # cumulative: open proposals keep findings of earlier rounds
        reg = load_registry(inc_root)

        # step 4: route and cluster the fixable culprits into proposals
        route_and_cluster(client, bench, ws, step, recs, reg, rd, lens_of)
        reflected = {r.task for r in recs if r.is_culprit and r.raw_finding.get("fixable_now")}

        # step 5: at most one proposal per lane
        picks = PF.select_portfolio(ws, max_lanes=MAX_LANES, seed=f"{bench}:{step}")
        rd["picks"] = [{"lane": p.lane, "proposal": p.proposal_id, "reason": p.reason} for p in picks]

        def settle(result: str, progress: bool = False) -> None:
            """Record the round's outcome in the ledger (reflections for the targeted tasks) and close the round."""
            rd["result"] = result
            for t in reflected:
                ledger.record_reflection(t, made_progress=progress)
            ledger.save(ws)
            log["rounds"].append(rd)

        if not picks:
            settle("no open proposal")
            evidence = next_evidence(ri)
            continue

        # step 6: dual implementation, gates, one repair pass
        outcomes = dual_implement(client, bench, ws, step, picks, inc_root, lens_of, pairs, by_task)
        rd["lanes"] = [{"proposal": o.proposal_id, "lane": o.lane, "attempted": o.attempted, "retry": o.retry,
                        "error": o.error, "passed": bool(o.result and o.result.passed),
                        **{k: v for k, v in ((o.result.detail if o.result else {}) or {}).items()
                           if k in ("reject", "reason", "routing", "variant")}} for o in outcomes]

        # step 7: promotion of the passing lanes onto a candidate tree
        cand = C.new_candidate(ws / "candidates" / step, inc_root, {"method": "b2", "round": ri})
        work = ws / "work" / step
        merged, failed = merge_lanes(client, bench, inc_root, cand, outcomes, pairs, by_task, work)
        rd["merged"] = merged
        rd["rebase_failed"] = failed
        rd["accepted"] = [(m["slot"], m["variant"]) for m in merged]
        merged_ids = {m["proposal"] for m in merged}
        if not merged:
            close_lanes(ws, step, outcomes, merged_ids, False, failed)
            shutil.rmtree(work, ignore_errors=True)
            settle("no variant passed the gates")
            evidence = next_evidence(ri)
            continue

        # step 8: integration, execution check, validation, confirm, shared promotion rule
        ok, glog = C.static_gate(cand)
        rd["integration_gate"] = "ok" if ok else glog[-500:]
        if not ok:
            close_lanes(ws, step, outcomes, merged_ids, False, failed)
            shutil.rmtree(work, ignore_errors=True)
            settle("integration failed")
            evidence = next_evidence(ri)
            continue
        (cand / "bundle.json").write_text(json.dumps({s: {"name": n} for s, n in rd["accepted"]}))
        ex = C.evaluate(bench, tasks["train"][0], tasks["train"][1][:cfg["n_check"]], cand, client, f"b2_{bench}_r{ri}_exec", out,
                        workers=cfg["workers"], label={"method": "b2", "phase": "exec_check", "round": ri})
        (cand / "bundle.json").unlink()
        rd["exec_check"] = [{"task": r["task_id"], "ok": r["success"], "error": r["error"]} for r in ex]
        if any(r["error"] for r in ex):
            close_lanes(ws, step, outcomes, merged_ids, False, failed)
            shutil.rmtree(work, ignore_errors=True)
            settle("execution check crashed")
            evidence = next_evidence(ri)
            continue
        # reference: promotion on the gates alone (smoke, niche dedup, review, sanity crash check); no reward is compared
        close_lanes(ws, step, outcomes, merged_ids, True, failed)
        shutil.rmtree(work, ignore_errors=True)
        inc_root, inc_composer = cand, True
        settle("promoted", progress=True)
        evidence = next_evidence(ri)
    log["evidence_batches"] = batches
    log["final"] = str(inc_root)
    (ws / "final.json").write_text(json.dumps({"final_root": str(inc_root), "composer": inc_composer}, indent=1))
    C.budget_check(f"b2[{bench}] test")
    comp_log = []
    test = C.evaluate(bench, tasks["test"][0], tasks["test"][1], inc_root, client, f"b2_{bench}_test", out,
                      composer=llm_composer_factory(client, bench, comp_log) if inc_composer else None,
                      workers=cfg["workers"], label={"method": "b2", "phase": "test"})
    log["test"] = {"success": C.score(test), "n": len(test), "composer_choices": comp_log}
    (ws / "log.json").write_text(json.dumps(log, indent=1, default=str))
    return {"log": log, "test": test}
