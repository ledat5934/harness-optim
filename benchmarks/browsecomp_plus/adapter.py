"""BrowseComp-Plus adapter: BM25 (pyserini/Lucene, prebuilt index) search agent + LLM judge.

Split: "subset" = the first N queries of shard 0 (see prepare_subset.py). The benchmark has a single test set.
We partition the subset deterministically: the first 10 are "dev" (smoke/H0/train/val), the rest are "test".
Tools follow the official search agent defaults (search_agent/openai_client.py: --k 5, --snippet-max-tokens 512,
QUERY_TEMPLATE_NO_GET_DOCUMENT): `search(query)` returns the top-5 docid/score/snippet. Snippets are cut to about
512 Qwen tokens; we approximate this with 2000 characters to avoid downloading a tokenizer.
We also expose `get_document(docid)`, as in the official QUERY_TEMPLATE variant, plus `finish(answer)`.
JUDGE: the official judge is Qwen3-32B (GPU). We use the official GRADER_TEMPLATE with our OpenRouter model
instead, so scores are NOT comparable with the public leaderboard.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from benchmarks.common import BAD_ARGS, Result, StepResult, TaskSpec, run_with_env, tool_arg

BENCH = "browsecomp_plus"
ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get("BCP_DATA", ROOT / "data" / "browsecomp_plus"))
INDEX = Path(os.environ.get("BCP_INDEX", "/root/bcp_index/bm25" if Path("/root/bcp_index/bm25").exists()
                            else DATA / "indexes" / "bm25"))
K = 5
SNIPPET_CHARS = 2000
DOC_CHARS = 12000
MAX_STEPS = 25
N_DEV = 10
N_DEV_MEDIUM = 80

# Official search-agent prompt (search_agent/prompts.py, MIT), adapted to a finish tool.
GUIDANCE = (
    "You are a deep research agent. You need to answer the given question by interacting with a search engine, "
    "using the search and get_document tools provided. Please perform reasoning and use the tools step by step, "
    "in an interleaved manner. You may use the search and get_document tools multiple times. When you are done, "
    "call the `finish` tool with your final response in the following format:\n"
    "Explanation: {your explanation for your final answer. Cite evidence documents inline by enclosing their "
    "docids in square brackets [] at the end of sentences. For example, [20].}\n"
    "Exact Answer: {your succinct, final answer}\n"
    "Confidence: {your confidence score between 0% and 100% for your answer}"
)

# Official GRADER_TEMPLATE (search_agent/prompts.py, MIT).
GRADER_TEMPLATE = """
Judge whether the following [response] to [question] is correct or not based on the precise and unambiguous [correct_answer] below.

[question]: {question}

[response]: {response}

Your judgement must be in the format and criteria specified below:

extracted_final_answer: The final exact answer extracted from the [response]. Put the extracted answer as 'None' if there is no exact, final answer to extract from the response.

[correct_answer]: {correct_answer}

reasoning: Explain why the extracted_final_answer is correct or incorrect based on [correct_answer], focusing only on if there are meaningful differences between [correct_answer] and the extracted_final_answer. Do not comment on any background to the problem, do not attempt to solve the problem, do not argue for any answer different than [correct_answer], focus only on whether the answers match.

correct: Answer 'yes' if extracted_final_answer matches the [correct_answer] given above, or is within a small margin of error for numerical problems. Answer 'no' otherwise, i.e. if there if there is any inconsistency, ambiguity, non-equivalency, or if the extracted answer is incorrect.


