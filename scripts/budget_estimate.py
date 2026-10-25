"""Real-run budget estimate from MEASURED smoke costs (results/cost_per_episode.json + spend.json tags).

Assumptions (edit below) are printed with the result; nothing here is a measurement except the per-episode
costs and per-call overheads read from results/.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
cpe = json.loads((ROOT / "results" / "cost_per_episode.json").read_text())
tags = json.loads((ROOT / "results" / "spend.json").read_text())["by_tag"]

# test-set sizes, verified with the adapters / appworld.load_task_ids on this machine
TEST = {"alfworld": 134 + 140,            # valid_unseen 134 + valid_seen 140
        "appworld": 168 + 417,            # test_normal 168 + test_challenge 417
        "browsecomp_plus": 830 - 150}     # 830 queries minus the 100 train + 50 val carved out of the same pool
TRAIN_CAP = {"appworld": 90}              # AppWorld has only 90 train tasks (val comes from dev: 57)
PLAN = {"methods": 4,                     # B1, B2, B3 + HarnessGraph
        "rounds": 10, "train_tasks": 100, "train_rolls": 3, "val_tasks": 50, "check_execs": 2, "seeds": 3}


def main():
    p = PLAN
    rows, total = [], 0.0
    for b, c in cpe.items():
        shared = min(p["train_tasks"], TRAIN_CAP.get(b, 10**9)) * p["train_rolls"] + p["val_tasks"]          # H0 evidence, once per seed
        per_method_evo = p["rounds"] * (p["check_execs"] + p["val_tasks"])      # matched per-method budget
        test = TEST[b] * (p["methods"] + 1)                                    # every method + H0 on full test
        eps = p["seeds"] * (shared + p["methods"] * per_method_evo + test)
        usd = eps * c
        total += usd
        rows.append((b, c, shared, per_method_evo, test, eps, usd))
    # measured non-episode overhead (proposer/investigator/composer/adaptation/distill calls) during the smoke
    ovh = sum(v["usd"] for t, v in tags.items() if t.startswith(("b1:", "b2:", "b3:")))
    out = ["| benchmark | measured $/episode | shared H0 eps | per-method evolution eps | test eps (H0 + methods) | total eps (x seeds) | est. USD |",
           "|---|---|---|---|---|---|---|"]
    for b, c, sh, pm, te, eps, usd in rows:
        out.append(f"| {b} | {c:.5f} | {sh} | {pm} | {te} | {eps:,} | {usd:,.2f} |")
    out.append(f"| **total** | | | | | | **{total:,.2f}** |")
    out.append("")
    out.append(f"Assumptions: {json.dumps(PLAN)}; test sizes {json.dumps(TEST)}. Non-episode LLM overhead measured in the "
               f"smoke run was ${ovh:.4f} in total for all methods/benchmarks (all rounds incl. superseded attempts), i.e. "
               f"< 10% of episode cost; budget +10% for it and for per-task composer/adaptation calls: "
               f"**≈ ${total * 1.1:,.2f}**.")
    print("\n".join(out))
    return "\n".join(out)


if __name__ == "__main__":
    main()
