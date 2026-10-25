"""Copy-fidelity report (run from E:/KLTN: python scripts/copy_fidelity.py).

Two measures per file. Headline = executed: only the logic lines the offline test suite actually runs, found with
`coverage` (the suite runs under coverage inside this script). Static = every logic line of the file. Both compare
against the reference source.

Logic line = non-blank, not a comment, not inside a docstring, not an import statement (import plumbing is excluded on
both sides). Copied line = a logic line in the in-order longest common subsequence with the reference (difflib matching
blocks). Own files count as 0 copied. Executed logic line = a logic line whose number coverage reports as executed.
Requires the `coverage` package (pip install coverage)."""
import ast, difflib, importlib.util, json, os, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "third_party"
SELF_EVO = REF / "ModularRSI/src/harbor/agents/terminus_2_modular/self_evo"
MEMO = REF / "MemoHarness/src/memoharness"
META = REF / "meta-harness/reference_examples"
VEND = ROOT / "baselines/vendor"


def logic_py(src: str) -> list[tuple[int, str]]:
    """(line number, stripped text) for each logic line of a Python source."""
    tree = ast.parse(src)
    skip = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and body:
            first = body[0]
            if (isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant)
                    and isinstance(first.value.value, str)):
                skip.update(range(first.lineno, first.end_lineno + 1))
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            skip.update(range(node.lineno, node.end_lineno + 1))
    out = []
    for i, line in enumerate(src.split("\n"), 1):
        s = line.strip()
        if not s or s.startswith("#") or i in skip:
            continue
        out.append((i, s))
    return out


def logic_md(src: str) -> list[str]:
    return [l.strip() for l in src.split("\n") if l.strip()]


def matched_idx(ours: list[str], ref: list[str]) -> set[int]:
    """Indices of `ours` that lie in the in-order longest common subsequence with `ref`."""
    sm = difflib.SequenceMatcher(None, ours, ref, autojunk=False)
    return {i for b in sm.get_matching_blocks() for i in range(b.a, b.a + b.size)}


def load(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def executed_map() -> dict[Path, set[int]]:
    """Run the offline suite under coverage; {resolved source path: executed line numbers}. A failing suite aborts."""
    if importlib.util.find_spec("coverage") is None:
        raise SystemExit("coverage is not installed: pip install coverage")
    work = Path(tempfile.mkdtemp(prefix="copyfid_"))
    env = {**os.environ, "COVERAGE_FILE": str(work / ".coverage")}
    cov = [sys.executable, "-m", "coverage"]
    subprocess.run(cov + ["run", "--source=baselines,h0,benchmarks", "-m", "pytest", "-q", "tests"],
                   cwd=ROOT, env=env, check=True)
    out = work / "cov.json"
    subprocess.run(cov + ["json", "-o", str(out)], cwd=ROOT, env=env, check=True)
    files = json.loads(out.read_text(encoding="utf-8"))["files"]
    return {(ROOT / k).resolve(): set(v["executed_lines"]) for k, v in files.items()}


def row(name, ours_path, exe, ref_src=None):
    """`exe` maps resolved paths to executed lines. The static count and the executed count share one matching."""
    pairs = logic_py(load(ours_path))
    ours = [t for _, t in pairs]
    m = matched_idx(ours, [t for _, t in logic_py(ref_src)]) if ref_src else set()
    ran = exe.get(ours_path.resolve(), set())
    ex = {i for i, (ln, _) in enumerate(pairs) if ln in ran}
    return {"file": name, "logic": len(ours), "copied": len(m),
            "exec_logic": len(ex), "exec_copied": len(m & ex)}


exe = executed_map()
report = {}

# ---- B2: ModularRSI. Own files count 0 copied; each vendored file is compared with its reference file.
b2 = []
for name in ["trajectory_analysis", "router", "review_verdict", "backlog", "routing", "clustering", "proposals",
             "portfolio", "dual_implement", "rebase", "promotion", "routing_probe", "confirm", "lease",
             "dispositions", "staging"]:
    b2.append(row(f"vendor/modularrsi/{name}.py", VEND / f"modularrsi/{name}.py", exe,
                  load(SELF_EVO / f"{name}.py")))
b2.append(row("baselines/b2_modular.py (own)", ROOT / "baselines/b2_modular.py", exe))
b2.append(row("vendor/modularrsi/prompts.py (own)", VEND / "modularrsi/prompts.py", exe))
report["B2"] = b2

# ---- B3: MemoHarness. Own file counts 0; vendored files compared with the MemoHarness source.
b3 = []
for rel in ["core/models.py", "bank/experience.py", "config/runtime.py", "llm/retry.py", "llm/distiller.py",
            "controllers/llm_controller.py"]:
    b3.append(row(f"vendor/memoharness/{rel}", VEND / "memoharness" / rel, exe, load(MEMO / rel)))
b3.append(row("baselines/b3_memo.py (own)", ROOT / "baselines/b3_memo.py", exe))
report["B3"] = b3

# ---- B1: Meta-Harness. The whole own file is matched against each candidate reference (Python code and the
# SKILL.md text separately); the better-matching reference is reported. Executed counts use the Python part only.
b1_path = ROOT / "baselines/b1_freeform.py"
b1_src = load(b1_path)
best = None
for ref_name, (py_path, md_path) in {
    "terminal_bench_2": (META / "terminal_bench_2/meta_harness.py",
                         META / "terminal_bench_2/.claude/skills/meta-harness-terminal-bench-2/SKILL.md"),
    "text_classification": (META / "text_classification/meta_harness.py",
                            META / "text_classification/.claude/skills/meta-harness/SKILL.md"),
}.items():
    pairs = logic_py(b1_src)  # the whole file parses as Python
    ours = [t for _, t in pairs]
    m_py = matched_idx(ours, [t for _, t in logic_py(load(py_path))])
    ours_md = logic_md(b1_src)
    copied_md = len(matched_idx(ours_md, logic_md(load(md_path))))
    ran = exe.get(b1_path.resolve(), set())
    ex = {i for i, (ln, _) in enumerate(pairs) if ln in ran}
    r = {"file": f"baselines/b1_freeform.py vs {ref_name} (code {len(m_py)} + SKILL text {copied_md})",
         "logic": len(ours), "copied": len(m_py) + copied_md,
         "exec_logic": len(ex), "exec_copied": len(m_py & ex)}
    if best is None or r["exec_copied"] > best["exec_copied"]:
        best = r
report["B1"] = [best]

for base, rows in report.items():
    logic_total = sum(r["logic"] for r in rows)
    copied = sum(r["copied"] for r in rows)
    ex_total = sum(r["exec_logic"] for r in rows)
    ex_copied = sum(r["exec_copied"] for r in rows)
    pct = lambda c, t: f"{100 * c / t:.1f}%" if t else "n/a"
    print(f"== {base}: executed {ex_copied} of {ex_total} executed logic lines copied = {pct(ex_copied, ex_total)} "
          f"| static {copied} of {logic_total} = {pct(copied, logic_total)}")
    for r in rows:
        ex_pct = f"{100 * r['exec_copied'] / r['exec_logic']:.0f}%" if r["exec_logic"] else "-"
        print(f"   {r['file']:<70} exec={r['exec_copied']:>4}/{r['exec_logic']:<4} {ex_pct:>5}"
              f"  static={r['copied']:>4}/{r['logic']:<5}")
