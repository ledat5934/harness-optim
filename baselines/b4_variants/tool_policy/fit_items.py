"""tool_policy/fit_items: shorten a long structured observation item by item instead of cutting its middle.

Principle (precondition -> action):
  precondition  the observation is longer than the budget and parses as JSON holding records (a list of objects,
                or one object) with long text fields
  action        cut the long text fields to one common length so that every record and all of its short fields
                (identifiers, scores) stay visible and the result fits the budget
The default policy keeps the head and the tail of the raw text, which drops whole records from the middle of a
result list together with their identifiers. The budget defaults to the context window's per-observation cap, so
the context manager does not cut the result a second time.
With `hint`, when fields were cut and another tool takes one of the records' short fields as a required parameter,
one line names that tool (derived from the tool schemas, not from any benchmark).
Everything else (tool exposure, parsing) is delegated to the default policy.
"""
from __future__ import annotations

import json


def _cut(v, c: int):
    if isinstance(v, str) and len(v) > c:
        return v[:c] + f" ...[+{len(v) - c} chars]"
    if isinstance(v, list):
        return [_cut(x, c) for x in v]
    if isinstance(v, dict):
        return {k: _cut(x, c) for k, x in v.items()}
    return v


def _dump(v) -> str:
    return json.dumps(v, ensure_ascii=False, indent=1)


class FitItems:
    def __init__(self, base, max_obs_chars: int = 6000, min_field: int = 200, hint: bool = False):
        self.base, self.max_obs_chars, self.min_field, self.hint = base, max_obs_chars, min_field, hint

    def tools(self, task):
        return self.base.tools(task)

    def parse(self, resp, task):
        return self.base.parse(resp, task)

    def format_observation(self, action, result, task):
        obs = result.observation
        if not isinstance(obs, str) or len(obs) <= self.max_obs_chars:
            return self.base.format_observation(action, result, task)
        try:
            data = json.loads(obs)
        except (ValueError, TypeError):
            return self.base.format_observation(action, result, task)
        if not isinstance(data, (list, dict)) or not data:
            return self.base.format_observation(action, result, task)
        note = self._hint(data, action, task) if self.hint else ""
        budget = self.max_obs_chars - len(note)
        lo, hi = self.min_field, max(self.min_field, len(obs))
        if len(_dump(_cut(data, lo))) > budget:  # too many records even with short fields: default behaviour
            return self.base.format_observation(action, result, task)
        while lo < hi:  # largest common field length that fits
            mid = (lo + hi + 1) // 2
            if len(_dump(_cut(data, mid))) <= budget:
                lo = mid
            else:
                hi = mid - 1
        return _dump(_cut(data, lo)) + note

    @staticmethod
    def _hint(data, action, task) -> str:
        recs = data if isinstance(data, list) else [data]
        keys = {k for r in recs if isinstance(r, dict) for k, v in r.items() if not isinstance(v, (dict, list))}
        for t in task.tools:
            fn = t.get("function") or {}
            if fn.get("name") in (action.tool, task.finish_tool):
                continue
            req = (fn.get("parameters") or {}).get("required") or []
            if len(req) == 1 and req[0] in keys:
                return (f"\n[Long fields above are shortened. `{fn['name']}` returns one item in full, given its "
                        f"`{req[0]}`.]")
        return ""


def register(reg):
    reg.register("tool_policy", "fit_items",
                 lambda c: FitItems(reg.instantiate("tool_policy", "default", {}), **c),
                 "Default tool policy, but a long JSON observation is shortened field by field so that every record "
                 "and its identifiers stay visible (budget 6000 chars); optional one-line pointer to the tool that "
                 "returns a full record.",
                 config_schema={"max_obs_chars": "int (default 6000)", "min_field": "int (default 200)",
                                "hint": "bool (default false)"},
                 niche={"exposure": "all", "parse": "native+text", "obs": "fit_records"})
