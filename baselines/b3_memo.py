"""B3: MemoHarness experience bank + global config search + per-case test-time adaptation, on H0.

Reuses MemoHarness's own code, vendored under baselines/vendor/memoharness/ (the source repo ships no LICENSE file;
code copied with the permission of its author, see docs/baseline_fidelity.md):
  - core/models.py            PerCaseEntry, CaseFeatures, CaseStats, HarnessConfig, Diagnosis, Trajectory, ...
  - bank/experience.py        ExperienceBank: add_entry, should_distill, mark_distill_done, retrieve_similar_cases_for_case
                              (only the embedder is replaced, by BM25ExperienceBank below)
  - llm/distiller.py          LLMDistiller: distillation prompt, pattern parsing (transport replaced by ChatShim)
  - controllers/llm_controller.py  LLMController: adapt_for_case, bank/signal summaries, stabilize_config,
                              _build_harness_config, config-only prompt _CONFIG_ONLY_DOC (transport replaced by ChatShim).
                              Its code-generation methods are NOT used: the controller changes only the D1..D6 config.
  - config/runtime.py         canary thresholds (HarnessSettings defaults)

Protocol (shared with B1/B2): H0 seed and splits, the same evidence (all K=3 train rolls), the canary on cfg["n_check"]
train tasks, the common C.better rule, freeze before test, no write-back during test.

D1..D6 -> H0 mapping (only the knobs that H0 can express are applied; see docs/baseline_fidelity.md, B3 table):
  D1..D6 "strategy"  -> context_mgmt.extra_system (strategy text, appended to the system prompt)
  D3 temperature     -> agent_loop.temperature
  D3 max_tokens      -> agent_loop.max_tokens
  D5 history_keep    -> context_mgmt.keep_turns
  other reference keys (D2 tool_*, D3 top_p/candidate_count, D4 workflow/stop_rule, D5 memory_policy, D6 *) are kept in
  the config for the controller's prompt but have no H0 counterpart, so they are not applied.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from types import SimpleNamespace

from baselines import common as C
from baselines.proposer_io import extract_json
from baselines.vendor.memoharness.bank.experience import ExperienceBank
from baselines.vendor.memoharness.config.runtime import ApiModelConfig, HarnessSettings
from baselines.vendor.memoharness.controllers import llm_controller as LC
from baselines.vendor.memoharness.controllers.llm_controller import LLMController
from baselines.vendor.memoharness.core.models import (BenchmarkCase, CaseFeatures, Diagnosis, DiagnosticSignal,
                                                      HarnessConfig, PerCaseEntry, Trajectory, make_minimal_config)
from baselines.vendor.memoharness.llm.distiller import LLMDistiller
from benchmarks.common import instruction_of

MODEL = "inclusionai/ling-3.0-flash"
EVERY_N_ENTRIES = 5             # reference should_distill(every_n_entries=5)
MIN_CONSECUTIVE_FAILURES = 3    # reference default (ExperienceBank / LLMDistiller)
MAX_PATTERNS = 3                # reference LLMDistiller max_patterns
TEST_TIME_CASE_ADAPTATION = True  # per-case adapt_for_case at val/test; False = the searched global config only
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


def to_bundle(cfg: HarnessConfig) -> dict:
    """Map D1..D6 onto H0 slot configs (see the module docstring for the table)."""
    strategies = [f"- {getattr(cfg, d).get('strategy')}" for d in DIMS if getattr(cfg, d).get("strategy")]
    extra = "\n".join(strategies)
    return {
        "context_mgmt": {"name": "default", "config": {"keep_turns": int(cfg.D5["history_keep"]),
                                                       "extra_system": ("Harness strategy:\n" + extra) if extra else ""}},
        "agent_loop": {"name": "default", "config": {"temperature": float(cfg.D3["temperature"]),
                                                     "max_tokens": int(cfg.D3["max_tokens"])}},
    }


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


def base_config(ctl: "ConfigController") -> HarnessConfig:
    """The H0 configuration in the reference schema. stabilize_config adds Harbor-only defaults and strategy text that
    H0's loop does not have, so strategies are cleared and the mapped numbers are reset to H0's own defaults."""
    cfg = ctl.stabilize_config(make_minimal_config())
    for d in DIMS:
        getattr(cfg, d)["strategy"] = ""
    cfg.D3.update(temperature=0.0, max_tokens=2048)  # H0 agent_loop defaults (client default, 2048 tokens)
    cfg.D5.update(history_keep=30)                   # H0 context_mgmt keep_turns default
    return cfg


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


def diagnose(client, bench: str, failed: list[tuple[PerCaseEntry, dict]]) -> dict[str, dict]:
    cases = "\n\n".join(f"### case {e.case_id}\n{C.summarize_trajectory(r['trajectory_path'], max_events=10)}"
                        for e, r in failed)
    rr = client.chat([{"role": "user", "content": DIAGNOSE.format(dims=LC._DIMENSIONS_DOC, cases=cases)}],
                     tag=f"b3:diagnose:{bench}", max_tokens=1200, fallback_no_reasoning=True)
    return _diagnoses(extract_json(rr.content), [e.case_id for e, _ in failed])


def ingest(bank: BM25ExperienceBank, recs: list[dict], iteration: int, cfg: HarnessConfig, prev: HarnessConfig,
           bench: str, client, distiller: LLMDistiller, log: dict) -> None:
    """Diagnose the failed episodes, add them to the bank, and distill when the reference trigger fires: a case reached
    the consecutive-failure threshold (add_entry returns True) or should_distill(EVERY_N_ENTRIES).
    Infra-error episodes are external blockers and never enter the bank (reference _filter_learning_results)."""
    recs = [rec for rec in recs if not rec.get("error")]
    failed = [rec for rec in recs if not rec["success"]]
    diag = {}
    if failed:
        pairs = [(to_entry(r, iteration, cfg, prev, bench), r) for r in failed]
        diag = diagnose(client, bench, pairs)
    trigger = False
    for rec in recs:
        trigger = bank.add_entry(to_entry(rec, iteration, cfg, prev, bench, diag.get(rec["task_id"]))) or trigger
    if trigger or bank.should_distill(EVERY_N_ENTRIES):
        bank.global_patterns = distiller.distill(bank, iteration)[:MAX_PATTERNS]
        bank.mark_distill_done()
        log.setdefault("distill", []).append({"iteration": iteration, "patterns": [p.description[:120] for p in bank.global_patterns]})


# ---------------------------------------------------------------- controller and memory slot
class ConfigController(LLMController):
    """Global search over D1..D6 only. Uses the reference config-only prompt (_CONFIG_ONLY_DOC) and parser; the
    code-generation path (generate_initial_harness, decide_next_harness) is not used."""

    def propose(self, bank: BM25ExperienceBank, current: HarnessConfig, iteration: int) -> tuple[HarnessConfig, str]:
        base = self.stabilize_config(current)
        prompt = ("You are optimizing the configuration of an LLM agent harness.\n"
                  f"Current iteration: {iteration}\n\n"
                  + LC._DIMENSIONS_DOC + LC._DIMENSION_ACTION_PLAYBOOK_DOC
                  + "\n## Experience Bank Summary\n"
                  + self._build_bank_summary(bank, iteration, MIN_CONSECUTIVE_FAILURES)
                  + "\n\n## Change-Outcome Signals\n"
                  + self._build_change_outcome_signals(bank, iteration)
                  + "\n\n## Current Config\n" + json.dumps(base.as_dict(), indent=1, default=str)
                  + "\n\nChoose 1-3 highest-priority interventions supported by the evidence. Strategy texts must be "
                  "general (never mention specific tasks, ids or answers).\n"
                  + LC._CONFIG_ONLY_DOC)
        updates = self._call_llm_for_config(prompt)
        nxt = clamp(self.stabilize_config(self._build_harness_config(updates, base)), fallback=base)
        rationale = str(updates.get("rationale", ""))[:300] if isinstance(updates, dict) else ""
        return nxt, rationale


class ExperienceMemory:
    """Memory-slot object for B3: recalls the distilled global patterns and similar failed cases from a FROZEN bank."""

    def __init__(self, bank: BM25ExperienceBank, bench: str, max_chars: int = 1500):
        self.bank, self.bench, self.max_chars = bank, bench, max_chars

    def recall(self, task):
        lines = [f"- [{p.primary_dim}] {p.description} -> {p.effect}" for p in self.bank.global_patterns]
        case = BenchmarkCase(case_id=task.task_id, prompt=task.instruction, expected_output="",
                             features=case_features(task.instruction, self.bench))
        sim = self.bank.retrieve_similar_cases_for_case(case, top_k_success=2, top_k_failure=2)
        lines += [f"- similar past case failed ({e.diagnosis.diagnostic_signal.primary_dim}): {e.diagnosis.analysis[:160]}"
                  for e in sim.failed if e.diagnosis.analysis]
        return "\n".join(lines)[: self.max_chars]

    def update(self, task, outcome, success, trajectory):
        return None  # frozen during val/test; bank updates happen in the training loop


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


def adapt_composer(ctl: ConfigController, bank: BM25ExperienceBank, base_cfg: HarnessConfig, bench: str, log: list,
                   adapt: bool):
    def composer(task, reg, base_bundle):
        if not adapt:
            return to_bundle(base_cfg)
        case = BenchmarkCase(case_id=task.task_id, prompt=task.instruction, expected_output="",
                             features=case_features(task.instruction, bench))
        try:
            # reference: one call, dimensions changed only with evidence; clamped like the global proposals
            cfg = clamp(ctl.adapt_for_case(bank, case, base_cfg).config, fallback=base_cfg)
        except Exception as e:
            budget = _budget_error(e)
            if budget is not None:
                raise budget  # budget exhaustion stops the whole run (benchmarks/common.run_with_env)
            log.append({"task": task.task_id, "error": f"{type(e).__name__}: {e}"[:300], "delta": {}})
            return to_bundle(base_cfg)  # adaptation failed: the searched global config, unadapted
        log.append({"task": task.task_id, "delta": cfg.delta_from(base_cfg)})
        return to_bundle(cfg)
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


# ---------------------------------------------------------------- run
def run(bench: str, shared: dict, client, cfg=C.SMOKE, tag: str = "smoke", adapt: bool = TEST_TIME_CASE_ADAPTATION) -> dict:
    ws = C.RUNS / "b3" / bench
    ws.mkdir(parents=True, exist_ok=True)
    out = C.OUT / f"b3_{bench}.jsonl"
    tasks = shared["tasks"]
    ctl = ConfigController(client=ChatShim(client, f"b3:controller:{bench}"), model=MODEL, api_config=API)
    distiller = LLMDistiller(client=ChatShim(client, f"b3:distill:{bench}"), model=MODEL,
                             min_consecutive_failures=MIN_CONSECUTIVE_FAILURES, max_patterns=MAX_PATTERNS,
                             api_config=API)
    bank = BM25ExperienceBank()
    log = {"method": "b3", "bench": bench, "test_time_case_adaptation": adapt, "rounds": []}
    base = base_config(ctl)
    # iteration 0 = the shared H0 rollouts, ALL K rolls per train task (the same evidence every method gets)
    ingest(bank, shared["h0_train"], 0, base, base, bench, client, distiller, log)
    inc_cfg, candidates = base, []
    for ri in range(1, cfg["rounds"] + 1):
        C.budget_check(f"b3[{bench}] round {ri}")
        rd = {"round": ri}
        new_cfg, rationale = ctl.propose(bank, inc_cfg, ri)
        rd.update(rationale=rationale, delta=new_cfg.delta_from(inc_cfg))
        cand = ws / "candidates" / f"r{ri}"
        C.new_candidate(cand, C.H0_ROOT, {"method": "b3", "round": ri, "config": new_cfg.as_dict()})
        (cand / "bundle.json").write_text(json.dumps(to_bundle(new_cfg), indent=1))
        (cand / "harness_config.json").write_text(json.dumps(new_cfg.as_dict(), indent=1, default=str))
        # canary: cfg["n_check"] train tasks (reference uses 6; the shared protocol uses n_check)
        canary_ids = tasks["train"][1][:cfg["n_check"]]
        can = C.evaluate(bench, tasks["train"][0], canary_ids, cand, client, f"b3_{bench}_r{ri}_canary", out,
                         memory=ExperienceMemory(bank, bench), workers=cfg["workers"],
                         label={"method": "b3", "phase": "canary", "round": ri})
        ref = [r for r in shared["h0_train"] if r["task_id"] in set(canary_ids)]  # H0, all K rolls on the same tasks
        can_m, ref_m = canary_metrics(can), canary_metrics(ref)
        accepted, reason = canary_check(can_m, ref_m)
        rd["canary"] = {"metrics": can_m, "baseline": ref_m, "reason": reason,
                        "errors": [r["error"] for r in can if r["error"]]}
        # canary rollouts are NOT ingested: the reference bank only receives full-train results
        if not accepted:
            rd["result"] = "rejected by canary"
            log["rounds"].append(rd)
            continue
        rd["result"] = "passed canary"
        rd["candidate_cfg"] = new_cfg.as_dict()
        candidates.append((f"r{ri}", new_cfg))
        inc_cfg = new_cfg  # the next proposal starts from the last configuration that passed the canary
        log["rounds"].append(rd)
    # ---- freeze the bank, then select the global config on val (per-case adaptation if enabled; correctness first)
    bank.frozen = True
    n_frozen = len(bank.entries)
    bank.save(ws / "bank.json")
    best = None
    for name, gcfg in [("h0", base)] + candidates:
        if name == "h0":
            v, tok = C.score(shared["h0_val"]), sum(r["tokens"] for r in shared["h0_val"])  # shared H0 val (no adaptation)
        else:
            alog: list = []
            val = C.evaluate(bench, tasks["val"][0], tasks["val"][1], C.H0_ROOT, client, f"b3_{bench}_{name}_val", out,
                             composer=adapt_composer(ctl, bank, gcfg, bench, alog, adapt),
                             memory=ExperienceMemory(bank, bench), workers=cfg["workers"],
                             label={"method": "b3", "phase": "val", "candidate": name})
            v, tok = C.score(val), sum(r["tokens"] for r in val)
            log.setdefault("val", {})[name] = {"success": v, "tokens": tok, "adaptations": alog}
        if best is None or C.better(v, tok, best[1], best[2]):
            best = (name, v, tok, gcfg)
    log["final"] = {"global": best[0], "val": best[1], "config": best[3].as_dict()}
    (ws / "final.json").write_text(json.dumps(log["final"], indent=1, default=str))
    C.budget_check(f"b3[{bench}] test")
    alog = []
    test = C.evaluate(bench, tasks["test"][0], tasks["test"][1], C.H0_ROOT, client, f"b3_{bench}_test", out,
                      composer=adapt_composer(ctl, bank, best[3], bench, alog, adapt),
                      memory=ExperienceMemory(bank, bench), workers=cfg["workers"], label={"method": "b3", "phase": "test"})
    log["test"] = {"success": C.score(test), "n": len(test), "adaptations": alog}
    assert bank.frozen and len(bank.entries) == n_frozen  # no write-back during test
    (ws / "log.json").write_text(json.dumps(log, indent=1, default=str))
    return {"log": log, "test": test}
