"""Prompt texts for B2, taken from ModularRSI and cut to what applies without a tool-calling agent.

Source: third_party/ModularRSI/src/harbor/agents/terminus_2_modular/self_evo/trajectory_analysis.py
(commit b5c72c3, CC BY-NC 4.0, research use only).

Changes: the reference constants are imported from the vendored copy of that file, not retyped.
Each function below removes one block that tells the model to read files, edit files, or emit
harness actions (`<read_file>`, `<task_complete>`, MODULE TRACE, helper tools). Every removal is
asserted to match exactly once, so a change in the reference text fails here instead of silently
shipping a different prompt. The composer prompt is copied from composer/llm_dynamic.py::_llm_pick
with the helper-tool block dropped and the example changed to H0 slot names.
"""
from __future__ import annotations

import re

from baselines.vendor.modularrsi import trajectory_analysis as ta


def _cut(text: str, pattern: str) -> str:
    out, n = re.subn(pattern, "", text, flags=re.DOTALL)
    assert n == 1, f"expected one match for {pattern!r}, got {n}"
    return out


def _sub(text: str, old: str, new: str) -> str:
    assert text.count(old) == 1, f"expected one occurrence of {old[:60]!r}"
    return text.replace(old, new)


def _tidy(text: str) -> str:
    return text.rstrip() + "\n"


# --- contrast investigation (locked to one slot; pass vs fail roll) ---------------------------
CONTRAST_INVESTIGATION = ta._CONTRAST_INVESTIGATION_PREAMBLE
CONTRAST_INVESTIGATION = _cut(CONTRAST_INVESTIGATION, r"Investigate the raw rolls with .*?readable at `\{locked\}/`\.\n\n")
CONTRAST_INVESTIGATION = _cut(CONTRAST_INVESTIGATION, r"\s*Then `<task_complete>true</task_complete>`\. Do NOT\s+edit any file — you are diagnosis only\.")
CONTRAST_INVESTIGATION = _tidy(CONTRAST_INVESTIGATION)

# Same finding block as the reference; the divergence field is the one the investigator fills.
CONTRAST_DIVERGENCE_FIELD = ta._DIVERGENCE_FIELD


# --- efficiency investigation (task passed, but wastefully) -----------------------------------
EFFICIENCY_INVESTIGATION = ta._EFFICIENCY_INVESTIGATION_PREAMBLE
EFFICIENCY_INVESTIGATION = _cut(EFFICIENCY_INVESTIGATION, r"Investigate with `<read_file>`.*?readable\.\n\n")
EFFICIENCY_INVESTIGATION = _cut(EFFICIENCY_INVESTIGATION, r"\s*Then `<task_complete>true</task_complete>`\. Do NOT edit any file\.")
EFFICIENCY_INVESTIGATION = _tidy(EFFICIENCY_INVESTIGATION)


# --- editor review of a proposed change (reward-blind) ----------------------------------------
REVIEW = ta._REVIEW_PREAMBLE
REVIEW = _cut(REVIEW, r"1\. \*\*Re-investigate the real trajectories\*\*.*?in context\.\n")
REVIEW = _sub(REVIEW, "2. Then judge the change", "1. Judge the change")
REVIEW = _cut(REVIEW, r"- Helper tools in `tools/helpers/\*\.py`.*?cannot occur\.\n")
REVIEW = _cut(REVIEW, r"The per-trial \*\*MODULE TRACE\*\*.*?never ran\.\n\n")
REVIEW = _cut(REVIEW, r"- Protocol: emit the action.*?`<task_complete>`\.\n")
REVIEW = _cut(REVIEW, r"\n*# You are READ-ONLY here.*?narrate what the harness might do\.")
REVIEW = _sub(REVIEW, "Do NOT edit any files. When you are done investigating, submit your decision as",
              "Submit your decision as")
REVIEW = _sub(REVIEW, "ONE structured action", "ONE structured block")
REVIEW = _sub(REVIEW, "this ACTION is the ONLY thing the harness reads", "this block is the ONLY thing the loop reads")
REVIEW = _sub(REVIEW, "the action EXECUTES", "the block is well-formed")
REVIEW = _tidy(REVIEW)


# --- composer: one call picks one variant per slot for a task -----------------------------------
def composer_prompt(task: str, catalog: str) -> str:
    """Same wording as llm_dynamic._llm_pick, minus the helper block; example uses H0 slot names."""
    return (
        "You assemble the module bundle for a terminal coding agent about to "
        "attempt the task below. For EACH module type listed, pick the SINGLE "
        "implementation whose description best fits THIS task. Match the variant "
        "to what the task actually needs; when in doubt prefer the default. "
        "There is no reward signal — judge from the descriptions and the task.\n\n"
        f"# Task\n{task}\n\n"
        f"# Choices per module type\n{catalog}\n\n"
        "Answer with ONLY a JSON object mapping each type to the chosen impl "
        'name, e.g. {"agent_loop": "default"}. Include only the '
        "types listed."
    )
