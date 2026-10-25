"""Judge sanity check (prints only verdicts, never the decrypted question/answer)."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import llm
from benchmarks.browsecomp_plus import adapter as A
llm.budget_banner("test_bcp_judge")
c = llm.LLM()
ok = True
for tid in A.list_tasks("dev")[:2]:
    env = A.BCPEnv(tid, c); env.reset()
    gold = env.row["answer"]
    env.answer = f"Explanation: based on the documents.\nExact Answer: {gold}\nConfidence: 90%"
    good, gi = env.evaluate()
    env.answer = "Explanation: guess.\nExact Answer: definitely-not-the-answer-xyz\nConfidence: 10%"
    bad, bi = env.evaluate()
    print(f"task {tid}: gold->correct={good} (expect True), wrong->correct={bad} (expect False), "
          f"judge cost ${gi['judge_cost'] + bi['judge_cost']:.6f}")
    ok &= good and not bad
print("JUDGE_SELFTEST", "PASS" if ok else "FAIL")
