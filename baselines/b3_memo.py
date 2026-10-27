"""B3: MemoHarness on H0: experience bank + Codex-bundle controller + per-case test-time adaptation.

Follows the reference's only supported controller (`HarnessSettings.controller == "codex"`, CodexBundleController):
each iteration the controller rewrites a harness *bundle* (AGENTS.override.md, policy.json with D1..D6,
.memoharness/playbook.md, .memoharness/memory.md) from the experience bank, the bundle is published only if the
canary accepts it, and memory.md / playbook.md are re-rendered from the distilled global patterns. At test time
adapt_for_case changes only the D1..D6 config, per case (the reference's config-only prompt).

Reuses MemoHarness's own code, vendored under baselines/vendor/memoharness/ (the source repo ships no LICENSE file;
code copied with the permission of its author, see docs/baseline_fidelity.md):
  - core/models.py, bank/experience.py   per-case entries, dual-layer bank, distillation triggers (embedder -> BM25)
  - llm/distiller.py                     LLMDistiller (transport -> ChatShim)
  - controllers/codex_bundle.py          CodexBundleController: iteration prompt, bundle load/snapshot/restore
  - controllers/local_cli.py             CodexController/ClaudeCodeController: bank summary, per-task history matrix,
                                         failure excerpts, change-outcome signals, retry loop, adapt_for_case prompt
  - runtime/codex_bundle.py              bundle layout, policy payload, memory/playbook rendering
  - config/runtime.py                    canary thresholds
Only the transport is replaced (BundleController below): the reference runs the Codex CLI with file tools in the
workspace; here one call to our model gets the bundle files inline and returns the files it rewrites.

Iteration loop (reference harbor/loop.py run()): run the current harness on the train tasks -> ingest into the bank
(+ distillation triggers) -> controller proposes the next bundle -> canary against the current harness's results on
the canary tasks -> publish or restore. The best harness is the iteration with the highest train mean reward
(tokens break ties); no validation set, as in the reference. Iteration 0 is the shared H0 evidence (all K rolls).
Budget per round matches the shared protocol: cfg["n_check"] canary + cfg["n_val"] train-run episodes.

Bundle -> H0: AGENTS.override.md, policy.json (D1..D6), playbook.md and memory.md are inserted into the system prompt
(context_mgmt.extra_system; the reference's Codex agent reads the same files from its workspace). The D1..D6 numbers
H0 can apply are D3.temperature -> agent_loop.temperature, D3.max_tokens -> agent_loop.max_tokens and
D5.history_keep -> context_mgmt.keep_turns (clamped); the controller is told so.
"""
from __future__ import annotations

import json
import math
import re
import shutil
from collections import Counter
from pathlib import Path
from textwrap import dedent
from types import SimpleNamespace

from baselines import common as C
from baselines.proposer_io import extract_json, reply_files
from baselines.vendor.memoharness.bank.experience import ExperienceBank
from baselines.vendor.memoharness.config.runtime import ApiModelConfig, HarnessSettings
from baselines.vendor.memoharness.controllers import llm_controller as LC
from baselines.vendor.memoharness.controllers.codex_bundle import CodexBundleController
from baselines.vendor.memoharness.core.models import (BenchmarkCase, CaseFeatures, Diagnosis, DiagnosticSignal,
                                                      HarnessConfig, PerCaseEntry, Trajectory, make_minimal_config)
from baselines.vendor.memoharness.llm.distiller import LLMDistiller
from baselines.vendor.memoharness.runtime import codex_bundle as RB
from benchmarks.common import instruction_of

MODEL = "inclusionai/ling-3.0-flash"
EVERY_N_ENTRIES = 5             # reference experiment.json distill_every
MIN_CONSECUTIVE_FAILURES = 3    # reference default (ExperienceBank / LLMDistiller)
MAX_PATTERNS = 3                # reference LLMDistiller max_patterns
TEST_TIME_CASE_ADAPTATION = True  # per-case adapt_for_case at test; False = the selected global harness only
CONTROLLER_MAX_RETRIES = 3      # reference _run_direct_edit_harness_with_retry(max_retries=3)
_SETTINGS = HarnessSettings()   # config/runtime.py defaults
CANARY_MIN_REWARD_DELTA = _SETTINGS.controller_canary_min_reward_delta      # -0.34
CANARY_MAX_BLOCKER_INCREASE = _SETTINGS.controller_canary_max_blocker_increase  # 0
CANARY_MAX_SUCCESS_DROP = -0.2  # reference _evaluate_candidate_with_canary: success_delta < -0.2 and reward_delta <= 0
DIMS = ("D1", "D2", "D3", "D4", "D5", "D6")