confidence: The extracted confidence score between 0|\\%| and 100|\\%| from [response]. Put 100 if there is no confidence score available.
""".strip()

TOOLS = [
    {"type": "function", "function": {
        "name": "search", "description": f"Perform a search on a knowledge source. Returns top-{K} hits with docid, score, and snippet. The snippet contains the document's contents (may be truncated based on token limits).",
        "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "Search query string"}},
                       "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "get_document", "description": "Retrieve a full document by its docid.",
        "parameters": {"type": "object", "properties": {"docid": {"type": "string", "description": "Document ID"}},
                       "required": ["docid"]}}},
    {"type": "function", "function": {
        "name": "finish", "description": "Submit the final response (Explanation / Exact Answer / Confidence).",
        "parameters": {"type": "object", "properties": {"answer": {"type": "string", "description": "Final response text."}},
                       "required": ["answer"]}}},
]

_searcher = None


class AnseriniBM25:
    """Direct pyjnius binding to io.anserini.search.SimpleSearcher, the Java class that pyserini's
    LuceneSearcher wraps (same default BM25 k1=0.9, b=0.4). Workaround: pyserini 2.4's `pyserini.search` package
    imports torch at import time, and installing torch is not worth it on this 8 GB / no-GPU machine just to run
    BM25. The jar is the anserini fat jar shipped inside the pyserini wheel. Returns hits with the same fields
    the official BM25Searcher reads."""

    def __init__(self, index_dir: str):
        import glob
        import sys as _sys

        import jnius_config
        jars = glob.glob(os.path.join(_sys.prefix, "lib", "python*", "site-packages", "pyserini", "resources",
                                      "jars", "anserini-*-fatjar.jar"))
        if not jars:
            raise FileNotFoundError("anserini fatjar not found (pip install --no-deps pyserini)")
        if not jnius_config.vm_running:
            jnius_config.add_options("-Xmx1g", "--add-modules=jdk.incubator.vector")
            jnius_config.set_classpath(jars[0])
        from jnius import autoclass
        self._s = autoclass("io.anserini.search.SimpleSearcher")(index_dir)
        import threading
        self._lock = threading.Lock()

    def search(self, query: str, k: int):
        with self._lock:
            hits = self._s.search(query, k)
            out = []
            for h in hits:
                # Some hits come back with a null lucene_document (observed NullPointerException in a run):
                # fall back to fetching the stored doc by id, and skip the hit if that also fails.
                try:
                    raw = h.lucene_document.get("raw")
                except Exception:
                    d = self._s.doc(h.docid)
                    raw = None if d is None else d.get("raw")
                if raw is not None:
                    out.append((h.docid, float(h.score), raw))
            return out

    def doc_raw(self, docid: str):
        with self._lock:
            d = self._s.doc(docid)
            return None if d is None else d.get("raw")


def searcher() -> AnseriniBM25:
    global _searcher
    if _searcher is None:
        _searcher = AnseriniBM25(str(INDEX))
    return _searcher


def _subset() -> list[dict]:
    p = DATA / "subset.jsonl"
    if not p.exists():
        raise FileNotFoundError(f"{p} missing; run python -m benchmarks.browsecomp_plus.prepare_subset")
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def list_tasks(split: str = "dev") -> list[str]:
    """dev/test: the smoke partition (first 10 / the rest). dev80/heldout: the medium partition (first 80 queries for
    train+val / the rest, from which the 100-task test subset is drawn). Both need subset.jsonl in dataset order."""
    ids = [r["query_id"] for r in _subset()]
    return {"dev": ids[:N_DEV], "test": ids[N_DEV:], "dev80": ids[:N_DEV_MEDIUM], "heldout": ids[N_DEV_MEDIUM:],
            "subset": ids}[split]


class BCPEnv:
    def __init__(self, task_id: str, judge_llm):
        rows = {r["query_id"]: r for r in _subset()}
        self.row = rows[task_id]
        self.task_id = task_id
        self.judge_llm = judge_llm
        self.answer: str | None = None
        self.retrieved: list[str] = []
        self.counts = {"search": 0, "get_document": 0}

    def reset(self) -> TaskSpec:
        return TaskSpec(task_id=self.task_id, benchmark=BENCH, instruction=f"Question: {self.row['query']}",
                        initial_observation="(no observation yet; use the search tool)", tools=TOOLS,
                        guidance=GUIDANCE, finish_tool="finish", max_steps=MAX_STEPS)

    def step(self, tool: str, args: dict) -> StepResult:
        if tool == "search":
            self.counts["search"] += 1
            q = tool_arg(args, "query", "q", "search_query")
            if q is None:
                return StepResult(BAD_ARGS)
            q = str(q)
            out = []
            for docid, sc, raw_s in searcher().search(q, K):
                raw = json.loads(raw_s)
                self.retrieved.append(docid)
                out.append({"docid": docid, "score": round(sc, 3), "snippet": raw["contents"][:SNIPPET_CHARS]})
            return StepResult(json.dumps(out, ensure_ascii=False, indent=1))
        if tool == "get_document":
            self.counts["get_document"] += 1
            docid = tool_arg(args, "docid", "doc_id", "id")
            if docid is None:
                return StepResult(BAD_ARGS)
            docid = str(docid).strip().strip("[]").strip("'\"")
            raw_s = searcher().doc_raw(docid)
            if raw_s is None:
                return StepResult(f"No document with docid {docid}")
            self.retrieved.append(docid)
            text = json.loads(raw_s)["contents"]
            return StepResult(json.dumps({"docid": docid, "text": text[:DOC_CHARS]}, ensure_ascii=False))
        if tool == "finish":
            ans = tool_arg(args, "answer", "final_answer", "exact_answer")
            if ans is None:
                return StepResult(BAD_ARGS)
            self.answer = str(ans)
            return StepResult("Final answer recorded.", done=True)
        return StepResult(f"Unknown tool '{tool}'.")

    def evaluate(self) -> tuple[bool, dict]:
        info = {"tool_counts": self.counts, "n_retrieved": len(set(self.retrieved)), "status":
                "completed" if self.answer else "no_answer"}
        if not self.answer:
            return False, {**info, "judge": "no answer submitted"}
        prompt = GRADER_TEMPLATE.format(question=self.row["query"], response=self.answer,
                                        correct_answer=self.row["answer"])
        r = self.judge_llm.chat([{"role": "user", "content": prompt}], tag="judge:browsecomp_plus", max_tokens=1024)
        # 'correct: yes', '**correct:** yes', '**Correct**: Yes'; the last one is the verdict line
        m = re.findall(r"correct\W{0,4}?:\W{0,4}(yes|no)\b", r.content, re.I)
        ok = bool(m and m[-1].lower() == "yes")
        # The judge cost is real spend: it is tracked in spend.json under tag judge:*, and reported separately.
        return ok, {**info, "judge_raw": r.content[-600:], "judge_cost": r.cost,
                    "judge_tokens": r.prompt_tokens + r.completion_tokens}

    def close(self) -> None:
        pass


def run_episode(task_id: str, harness, llm, split: str = "dev", run_tag: str = "adhoc",
                max_steps: int | None = None) -> Result:
    res = run_with_env(BENCH, task_id, lambda: BCPEnv(task_id, llm), harness, llm, run_tag=run_tag,
                       max_steps=max_steps)
    ji = res.extra.get("eval_info") or {}
    res.cost = round(res.cost + float(ji.get("judge_cost") or 0), 8)  # include judge in per-episode cost
    res.extra["judge_cost"] = ji.get("judge_cost")
    return res
