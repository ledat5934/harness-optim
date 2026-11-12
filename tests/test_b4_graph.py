"""Causal map of the B4 v7 ledger (baselines/b4_graph.py): pure functions on synthetic ledgers."""
from baselines import b4_graph as G


def eff(**kw):
    return {k: {"before": a, "after": b, "up": 10 if b > a else 0, "down": 10 if b < a else 0, "n": 10, "clear": c}
            for k, (a, b, c) in kw.items()}


def row(i, beh, direction, verdict, status="rejected", shifted=None, W=0, L=0, effects=None, **kw):
    r = {"id": f"c{i}", "round": 1, "slot": "verifier", "name": f"e{i}", "behaviour": beh, "direction": direction,
         "hypothesis": "h" * 30, "mechanism": "m" * 30, "verdict": verdict, "status": status, **kw}
    if shifted is not None:
        r["shift"] = {"shifted": shifted, "before": 1.0, "after": 2.0, "as_predicted": 3, "opposite": 9, "n": 16}
        r["outcome"] = {"W": W, "L": L, "n": 16}
    if effects is not None:
        r["effects"] = effects
    return r


def test_behaviour_nodes_pool_outcomes_and_group_inseparable_features():
    led = [row(1, "steps", "up", "SUPPORTED", "merged", True, 6, 0, eff(steps=(5, 9, True), tokens=(10, 30, True))),
           row(2, "finish_rejects", "up", "SUPPORTED", "rejected", True, 4, 1,
               eff(steps=(5, 8, True), tokens=(10, 20, True), finish_rejects=(0, 2, True), answered=(1, 1, False))),
           row(3, "steps", "down", "REFUTED", "rejected", True, 0, 5, eff(steps=(9, 4, True)))]
    g = G.build(led)
    by = {tuple(b["features"]): b for b in g["behaviours"]}
    both = by[("steps up", "tokens up")]            # moved by the same two edits: one node
    assert [e["id"] for e in both["edits"]] == ["c1", "c2"] and (both["W"], both["L"]) == (10, 1)
    assert both["reading"] == "more wins than losses"
    assert by[("steps down",)]["reading"] == "more losses than wins"
    assert by[("finish_rejects up",)]["reading"] == "no clear effect on success"   # 4W/1L of one edit: not enough
    assert not any("answered" in f for b in g["behaviours"] for f in b["features"])  # not a clear effect
    v = G.view(g)
    assert "steps up; tokens up" in v and "[adopted]" in v and "10 wins / 1 losses" in v


def test_open_ideas_are_untested_hypotheses_with_their_failure():
    led = [row(1, "answered", "up", "DEAD CODE: the edit changed nothing in any of 150 saved runs. Make the condition "
                                      "one that holds", ),
           row(2, "answered ", "up", "INEFFECTIVE: the code did not cause the behaviour", shifted=False, coverage=0.4),
           row(3, "obs_chars", "down", "NOT BUILT: variant load failed /a/b/runs/tag/roots/c3_a1/variants/x/v.py: boom"),
           row(4, "obs_chars", "down", "REFUTED", shifted=True, L=3, effects=eff(obs_chars=(9, 4, True)))]
    g = G.build(led)
    assert [(o["behaviour"], o["direction"], len(o["attempts"])) for o in g["open"]] == [("answered", "up", 2)]
    a = g["open"][0]["attempts"]
    assert a[0]["why"].startswith("DEAD CODE") and "Make the condition" not in a[0]["why"]
    assert "3 as predicted / 9 opposite" in a[1]["why"] and "0.4" in a[1]["why"]
    # obs_chars down was caused later by c4: tested (refuted), no longer an open idea
    assert "obs_chars" not in G.view(g).split("B. Open ideas")[1]
    h = G.attempts(g, "answered", "up")
    assert "verifier/e1" in h and "verifier/e2" in h and G.attempts(g, "answered", "down") == ""
    assert "/a/b/" not in G._short(led[2]["verdict"]) and "v.py" in G._short(led[2]["verdict"])


def test_side_effects_of_adopted_edits_and_their_repair():
    led = [row(1, "steps", "up", "SUPPORTED", "merged", True, 6, 0,
               eff(steps=(5, 9, True), unexecuted_calls=(0, 6, True), tokens=(10, 30, True))),
           row(2, "tokens", "down", "SUPPORTED", "rejected", True, 0, 0, eff(tokens=(30, 12, True))),  # not adopted
           row(3, "answered", "up", "SUPPORTED", "merged", True, 4, 0,
               eff(unexecuted_calls=(6, 0, True), answered=(0.3, 0.6, True)),
               review={"claim": {"behaviour": "unexecuted_calls", "direction": "down"}})]
    g = G.build(led)
    s = {(x["edit"], x["feature"]): x for x in g["side_effects"]}
    assert ("c1", "steps") not in s                                   # the behaviour it was adopted for
    assert s[("c1", "unexecuted_calls")]["moved_back_by"]["id"] == "c3"
    assert s[("c1", "tokens")]["moved_back_by"] is None               # c2 moved it back but was not adopted
    assert ("c3", "unexecuted_calls") not in s and ("c3", "answered") not in s
    v = G.view(g)
    assert "STILL PRESENT in the current harness: tokens 10 -> 30" in v
    assert "later moved back by another adopted edit: unexecuted_calls 0 -> 6 (then c3: 6 -> 0)" in v


def test_empty_ledger_gives_no_text():
    g = G.build([])
    assert G.view(g) == "" and g["behaviours"] == [] and G.attempts(g, "steps", "up") == ""
