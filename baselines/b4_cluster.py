"""B4 v7 with failure clusters (B4_CLUSTER=1).

Every failed training run of the current harness is read by an LLM, which says in one sentence what went wrong and
files the run under an existing failure cluster or opens a new one (name + one-sentence definition). The registry is
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

BATCH = 6            # failed runs per labelling call
MAX_CLUSTERS = 12    # above this, one consolidation call merges near-duplicates
JUDGE_WORKERS = 8

LABEL = """You keep a registry of FAILURE CLUSTERS of an AI agent. It is used to decide which change of the agent's
scaffolding to try next, so a cluster must describe a GENERAL pattern of behaviour that recurs across tasks.

Existing clusters (name: definition [failed runs filed so far]):
{registry}

Failed runs (the grader marked each one as failed; read what the agent actually did, including the arguments and
code of its actions):
{runs}

For EACH run give:
- what_went_wrong: one sentence on the agent's mistake, in general terms (no task entities, names, values or ids)
- cluster: the name of the existing cluster it belongs to, or a NEW snake_case name (2-4 short words, <= 40 chars). Reuse a name when
  the meaning is the same. Runs of this batch that share a new pattern get the same new name.
- definition: for a NEW name only, one sentence describing the observable behaviour (general, no task entities)
- harness_fixable: for a NEW name only, false if the pattern is mainly the model's knowledge or reasoning, an
  ambiguous task or an infrastructure failure, true if the scaffolding (tools, observations, checks, loop) could
  reasonably prevent it
Answer ONLY with JSON: {{"runs": [{{"i": 0, "what_went_wrong": "...", "cluster": "...", "definition": "...",
"harness_fixable": true}}]}}"""

MERGE = """These are failure clusters of an AI agent, each with its definition and count of failed runs:
{registry}
Some may describe the same pattern. Merge duplicates so that at most {k} clusters remain; keep distinct patterns
apart. Answer ONLY with JSON: {{"merge": {{"<cluster merged away>": "<cluster it goes into>"}}}} ({{}} if none)."""

JUDGE = """You check whether a finished run of an AI agent shows one specific failure pattern. You are not told
whether the run succeeded.

Pattern `{name}`: {definition}

Run (digest):
{digest}

Answer ONLY with JSON: {{"shows": true or false, "why": "<one short sentence>"}}"""


def digest(path: str, max_events: int = 30, arg_chars: int = 500, obs_chars: int = 300, task_chars: int = 600) -> str:
    """The run as the agent lived it: task, its reasoning, each action WITH its arguments, each result. The outcome
    is not shown."""
    ev = V.load_events(path)
    task = next((e for e in ev if e.get("type") == "task"), {})
    lines = [f"TASK: {str(task.get('instruction') or '')[:task_chars]}"]
    body = []
    for e in ev:
        t = e.get("type")
        if t == "llm" and "check" not in e and (e.get("content") or "").strip():
            body.append(f"  THINK: {str(e.get('content'))[:250]!r}")
        elif t == "step":
            a = e.get("args")
            a = a if isinstance(a, str) else json.dumps(a, default=str)
            body.append(f"  ACT {e.get('tool')}: {a[:arg_chars]}\n  RESULT: {str(e.get('observation') or '')[:obs_chars]!r}")
        elif t in ("verifier_reject", "exception"):
            body.append(f"  {t.upper()}: {str(e.get('feedback') or e.get('error'))[:obs_chars]}")
    if len(body) > max_events:
        lines.append(f"  ... ({len(body) - max_events} earlier events omitted)")
        body = body[-max_events:]
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
        return "\n".join(f"- {n}: {m['definition']} [{counts.get(n, 0)}]" for n, m in self.reg.items()) or "(none yet)"

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
                    dfn = dfn if len(dfn) >= 10 else str(row.get("what_went_wrong") or "").strip()
                    if len(dfn) < 10:
                        continue
                    self.reg[name] = {"definition": dfn[:300],
                                      "harness_fixable": row.get("harness_fixable") is not False, "round": r}
                x = batch[row["i"]]
                self.assign[x["trajectory_path"]] = {"cluster": name, "what": str(row.get("what_went_wrong") or "")[:240],
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

    def view(self, fails: list[dict], max_chars: int = 4000) -> str:
        """Clusters by their count among the CURRENT failed runs, with failed tasks, the total filed over the search,
        the labeller's opinion on fixability and two examples of what went wrong."""
        cur = {x["trajectory_path"]: x for x in fails if x.get("trajectory_path") in self.assign}
        tot = self.cum_counts()
        rows = []
        for n, m in self.reg.items():
            paths = [p for p in cur if self.assign[p]["cluster"] == n]
            ex = []
            for p in paths:
                w = self.assign[p]["what"]
                if w and w not in ex:
                    ex.append(w)
            rows.append((len(paths), len({cur[p]["task_id"] for p in paths}), n, m, ex[:2], tot.get(n, 0)))
        rows.sort(key=lambda t: (-t[0], -t[5], t[2]))
        out = [f"{len(cur)} of the {len(fails)} failed runs of the current harness are filed in clusters "
               "(name: definition | failed runs now / failed tasks now / filed over the search | labeller's view):"]
        for k, kt, n, m, ex, t in rows:
            out.append(f"- {n}: {m['definition']} | {k} runs / {kt} tasks / {t} | "
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