# Transport for the vendored code: the reference calls an OpenAI client with the endpoint below, which we replace by
# llm.py (one model, budget guard). connection_retry_limit=0 leaves retries to llm.py.
API = ApiModelConfig(provider="openrouter", model=MODEL, api_key_env="OPENROUTER_API_KEY",
                     api_base="https://openrouter.ai/api/v1", connection_retry_limit=0)


class ChatShim:
    """OpenAI-style `chat.completions.create(...)` on top of our llm.py client: the vendored code calls this surface."""

    def __init__(self, client, tag: str):
        self._client, self._tag = client, tag
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, model=None, messages=None, temperature=None, max_completion_tokens=None, **unexpected):
        # The reference call sites pass exactly these four keywords (controller: temperature 0.2; distiller: 0.0).
        # Any other keyword would be silently lost, so it is refused instead.
        if unexpected:
            raise TypeError(f"ChatShim does not forward {sorted(unexpected)}")
        r = self._client.chat(messages, tag=self._tag, temperature=temperature,
                              max_tokens=max_completion_tokens or 2048, fallback_no_reasoning=True)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=r.content))])


# ---------------------------------------------------------------- BM25 replaces the embedding pair
def _tok(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (s or "").lower())


def _bm25(query: list[str], doc: list[str], df: Counter, n_docs: int, avgdl: float) -> float:
    tf, dl = Counter(doc), len(doc)
    return sum(math.log(1 + (n_docs - df[t] + 0.5) / (df[t] + 0.5)) * tf[t] * 2.2 / (tf[t] + 1.2 * (0.25 + 0.75 * dl / avgdl))
               for t in set(query) if t in tf)


class BM25ExperienceBank(ExperienceBank):
    """Reference ExperienceBank. The embedding pair (_embed_text, _cosine_similarity) is replaced by BM25 over the
    bank's instructions: the query's BM25 against one document, divided by the query's self-score so it lies in [0, 1]
    like the cosine it replaces. _case_similarity and retrieve_similar_cases_for_case are the reference code."""

    def __init__(self) -> None:
        super().__init__(min_consecutive_failures=MIN_CONSECUTIVE_FAILURES)
        self.frozen = False

    @classmethod
    def from_snapshot(cls, path: Path) -> "BM25ExperienceBank":
        """Rebuild a bank from the inspection JSON that ExperienceBank.save writes next to its pickle (entries are
        re-added in order, so the indexes and case_stats are recomputed exactly)."""
        from baselines.vendor.memoharness.core.models import GlobalPattern
        snap = json.loads(Path(path).read_text())
        bank = cls()
        for e in snap["entries"]:
            d = e["diagnosis"]
            bank.add_entry(PerCaseEntry(
                case_id=e["case_id"], iteration=e["iteration"], case_features=CaseFeatures(**e["case_features"]),
                config=HarnessConfig(**e["config"]), delta_from_prev=e["delta_from_prev"],
                trajectory=Trajectory(**e["trajectory"]), primary_reward=e["primary_reward"],
                cost_actual=e["cost_actual"],
                diagnosis=Diagnosis(success=d["success"], analysis=d["analysis"],
                                    diagnostic_signal=DiagnosticSignal(**d["diagnostic_signal"]))))
        bank.global_patterns = [GlobalPattern(**{**g, "iteration_range": tuple(g["iteration_range"])})
                                for g in snap["global_patterns"]]
        bank.last_distill_entry_count = snap["meta"]["last_distill_entry_count"]
        return bank

    def add_entry(self, entry: PerCaseEntry) -> bool:
        if self.frozen:
            raise RuntimeError("experience bank is frozen (test time)")
        return super().add_entry(entry)

    def _embed_text(self, text: str):
        return _tok(text)

    def _cosine_similarity(self, query: list[str], doc: list[str]) -> float:
        if not query or not doc:
            return 0.0
        corpus = [_tok(e.case_features.instruction or e.case_id) for e in self.entries]
        if not corpus:
            return 0.0
        n_docs = len(corpus)
        avgdl = sum(map(len, corpus)) / n_docs or 1.0
        df = Counter(t for d in corpus for t in set(d))
        self_score = _bm25(query, query, df, n_docs, avgdl)
        if self_score <= 0:
            return 0.0
        return min(1.0, _bm25(query, doc, df, n_docs, avgdl) / self_score)


# ---------------------------------------------------------------- config mapping
def norm_dim(v) -> str | None:
    """'D3', 'd3', 'D3 Generation', 'dimension 3' -> 'D3'."""
    m = re.search(r"\bd(?:im(?:ension)?)?[\s_-]*([1-6])\b", str(v or ""), re.I)
    return f"D{m.group(1)}" if m else None


