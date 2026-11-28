"""B4 v7 with failure clusters (B4_CLUSTER=1).

Every failed training run of the current harness is read by an LLM, which finds the decisive step (the earliest one
after which the run could not succeed without a change of course), says what the agent did there, what visible in
the run showed it was a mistake and what was better, and files the run by that MISTAKE (not by its consequence,
such as stopping early) under an existing cluster or a new one (name, definition, and a signature a program could
check on the run). The registry is
cumulative across rounds, every cluster carries its count of failed runs and tasks, and nothing is filtered out:
`harness_fixable` is shown as the labeller's opinion, the proposer decides. The digest the labeller reads keeps the
arguments of the agent's actions (for code-writing agents the action IS its argument), which the short digests of
the run reviews cut.

A cluster is also a behaviour measure. A hypothesis may state `behaviour` = `mode:<cluster>` (direction down): on
each branch and on the saved run it forks, a blind judge (outcome hidden) answers whether the run shows that failure;
the paired sign test of behaviour_shift then applies as for a numeric feature. This covers failures that end-of-run
counts cannot express (what the agent did, not how often).

Determinism on resume: the labelling calls go through the method's replay cache (tags "b4:*", sequential). Judge
calls run in parallel, so they bypass that cache (tag "b4j:*") and use their own cache keyed by (run, cluster).
"""
from __future__ import annotations

import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from baselines.proposer_io import extract_json
from baselines import b4_branch as V

BATCH = 4            # failed runs per labelling call
MAX_CLUSTERS = 12    # above this, one consolidation call merges near-duplicates
JUDGE_WORKERS = 8

LABEL = """You keep a registry of FAILURE CLUSTERS of an AI agent. It decides which change of the agent's
scaffolding (its tools, what tool results show, its checks, its loop) is tried next. So a cluster names a MISTAKE
that recurs across tasks and that a program watching the run could notice when it happens.

Existing clusters (name: definition | signature [failed runs filed so far]):
{registry}

Failed runs (the grader marked each one as failed; steps are numbered; read what the agent actually did, including
the arguments and code of its actions and the results it got):
{runs}

Read each run like this:
1. step: the decisive step, the earliest one after which the run could no longer succeed unless the agent changed
   course. Every failed run ends with a wrong, partial or missing answer; that ending is NOT the mistake. Find
   what led to it.
2. did: what the agent did at that step, in terms of the tool interface: which tool, the form of its arguments
   (which arguments it set or left out, how it combined conditions, what it repeated or changed), never the
   task's entities or values.
3. evidence: what was visible in the run at that point that shows it was a mistake: the result the agent got and
   how it treated it (ignored it, misread it, never checked it, acted before having it).
4. better: the next action that would have been better, again in terms of the tool interface.
5. cluster: file the run by its MISTAKE (did + evidence), not by its consequence. Names such as "stopped too
   early", "gave up", "incomplete answer" describe how almost every failure ends and point to no change; use
   them only if the run really shows nothing earlier. Reuse an existing name when the mistake is the same; runs
   of this batch that share a new mistake get the same new name (snake_case, 2-4 short words, <= 40 chars).
   For a NEW name also give:
   - definition: one sentence on the mistake, general (no task entities)
   - signature: a condition a program could check on the run up to the decisive step, from the agent's actions
     and the tool results only (the outcome is unknown to it)
   - harness_fixable: false if the run shows no mistake of this kind that the scaffolding could notice (the model
     lacked knowledge or reasoned wrongly from complete information, the task is ambiguous, the environment
     failed), else true
Write every field in general terms: no task entities, names, values or ids.
Answer ONLY with JSON: {{"runs": [{{"i": 0, "step": 3, "did": "...", "evidence": "...", "better": "...",
"cluster": "...", "definition": "...", "signature": "...", "harness_fixable": true}}]}}"""

MERGE = """These are failure clusters of an AI agent, each with its definition and count of failed runs:
{registry}
Some may describe the same pattern. Merge duplicates so that at most {k} clusters remain; keep distinct patterns
apart. Answer ONLY with JSON: {{"merge": {{"<cluster merged away>": "<cluster it goes into>"}}}} ({{}} if none)."""

JUDGE = """You check whether a finished run of an AI agent makes one specific mistake. You are not told whether the
run succeeded, and the outcome does not matter: answer about the mistake itself, at the step where it happens.

Mistake `{name}`: {definition}
Signature (how it shows on a run): {signature}

Run (digest, steps numbered):
{digest}

Answer ONLY with JSON: {{"shows": true or false, "step": <first step where it happens, or null>,
"why": "<one short sentence>"}}"""


