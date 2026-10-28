"""memory/default: no cross-episode memory (H0). recall() returns "", update() does nothing.

This is the seed the evolution methods start from; B3 (MemoHarness-style) and HarnessGraph add real memory
variants in this slot.
"""
from __future__ import annotations


class NoMemory:
    def __init__(self, **_):
        pass

    def recall(self, task):
        return ""

    def update(self, task, outcome, success, trajectory):
        return None


def register(reg):
    reg.register("memory", "default", lambda c: NoMemory(**c),
                 "No cross-episode memory: nothing recalled, nothing stored.",
                 niche={"store": "none", "retrieval": "none"})