_H0_NUMBERS = {("D3", "temperature"): 0.0, ("D3", "max_tokens"): 2048, ("D5", "history_keep"): 30}


def _num(cfg: HarnessConfig, dim: str, key: str, fallback: HarnessConfig | None) -> float:
    """The value as a finite number; else the fallback config's value; else H0's default."""
    for c in (cfg, fallback):
        try:
            v = float(getattr(c, dim)[key])
            if math.isfinite(v):
                return v
        except (AttributeError, KeyError, TypeError, ValueError):
            pass
    return float(_H0_NUMBERS[(dim, key)])


def clamp(cfg: HarnessConfig, fallback: HarnessConfig | None = None) -> HarnessConfig:
    """Range guards on the numbers H0 can apply (the reference does not clamp; this keeps a bad proposal from
    breaking the harness). A value that is not a number falls back to `fallback` (the base config), then to H0."""
    cfg.D3["temperature"] = min(1.0, max(0.0, _num(cfg, "D3", "temperature", fallback)))
    cfg.D3["max_tokens"] = int(min(4096, max(256, int(_num(cfg, "D3", "max_tokens", fallback)))))
    cfg.D5["history_keep"] = int(min(60, max(4, int(_num(cfg, "D5", "history_keep", fallback)))))
    return cfg


def base_config(ctl) -> HarnessConfig:
    """The H0 configuration in the reference schema. stabilize_config adds Harbor-only defaults and strategy text that
    H0's loop does not have, so strategies are cleared and the mapped numbers are reset to H0's own defaults."""
    cfg = ctl.stabilize_config(make_minimal_config())
    for d in DIMS:
        getattr(cfg, d)["strategy"] = ""
    cfg.D3.update(temperature=0.0, max_tokens=2048)  # H0 agent_loop defaults (client default, 2048 tokens)
    cfg.D5.update(history_keep=30)                   # H0 context_mgmt keep_turns default
    # The other keys describe H0 as it is, instead of Harbor defaults (bash tools, stop_rule 'immediate', ...) that the
    # diagnosis and distillation would otherwise blame for failures H0 cannot have. They are descriptive only.
    for d, kv in H0_DESCRIPTION.items():
        for k, v in kv.items():
            if k in getattr(cfg, d):
                getattr(cfg, d)[k] = v
    return cfg


H0_DESCRIPTION = {
    "D2": {"tool_access": "benchmark_tools", "tool_protocol": "native", "retrieval_mode": "none"},
    "D4": {"workflow": "react_loop", "stop_rule": "env_done_or_accepted_finish_or_max_steps"},
    "D5": {"memory_policy": "sliding_window"},
    "D6": {"validator": "verifier_slot", "postprocess": "none"},
}


# ---------------------------------------------------------------- bundle <-> H0
SEED_AGENTS = dedent("""
    # MemoHarness Overlay

    Bundle contract:
    - policy.json holds the authoritative D1-D6 summary; playbook.md holds stable execution heuristics and memory.md
      the rolling distilled notes.
    - No harness-specific rules yet: the current harness is the seed agent.
""").strip() + "\n"


def bundle_text(root: Path, cfg: HarnessConfig | None = None, patterns=None) -> str:
    """The bundle as the agent sees it (system prompt). With `cfg` (test-time adaptation), policy.json and playbook.md
    are rendered from the adapted config, as the reference's _apply_eval_config -> refresh_codex_bundle_support_docs
    does; the files on disk are not touched (episodes run in parallel)."""
    p = RB.resolve_codex_bundle_paths(root)
    agents = p.agents_path.read_text(encoding="utf-8") if p.agents_path.exists() else ""
    if cfg is None:
        policy = p.policy_path.read_text(encoding="utf-8") if p.policy_path.exists() else "{}"
        playbook = p.playbook_path.read_text(encoding="utf-8") if p.playbook_path.exists() else ""
        memory = p.memory_path.read_text(encoding="utf-8") if p.memory_path.exists() else ""
    else:
        pats = list(patterns or [])[-5:]
        policy = json.dumps(RB._policy_payload(cfg, distilled_patterns=pats), indent=1)
        playbook = RB._render_playbook_content(cfg, pats)
        memory = RB._render_memory_content(pats)
    return ("# Harness bundle (MemoHarness)\nThe files below are your harness policy, in the order to read them.\n\n"
            f"## ./AGENTS.override.md\n{agents.strip()}\n\n## ./policy.json\n{policy.strip()}\n\n"
            f"## ./.memoharness/playbook.md\n{playbook.strip()}\n\n## ./.memoharness/memory.md\n{memory.strip()}\n")