def digest(path: str, max_events: int = 30, head: int = 8, arg_chars: int = 500, obs_chars: int = 600,
           task_chars: int = 600) -> str:
    """The run as the agent lived it: task, its reasoning, each numbered action WITH its arguments, each result. The
    outcome is not shown. A long run keeps its first `head` events (where the course is often set) and its last
    ones."""
    ev = V.load_events(path)
    task = next((e for e in ev if e.get("type") == "task"), {})
    lines = [f"TASK: {str(task.get('instruction') or '')[:task_chars]}"]
    body, n = [], 0
    for e in ev:
        t = e.get("type")
        if t == "llm" and "check" not in e and (e.get("content") or "").strip():
            body.append(f"  THINK: {str(e.get('content'))[:250]!r}")
        elif t == "step":
            n += 1
            a = e.get("args")
            a = a if isinstance(a, str) else json.dumps(a, default=str)
            body.append(f"  [step {n}] ACT {e.get('tool')}: {a[:arg_chars]}\n  RESULT: {str(e.get('observation') or '')[:obs_chars]!r}")
        elif t in ("verifier_reject", "exception"):
            body.append(f"  {t.upper()}: {str(e.get('feedback') or e.get('error'))[:obs_chars]}")
    if len(body) > max_events:
        body = body[:head] + [f"  ... ({len(body) - max_events} events omitted)"] + body[-(max_events - head):]
    return "\n".join(lines + body)


def _name(s) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9_]", "_", str(s or "").strip().lower())).strip("_")[:48].strip("_")


