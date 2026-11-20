"""B4 v7 causal map: a view of the experiment ledger as `edit -> behaviour change -> outcome`.

The ledger (one row per candidate) stays the only source of truth; this module derives three things from it and
nothing here is stored except as a per-round dump (`graph.json`) for inspection:

1. behaviour nodes: every feature an edit moved clearly, with the outcomes measured under the edits that moved it.
   Features moved by exactly the same edits are one node: the experiments cannot tell them apart.
2. open ideas: hypotheses whose predicted behaviour was never caused (code not built, dead code, behaviour did not
   appear). They are untested, not refuted, and keep the reasons their code failed.
3. side effects: what each adopted edit changed besides the behaviour it was adopted for, and whether a later
   adopted edit moved it back.

Everything is feature names, slot names and counts: no task content.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict

UNBUILT = ("NOT BUILT", "DEAD CODE")
MARGIN = 2    # wins - losses (pooled over the edits of a node) ...
ALPHA = 0.1   # ... and one-sided sign test level, to call the outcome under a behaviour one-sided


def _sign_p(w: int, l: int) -> float:
    n = w + l
    return sum(math.comb(n, i) for i in range(w, n + 1)) / 2 ** n if n else 1.0


def _short(text: str, n: int = 220) -> str:
    """One line, no absolute paths (they carry run tags), without the advice appended to gate messages."""
    t = str(text or "").split("Make the condition")[0]
    t = re.sub(r"(?:/[\w.\-]+)+/([\w.\-]+)", r"\1", t)
    return re.sub(r"\s+", " ", t).strip()[:n]


def _norm(expr: str) -> str:
    return re.sub(r"\s+", "", str(expr or ""))


def _names(expr: str) -> set:
    return set(re.findall(r"[A-Za-z_][A-Za-z_0-9]*", str(expr or "")))


def _clear(row: dict) -> dict:
    """feature -> 'up' | 'down' for every feature the edit moved clearly."""
    return {k: ("up" if e["after"] > e["before"] else "down") for k, e in (row.get("effects") or {}).items()
            if e.get("clear") and e.get("after") != e.get("before")}


def _tally(row: dict) -> dict:
    t = row.get("pooled") or row.get("outcome") or {}
    return {"W": int(t.get("W") or 0), "L": int(t.get("L") or 0), "n": int(t.get("n") or 0)}


def _caused(row: dict) -> bool:
    return bool((row.get("shift") or {}).get("shifted"))


def build(ledger: list[dict]) -> dict:
    # ---- 1. behaviour nodes
    moved = defaultdict(dict)  # (feature, direction) -> {edit id: row}
    for row in ledger:
        for k, d in _clear(row).items():
            moved[(k, d)][row["id"]] = row
    groups = defaultdict(list)  # the same set of edits -> features
    for (k, d), rows in moved.items():
        groups[tuple(sorted(rows))].append((k, d))
    behaviours = []
    for ids, fs in groups.items():
        rows = [moved[fs[0]][i] for i in ids]
        w, l = sum(_tally(x)["W"] for x in rows), sum(_tally(x)["L"] for x in rows)
        behaviours.append({
            "features": sorted(f"{k} {d}" for k, d in fs),
            "edits": [{"id": x["id"], "slot": x["slot"], "name": x["name"], "status": x.get("status"), **_tally(x)}
                      for x in rows],
            "W": w, "L": l,
            "reading": "more wins than losses" if w - l >= MARGIN and _sign_p(w, l) <= ALPHA
            else "more losses than wins" if l - w >= MARGIN and _sign_p(l, w) <= ALPHA
            else "no clear effect on success"})
    behaviours.sort(key=lambda b: (b["reading"] == "no clear effect on success", -abs(b["W"] - b["L"]), -len(b["edits"])))
    # ---- 2. open ideas
    tested = {(_norm(x["behaviour"]), x["direction"]) for x in ledger if _caused(x)}
    opened = defaultdict(list)
    for row in ledger:
        key = (_norm(row["behaviour"]), row["direction"])
        if _caused(row) or key in tested:
            continue
        v = str(row.get("verdict") or "")
        sh = row.get("shift") or {}
        if v.startswith(UNBUILT):
            why = _short(v)
        elif sh:
            why = (f"the code ran on {row.get('coverage', '?')} of the runs but the metric went {sh.get('before')} -> "
                   f"{sh.get('after')} ({sh.get('as_predicted', 0)} as predicted / {sh.get('opposite', 0)} opposite of "
                   f"{sh.get('n', 0)} branches)")
        else:
            why = _short(v) or "no measurement"
        opened[key].append({"id": row["id"], "round": row.get("round"), "slot": row["slot"], "name": row["name"],
                            "mechanism": _short(row.get("mechanism"), 180), "why": why})
    open_ideas = [{"behaviour": next(x["behaviour"] for x in ledger if _norm(x["behaviour"]) == b), "direction": d,
                   "attempts": a} for (b, d), a in opened.items()]
    # ---- 3. side effects of adopted edits
    merged = [x for x in ledger if x.get("status") == "merged"]
    side = []
    for i, row in enumerate(merged):
        meant = _names(row.get("behaviour")) | _names(((row.get("review") or {}).get("claim") or {}).get("behaviour"))
        for k, d in _clear(row).items():
            if k in meant:
                continue
            e = row["effects"][k]
            later = next(({"id": y["id"], "name": y["name"], "before": y["effects"][k]["before"],
                           "after": y["effects"][k]["after"]}
                          for y in merged[i + 1:] if _clear(y).get(k) not in (None, d)), None)
            side.append({"edit": row["id"], "slot": row["slot"], "name": row["name"], "feature": k, "direction": d,
                         "before": e["before"], "after": e["after"], "branches": e["n"], "moved_back_by": later})
    return {"behaviours": behaviours, "open": open_ideas, "side_effects": side,
            "n_edits": len(ledger), "n_measured": sum(1 for x in ledger if x.get("effects"))}


def view(g: dict, max_rows: int = 8) -> str:
    """The map as prompt text. Empty string when the ledger holds nothing to derive."""
    out = []
    if g.get("behaviours"):
        out.append("A. Behaviour changes that edits actually caused, and the paired outcomes measured under those edits "
                   "(features on one line moved together in the same edits: these experiments cannot tell which of "
                   "them mattered):")
        for b in g["behaviours"][:max_rows]:
            eds = ", ".join(f"{e['id']} {e['slot']}/{e['name']} {e['W']}W/{e['L']}L"
                            + (" [adopted]" if e["status"] == "merged" else "") for e in b["edits"])
            out.append(f"- {'; '.join(b['features'])}\n    caused by {len(b['edits'])} edit(s): {eds}\n"
                       f"    together: {b['W']} wins / {b['L']} losses -> {b['reading']}")
    if g.get("open"):
        out.append("B. Open ideas: the predicted behaviour was never caused, so the hypothesis is UNTESTED (not "
                   "refuted). Each may be proposed again, but only by a route that avoids the recorded failure:")
        for o in g["open"][:max_rows]:
            out.append(f"- `{o['behaviour']}` {o['direction']}: {len(o['attempts'])} failed attempt(s)")
            for a in o["attempts"][-3:]:
                out.append(f"    [{a['id']}, round {a['round']}, {a['slot']}/{a['name']}] {a['mechanism']}\n"
                           f"      failed because: {a['why']}")
    if g.get("side_effects"):
        rows = g["side_effects"]
        out.append("C. Side effects of adopted edits (changes they made besides the behaviour they were adopted for; "
                   "measured on branches when the edit was tested). One still present may be a cost worth removing "
                   "by a follow-up edit that keeps the benefit, or it may be the cause of the benefit:")
        by = defaultdict(lambda: ([], []))
        for s in rows:
            back = s["moved_back_by"]
            by[f"{s['edit']} {s['slot']}/{s['name']}"][back is not None].append(
                f"{s['feature']} {s['before']:g} -> {s['after']:g}" + (f" (then {back['id']}: {back['before']:g} -> "
                                                                         f"{back['after']:g})" if back else ""))
        for name, (still, back) in by.items():
            out.append(f"- {name}\n    STILL PRESENT in the current harness: {'; '.join(still) or '(none)'}"
                       + (f"\n    later moved back by another adopted edit: {'; '.join(back)}" if back else ""))
    return "\n".join(out)


def attempts(g: dict, behaviour: str, direction: str) -> str:
    """Earlier failed attempts at the same predicted behaviour, as context for the implementer."""
    key = (_norm(behaviour), direction)
    for o in g.get("open") or []:
        if (_norm(o["behaviour"]), o["direction"]) == key:
            return "\n".join(f"- {a['slot']}/{a['name']}: {a['mechanism']}\n  failed because: {a['why']}"
                             for a in o["attempts"][-3:])
    return ""


__all__ = ["build", "view", "attempts"]