def to_bundle(root: Path | None, cfg: HarnessConfig, patterns=None, adapted: bool = False) -> dict:
    """H0 slot configs for a bundle (None: H0 itself, no bundle text)."""
    c = clamp(cfg.clone())
    extra = "" if root is None else bundle_text(root, c if adapted else None, patterns)
    return {
        "context_mgmt": {"name": "default", "config": {"keep_turns": int(c.D5["history_keep"]), "extra_system": extra}},
        "agent_loop": {"name": "default", "config": {"temperature": float(c.D3["temperature"]),
                                                     "max_tokens": int(c.D3["max_tokens"])}},
    }


class BundleInvalid(ValueError):
    pass


class BundleController(CodexBundleController):
    """The reference CodexBundleController with the Codex CLI replaced by one call to our model. The reference controller
    edits the bundle files in place with shell tools; ours gets them inline and returns the files it rewrites as
    `### FILE:` blocks, which are written into the bundle before the reference loader reads it back. The publish gate
    the reference asks Codex to run (policy.json valid, D1-D6 present, AGENTS file present, bundle budget) is checked
    by the caller and a failure goes through the reference retry prompt."""

    BUNDLE_FILES = ("AGENTS.override.md", "policy.json", ".memoharness/playbook.md", ".memoharness/memory.md")

    def __init__(self, *, bundle_root: Path, client, bench: str, workspace: Path):
        super().__init__(bundle_root=bundle_root, workspace_root=workspace, dataset=bench,
                         args=["exec", "--dangerously-bypass-approvals-and-sandbox", "-"], use_stdin=True)
        self._client, self._bench = client, bench
        self.calls: list[dict] = []
        self.budget_error: BaseException | None = None  # the reference retry loop swallows exceptions; this one must stop the run

    # -- transport
    def _run_controller_command(self, prompt: str) -> str:
        adapt = "adapting a MemoHarness configuration for one evaluation case" in prompt
        tag = f"b3:{'adapt' if adapt else 'controller'}:{self._bench}"
        try:
            r = self._client.chat([{"role": "user", "content": prompt}], tag=tag, max_tokens=2048 if adapt else 8000,
                                  fallback_no_reasoning=True)
        except Exception as e:
            if _budget_error(e) is not None:
                self.budget_error = _budget_error(e)
            raise
        if not adapt:
            files = {k: v for k, v in reply_files(r).items() if k in self.BUNDLE_FILES}
            for rel, body in files.items():
                path = self.bundle_root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(body, encoding="utf-8")
            self.calls.append({"written": sorted(files), "chars": len(r.content or "")})
        return r.content or ""

    def _load_live_harness_state(self, fallback: HarnessConfig) -> tuple[str, HarnessConfig]:
        problems = publish_gate(self.bundle_root)
        if problems:
            raise BundleInvalid("publish gate failed: " + "; ".join(problems))
        return super()._load_live_harness_state(fallback)

    # -- prompt sections that describe the CLI workspace; replaced because this controller has no tools
    def _project_brief_doc(self) -> str:
        return dedent(f"""
            ## Project Brief
            MemoHarness is optimizing a harness bundle for a ReAct tool-calling agent on {self._bench} instead of a
            free-form Python harness. The agent loop is fixed; this bundle controls the iterated MemoHarness policy:
            - AGENTS.override.md: primary task-scaffolding and execution rules
            - .memoharness/playbook.md: stable repo-level playbook
            - .memoharness/memory.md: rolling distilled memory
            - policy.json: structured D1-D6 summary
            All four files are inserted into the agent's system prompt. Of the D1-D6 values only D3.temperature
            (0-1), D3.max_tokens (256-4096) and D5.history_keep (4-60 recent turns kept in context) change runtime
            settings; every other key and every strategy text acts only through the prompt.
        """).strip()

    def _controller_command_scope_doc(self) -> str:
        return dedent("""
            ## No Tools In This Setup
            You have no shell or file tools: the current bundle files are shown in full under Current Live State.
            Reply with the COMPLETE new content of every bundle file you change, one block each, e.g.
            ### FILE: AGENTS.override.md
            ```markdown
            ...
            ```
            ### FILE: policy.json
            ```json
            {"config": {"D1": {...}, ..., "D6": {...}}}
            ```
            Files you do not emit stay as they are.
        """).strip()

    def _bundle_inspection_doc(self, iteration: int) -> str:
        del iteration
        return "## Inspect First\nStart from the current bundle files under Current Live State below."

    def _targeted_supporting_evidence_doc(self) -> str:
        return dedent("""
            ## Evidence Strategy
            Start from the current bundle files and the summarized iteration evidence below; no other logs are
            available.
        """).strip()

    def _on_disk_state_doc(self) -> str:
        return ("## Current Live State\nThe current bundle files (source of truth for this edit):\n\n"
                + RB.render_codex_bundle_preview(self.bundle_root))

    def _direct_edit_finish_doc(self) -> str:
        return dedent("""
            ## Required Finish State
            The caller runs this publish gate on the files you leave behind:
            - `policy.json` is valid JSON with a top-level `config` object holding D1-D6 entries
            - AGENTS.override.md exists and is not empty
            - AGENTS.override.md plus policy.json stay within the bundle budget
            - keep the bundle concise, specific, and grounded in the current iteration evidence
            If a check fails you will be asked to repair the files.

            Print a short final status after the file blocks.
        """).strip()