class Clusters:
    def __init__(self, ws: Path, resume: bool):
        self.reg: dict[str, dict] = {}      # name -> {definition, harness_fixable, round}
        self.assign: dict[str, dict] = {}   # trajectory path -> {cluster, what, task_id, round}
        self.ws = ws
        self.jpath = ws / "judge_cache.jsonl"
        self.jcache: dict[tuple, dict] = {}
        if resume and self.jpath.exists():
            for l in self.jpath.read_text(encoding="utf-8").splitlines():
                try:
                    d = json.loads(l)
                    self.jcache[(d["path"], d["mode"])] = d
                except Exception:
                    pass
        elif self.jpath.exists():
            self.jpath.unlink()
        self.lock = threading.Lock()

    # ---------------------------------------------------------------- labelling
    def _reg_text(self, counts: dict | None = None) -> str:
        counts = counts or self.cum_counts()
        return "\n".join(f"- {n}: {m['definition']} | {m.get('signature') or '-'} [{counts.get(n, 0)}]"
                         for n, m in self.reg.items()) or "(none yet)"

    def cum_counts(self) -> dict:
        c: dict[str, int] = {}
        for a in self.assign.values():
            c[a["cluster"]] = c.get(a["cluster"], 0) + 1
        return c

    def update(self, client, bench: str, fails: list[dict], r: int, ask_json) -> dict:
        """File every failed run not filed yet. Sequential calls (replayed in order on resume)."""
        todo = [x for x in fails if x.get("trajectory_path") and x["trajectory_path"] not in self.assign]
        n_new = 0
        for b in [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)]:
            n_new += self._file(client, bench, b, r, ask_json)
        left = [x for x in todo if x["trajectory_path"] not in self.assign]
        for i in range(0, len(left), 3):  # once more, in small batches, for runs a reply skipped
            n_new += self._file(client, bench, left[i:i + 3], r, ask_json)
        return self._finish(todo, n_new, self._merge(client, bench, ask_json))

    def _file(self, client, bench, batch, r, ask_json) -> int:
        n_new = 0
        if batch:
            runs = "\n\n".join(f"[{j}]\n{digest(x['trajectory_path'])}" for j, x in enumerate(batch))
            d = ask_json(client, LABEL.format(registry=self._reg_text(), runs=runs), f"b4:{bench}:cluster_label", 3000)
            for row in d.get("runs") or []:
                if not isinstance(row, dict) or not isinstance(row.get("i"), int) or not 0 <= row["i"] < len(batch):
                    continue
                name = _name(row.get("cluster"))
                if not name:
                    continue
                if name not in self.reg:
                    dfn = str(row.get("definition") or "").strip()
                    dfn = dfn if len(dfn) >= 10 else str(row.get("did") or row.get("what_went_wrong") or "").strip()
                    if len(dfn) < 10:
                        continue
                    self.reg[name] = {"definition": dfn[:300], "signature": str(row.get("signature") or "")[:300],
                                      "harness_fixable": row.get("harness_fixable") is not False, "round": r}
                x = batch[row["i"]]
                self.assign[x["trajectory_path"]] = {
                    "cluster": name, "step": row.get("step") if isinstance(row.get("step"), int) else None,
                    "did": str(row.get("did") or "")[:240], "evidence": str(row.get("evidence") or "")[:240],
                    "better": str(row.get("better") or "")[:240], "what": str(row.get("what_went_wrong") or "")[:240],
                    "task_id": x["task_id"], "round": r}
                n_new += 1
        return n_new

    def _merge(self, client, bench, ask_json) -> dict:
        merged = {}
        if len(self.reg) > MAX_CLUSTERS:
            d = ask_json(client, MERGE.format(registry=self._reg_text(), k=MAX_CLUSTERS), f"b4:{bench}:cluster_merge", 1500)
            for a, b in ((d.get("merge") or {}) if isinstance(d.get("merge"), dict) else {}).items():
                a, b = _name(a), _name(b)
                if a in self.reg and b in self.reg and a != b and b not in merged:
                    merged[a] = b
            for a, b in merged.items():
                self.reg.pop(a, None)
                for v in self.assign.values():
                    if v["cluster"] == a:
                        v["cluster"] = b
        return merged

    def _finish(self, todo, n_new, merged) -> dict:
        self.save()
        return {"filed": n_new, "unfiled": len(todo) - n_new, "merged": merged}

    def save(self):
        (self.ws / "clusters.json").write_text(json.dumps({"registry": self.reg, "assign": self.assign,
                                                           "counts": self.cum_counts()}, indent=1), encoding="utf-8")

    def members(self, name: str) -> set[str]:
        return {p for p, a in self.assign.items() if a["cluster"] == name}

    def view(self, fails: list[dict], max_chars: int = 6000) -> str:
        """Clusters by their count among the CURRENT failed runs, with failed tasks, the total filed over the search,
        the labeller's opinion on fixability and two examples of what went wrong."""
        cur = {x["trajectory_path"]: x for x in fails if x.get("trajectory_path") in self.assign}
        tot = self.cum_counts()
        rows = []
        for n, m in self.reg.items():
            paths = [p for p in cur if self.assign[p]["cluster"] == n]
            ex = []
            for p in paths:
                a = self.assign[p]
                w = (f"did: {a['did']} | evidence: {a.get('evidence') or '-'} | better: {a.get('better') or '-'}"
                     if a.get("did") else a.get("what", ""))
                if w and w not in ex:
                    ex.append(w)
            rows.append((len(paths), len({cur[p]["task_id"] for p in paths}), n, m, ex[:2], tot.get(n, 0)))
        rows.sort(key=lambda t: (-t[0], -t[5], t[2]))
        out = [f"{len(cur)} of the {len(fails)} failed runs of the current harness are filed in clusters "
               "(name: definition | signature | failed runs now / failed tasks now / filed over the search | labeller's view;\n"
               "each example is one run's decisive step: what the agent did, what showed it was a mistake, what was better):"]
        for k, kt, n, m, ex, t in rows:
            out.append(f"- {n}: {m['definition']} | signature: {m.get('signature') or '-'} | {k} runs / {kt} tasks / {t} | "
                       f"{'harness-fixable' if m['harness_fixable'] else 'model/task/environment'}"
                       + "".join(f"\n    e.g. {e}" for e in ex))
        s = "\n".join(out)
        return s[:max_chars]

    def define(self, name: str) -> str:
        return self.reg.get(name, {}).get("definition", "")

    # ---------------------------------------------------------------- judge
    def _judge(self, client, bench: str, path: str, name: str) -> dict:
        key = (path, name)
        if key in self.jcache:
            return self.jcache[key]
        d = {}
        for _ in range(2):
            try:
                rsp = client.chat([{"role": "user", "content": JUDGE.format(name=name, definition=self.define(name),
                                                                              signature=self.reg.get(name, {}).get("signature") or "-",
                                                                              digest=digest(path))}],
                                  tag=f"b4j:{bench}:mode_judge", max_tokens=600, fallback_no_reasoning=True)
                d = extract_json(rsp.content or "")
                if isinstance(d, dict) and isinstance(d.get("shows"), bool):
                    break
            except Exception:
                d = {}
        row = {"path": path, "mode": name, "shows": d.get("shows") if isinstance(d, dict) else None,
               "why": str((d or {}).get("why") or "")[:200] if isinstance(d, dict) else ""}
        if row["shows"] is None:
            return row  # not cached: an unanswered judgement is not a measurement
        with self.lock:
            self.jcache[key] = row
            with self.jpath.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
        return row

    def prejudge(self, client, bench: str, paths: list[str], name: str):
        todo = sorted({p for p in paths if p and (p, name) not in self.jcache})
        if todo:
            with ThreadPoolExecutor(JUDGE_WORKERS) as ex:
                list(ex.map(lambda p: self._judge(client, bench, p, name), todo))

    def judged(self, path: str, name: str) -> float | None:
        v = self.jcache.get((path, name), {}).get("shows")
        return None if v is None else float(v)


class ModeMetric:
    """`mode:<cluster>`: 1 if the blind judge finds the run showing that failure cluster, else 0."""
    def __init__(self, name: str):
        self.name = name

    def __repr__(self):
        return f"mode:{self.name}"