def publish_gate(root: Path) -> list[str]:
    """The checks of the reference's Required Finish State, run by the caller (the reference has Codex run them)."""
    from baselines.vendor.memoharness.controllers.codex_bundle import _BUNDLE_CHAR_BUDGET
    p = RB.resolve_codex_bundle_paths(root)
    out = []
    agents = p.agents_path.read_text(encoding="utf-8") if p.agents_path.exists() else ""
    policy = p.policy_path.read_text(encoding="utf-8") if p.policy_path.exists() else ""
    if not agents.strip():
        out.append("AGENTS.override.md is missing or empty")
    try:
        raw = json.loads(policy)
        cfg = raw.get("config") if isinstance(raw, dict) else None
        if not isinstance(cfg, dict) or any(not isinstance(cfg.get(d), dict) for d in DIMS):
            out.append("policy.json has no top-level `config` object with D1-D6 entries")
    except json.JSONDecodeError as e:
        out.append(f"policy.json is not valid JSON ({e})")
    if len(agents) + len(policy) > _BUNDLE_CHAR_BUDGET:
        out.append(f"AGENTS.override.md + policy.json = {len(agents) + len(policy)} chars > budget {_BUNDLE_CHAR_BUDGET}")
    return out


def _diagnoses(diag, case_ids: list[str]) -> dict[str, dict]:
    """case_id -> {primary_dim, analysis}. Accepts {case_id: {...}}, {"cases"/"diagnoses": ...},
    [{"case_id": ..., ...}], and keys that quote the id with a prefix ('case X') or a truncated id."""
    if isinstance(diag, dict):
        for k in ("cases", "diagnoses", "results"):
            if isinstance(diag.get(k), (dict, list)):
                diag = diag[k]
                break
    if isinstance(diag, list):
        diag = {str(d.get("case_id") or d.get("case") or d.get("id")): d for d in diag if isinstance(d, dict)}
    if not isinstance(diag, dict):
        return {}
    out = {}
    for key, d in diag.items():
        if not isinstance(d, dict):
            continue
        k = re.sub(r"^\s*case[\s:_-]*", "", str(key), flags=re.I).strip()
        hit = [c for c in case_ids if c == k] or [c for c in case_ids if k and (c.startswith(k) or k.startswith(c))]
        if len(hit) == 1:
            out[hit[0]] = d
    return out


# ---------------------------------------------------------------- entries
def case_features(instr: str, bench: str) -> CaseFeatures:
    return CaseFeatures(input_length=len(instr), complexity_estimate=min(1.0, len(instr) / 2000), domain=bench,
                        requires_external_knowledge=bench == "browsecomp_plus", safety_sensitivity=0.0,
                        ambiguity_score=0.0, instruction=instr, cluster_id=bench)


def _instr_of(rec: dict) -> str:
    if rec.get("error") or not rec.get("trajectory_path"):
        return rec["task_id"]
    return instruction_of(rec)[:800]


def to_entry(rec: dict, iteration: int, cfg: HarnessConfig, prev: HarnessConfig, bench: str,
             diag: dict | None = None) -> PerCaseEntry:
    ok = bool(rec["success"])
    d = diag or {}
    dim = norm_dim(d.get("primary_dim")) or ("D1" if ok else "D4")  # reference rule for the default dimension
    return PerCaseEntry(
        case_id=rec["task_id"], iteration=iteration, case_features=case_features(_instr_of(rec), bench),
        config=cfg.clone(), delta_from_prev=cfg.delta_from(prev),
        trajectory=Trajectory(num_llm_calls=rec["steps"], total_tokens=rec["tokens"], latency_ms=0, tools_invoked=[],
                              intermediate_outputs=[], final_output=""),
        primary_reward=1.0 if ok else 0.0, cost_actual=float(rec.get("cost") or 0.0),
        diagnosis=Diagnosis(success=ok, analysis=str(d.get("analysis", ""))[:300],
                            diagnostic_signal=DiagnosticSignal(primary_dim=dim)))


DIAGNOSE = """You diagnose why an LLM agent harness failed on benchmark cases. Harness dimensions:
{dims}

For EACH failed case below, name the single harness dimension most responsible (primary_dim) and give a one-sentence
general analysis (no task-specific answers). Reply with ONLY a JSON object {{"<case_id>": {{"primary_dim": "D1".."D6",
"analysis": "..."}}, ...}}.

{cases}"""


def diagnose(client, bench: str, failed: list[tuple[PerCaseEntry, dict]], batch: int = 10) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for i in range(0, len(failed), batch):
        part = failed[i: i + batch]
        cases = "\n\n".join(f"### case {e.case_id}\n{C.summarize_trajectory(r['trajectory_path'], max_events=10)}"
                            for e, r in part)
        rr = client.chat([{"role": "user", "content": DIAGNOSE.format(dims=LC._DIMENSIONS_DOC, cases=cases)}],
                         tag=f"b3:diagnose:{bench}", max_tokens=1200, fallback_no_reasoning=True)
        out.update(_diagnoses(extract_json(rr.content), [e.case_id for e, _ in part]))
    return out


def ingest(bank: BM25ExperienceBank, recs: list[dict], iteration: int, cfg: HarnessConfig, prev: HarnessConfig,
           bench: str, client, distiller: LLMDistiller, log: dict, live: Path | None = None) -> None:
    """Reference _update_bank + distillation triggers: diagnose the failed episodes, add every episode to the bank,
    distill when a case reaches the consecutive-failure threshold (add_entry returns True) or on
    should_distill(EVERY_N_ENTRIES). Patterns are appended (distill_global_patterns_llm) and, as in the reference's
    _distill, the live bundle's memory.md / playbook.md / policy.json are re-rendered from them. Infra-error episodes
    are external blockers and never enter the bank (_filter_learning_results)."""
    recs = [rec for rec in recs if not rec.get("error")]
    failed = [rec for rec in recs if not rec["success"]]
    diag = diagnose(client, bench, [(to_entry(r, iteration, cfg, prev, bench), r) for r in failed]) if failed else {}

    def distill():
        new = bank.distill_global_patterns_llm(distiller, iteration)
        bank.mark_distill_done()
        log.setdefault("distill", []).append({"iteration": iteration, "patterns": [p.description[:120] for p in new]})
        if live is not None:
            RB.refresh_codex_bundle_support_docs(live, cfg, distilled_patterns=bank.global_patterns,
                                                 updated_iteration=iteration)

    for rec in recs:
        if bank.add_entry(to_entry(rec, iteration, cfg, prev, bench, diag.get(rec["task_id"]))):
            distill()
    if bank.should_distill(EVERY_N_ENTRIES):
        distill()


def _budget_error(exc: BaseException) -> BaseException | None:
    """The BudgetExceeded in an exception chain (call_with_retries may wrap it in a RuntimeError), else None."""
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        if type(cur).__name__ == "BudgetExceeded":
            return cur
        seen.add(id(cur))
        cur = cur.__cause__ or cur.__context__
    return None


def adapt_composer(ctl: BundleController, bank: BM25ExperienceBank, root: Path | None, base_cfg: HarnessConfig,
                   bench: str, log: list, adapt: bool):
    """Test-time Phase B: the reference adapt_for_case (config-only, similar-case evidence) on the selected harness,
    then the bundle rendered with the adapted config."""
    def composer(task, reg, base_bundle):
        if not adapt:
            return to_bundle(root, base_cfg)
        case = BenchmarkCase(case_id=task.task_id, prompt=task.instruction, expected_output="",
                             features=case_features(task.instruction, bench))
        try:
            cfg = clamp(ctl.adapt_for_case(bank, case, base_cfg).config, fallback=base_cfg)
        except Exception as e:
            budget = _budget_error(e)
            if budget is not None:
                raise budget  # budget exhaustion stops the whole run (benchmarks/common.run_with_env)
            log.append({"task": task.task_id, "error": f"{type(e).__name__}: {e}"[:300], "delta": {}})
            return to_bundle(root, base_cfg)  # reference: adaptation failed -> base harness config
        log.append({"task": task.task_id, "delta": cfg.delta_from(base_cfg)})
        return to_bundle(root, cfg, bank.global_patterns, adapted=True)
    return composer


def canary_metrics(recs: list[dict]) -> dict[str, float]:
    """Reference _result_metrics, per task: a task whose rolls all hit an infra error is an external blocker; the
    others score the mean reward of their non-error rolls (H0 has K rolls per task, the canary one) and count as
    succeeded at reward >= 0.5. Rates are over the learnable (non-blocker) tasks."""
    by: dict[str, list[dict]] = {}
    for r in recs:
        by.setdefault(r["task_id"], []).append(r)
    rewards = []
    for rolls in by.values():
        ok = [r for r in rolls if not r.get("error")]
        if ok:
            rewards.append(sum(1.0 for r in ok if r["success"]) / len(ok))
    n = len(rewards)
    return {"cases_total": float(len(by)), "cases_learning": float(n),
            "cases_succeeded": float(sum(1 for x in rewards if x >= 0.5)),
            "mean_reward": sum(rewards) / max(n, 1),
            "success_rate": sum(1 for x in rewards if x >= 0.5) / max(n, 1),
            "blockers": float(len(by) - n)}


def canary_check(metrics: dict[str, float], baseline: dict[str, float]) -> tuple[bool, str]:
    """Reference _evaluate_candidate_with_canary: the three rejection rules in the reference order."""
    if metrics["cases_learning"] <= 0:
        return False, "no learnable canary cases (all external blockers)"
    reward_delta = metrics["mean_reward"] - baseline["mean_reward"]
    blocker_increase = metrics["blockers"] - baseline["blockers"]
    success_delta = metrics["success_rate"] - baseline["success_rate"]
    if reward_delta < CANARY_MIN_REWARD_DELTA:
        return False, f"reward delta {reward_delta:.3f} < threshold {CANARY_MIN_REWARD_DELTA:.3f}"
    if blocker_increase > CANARY_MAX_BLOCKER_INCREASE:
        return False, f"blocker increase {blocker_increase:.0f} > threshold {CANARY_MAX_BLOCKER_INCREASE}"
    if success_delta < CANARY_MAX_SUCCESS_DROP and reward_delta <= 0.0:
        return False, f"success rate dropped too much ({success_delta:.3f}) without reward gain"
    return True, "accepted by canary gate"


def materialize(dest: Path, live: Path | None, cfg: HarnessConfig, round_i: int) -> Path:
    """A harness root for C.evaluate: H0's files plus bundle.json carrying the bundle (a copy of the live bundle,
    so later edits of the live bundle do not change it). live=None: H0 itself with the config's numbers."""
    C.new_candidate(dest, C.H0_ROOT, {"method": "b3", "round": round_i})
    root = None
    if live is not None:
        shutil.copytree(live, dest / "bundle")
        root = dest / "bundle"
    (dest / "bundle.json").write_text(json.dumps(to_bundle(root, cfg), indent=1))
    return dest


def iteration_score(recs: list[dict], ids: list[str]) -> tuple[float, float]:
    """Reference iter_rewards / iter_total_tokens on the train-run tasks: mean per-task reward over the learnable
    tasks (H0's K rolls averaged per task) and mean tokens per episode (the tie-breaker)."""
    sub = [r for r in recs if r["task_id"] in set(ids)]
    m = canary_metrics(sub)
    ok = [r for r in sub if not r.get("error")]
    return m["mean_reward"], sum(r["tokens"] for r in ok) / max(1, len(ok))


# ---------------------------------------------------------------- run
def run(bench: str, shared: dict, client, cfg=C.SMOKE, tag: str = "smoke", adapt: bool = TEST_TIME_CASE_ADAPTATION) -> dict:
    ws = C.RUNS / "b3" / bench
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    out = C.OUT / f"b3_{bench}.jsonl"
    tasks = shared["tasks"]
    live = ws / "bundle_live"
    ctl = BundleController(bundle_root=live, client=client, bench=bench, workspace=ws)
    distiller = LLMDistiller(client=ChatShim(client, f"b3:distill:{bench}"), model=MODEL,
                             min_consecutive_failures=MIN_CONSECUTIVE_FAILURES, max_patterns=MAX_PATTERNS,
                             api_config=API)
    bank = BM25ExperienceBank()
    log = {"method": "b3", "bench": bench, "controller": "codex-bundle", "test_time_case_adaptation": adapt,
           "rounds": []}
    base = base_config(ctl)
    RB.write_codex_policy(live, base)
    RB.resolve_codex_bundle_paths(live).agents_path.write_text(SEED_AGENTS, encoding="utf-8")
    train_ids = tasks["train"][1][: cfg["n_val"]]   # reference: the train set every iteration (budget: n_val tasks)
    canary_ids = train_ids[: cfg["n_check"]]        # reference: the first controller_canary_task_count train tasks
    # iteration 0 = the shared H0 rollouts, ALL K rolls per train task (the same evidence every method gets)
    ingest(bank, shared["h0_train"], 0, base, base, bench, client, distiller, log, live)
    cur = {"name": "h0", "bundle": False, "cfg": base, "recs": list(shared["h0_train"])}
    iters = {0: {"harness": "h0", "root": None, "cfg": base, "score": iteration_score(shared["h0_train"], train_ids)}}
    for ri in range(1, cfg["rounds"] + 1):
        C.budget_check(f"b3[{bench}] round {ri}")
        rd = {"round": ri}
        snap = RB.snapshot_codex_bundle(live)
        try:
            _, new_cfg = ctl.decide_next_harness(bank, RB.render_codex_bundle_preview(live), cur["cfg"], ri - 1,
                                                 MIN_CONSECUTIVE_FAILURES)
            new_cfg = clamp(new_cfg, fallback=cur["cfg"])
        except Exception as e:
            if ctl.budget_error is not None or _budget_error(e) is not None:
                raise ctl.budget_error or _budget_error(e)
            RB.restore_codex_bundle(snap)
            new_cfg = None
            rd.update(result="controller failed", error=f"{type(e).__name__}: {e}"[:400])
        if new_cfg is not None:
            cand = materialize(ws / "candidates" / f"r{ri}", live, new_cfg, ri)
            rd["delta"] = new_cfg.delta_from(cur["cfg"])
            rd["controller_calls"] = ctl.calls[-CONTROLLER_MAX_RETRIES:]
            can = C.evaluate(bench, tasks["train"][0], canary_ids, cand, client, f"b3_{bench}_r{ri}_canary", out,
                             workers=cfg["workers"], label={"method": "b3", "phase": "canary", "round": ri})
            ref = [r for r in cur["recs"] if r["task_id"] in set(canary_ids)]  # current harness, same tasks
            can_m, ref_m = canary_metrics(can), canary_metrics(ref)
            accepted, reason = canary_check(can_m, ref_m)
            rd["canary"] = {"metrics": can_m, "baseline": ref_m, "reason": reason,
                            "errors": [r["error"] for r in can if r["error"]]}
            if accepted:
                rd["result"] = "passed canary"
                cur = {"name": f"r{ri}", "bundle": True, "cfg": new_cfg, "recs": []}
            else:
                rd["result"] = "rejected by canary"
                RB.restore_codex_bundle(snap)  # reference: the live bundle goes back to the previous harness
        # reference: every iteration runs the current harness on the train tasks and learns from the results. The
        # current harness is the live bundle (including memory refreshed by distillation), or H0 while no bundle passed.
        run_dir = materialize(ws / "iterations" / f"it{ri}", live if cur["bundle"] else None, cur["cfg"], ri)
        tr = C.evaluate(bench, tasks["train"][0], train_ids, run_dir, client, f"b3_{bench}_r{ri}_train", out,
                        workers=cfg["workers"], label={"method": "b3", "phase": "train", "round": ri,
                                                       "harness": cur["name"]})
        cur["recs"] = tr
        ingest(bank, tr, ri, cur["cfg"], iters[max(iters)]["cfg"], bench, client, distiller, log, live)
        iters[ri] = {"harness": cur["name"], "root": (run_dir / "bundle") if cur["bundle"] else None, "cfg": cur["cfg"],
                     "score": iteration_score(tr, train_ids)}
        rd.update(harness=cur["name"], train=iters[ri]["score"][0])
        log["rounds"].append(rd)
    # ---- correctness-first selection over the iterations (tokens break ties), then freeze the bank
    best = 0
    for it, v in iters.items():
        if C.better(v["score"][0], v["score"][1], iters[best]["score"][0], iters[best]["score"][1]):
            best = it
    sel = iters[best]
    log["iterations"] = {it: {"harness": v["harness"], "train_reward": v["score"][0], "tokens": v["score"][1]}
                         for it, v in iters.items()}
    log["final"] = {"global": sel["harness"], "iteration": best, "train": sel["score"][0], "config": sel["cfg"].as_dict()}
    bank.frozen = True
    n_frozen = len(bank.entries)
    bank.save(ws / "bank.pkl")  # pickle + bank.json (save writes the JSON next to it with suffix .json)
    (ws / "final.json").write_text(json.dumps(log["final"], indent=1, default=str))
    C.budget_check(f"b3[{bench}] test")
    alog: list = []
    test = C.evaluate(bench, tasks["test"][0], tasks["test"][1], C.H0_ROOT, client, f"b3_{bench}_test", out,
                      composer=adapt_composer(ctl, bank, sel["root"], sel["cfg"], bench, alog, adapt),
                      workers=cfg["workers"], label={"method": "b3", "phase": "test", "harness": sel["harness"]})
    log["test"] = {"success": C.score(test), "n": len(test), "adaptations": alog}
    assert bank.frozen and len(bank.entries) == n_frozen  # no write-back during test
    (ws / "log.json").write_text(json.dumps(log, indent=1, default=str))
    return {"log": log, "test": test}
