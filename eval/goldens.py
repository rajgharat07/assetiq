"""Expected answers for the official 18 sample questions (challenge answer key).

Assertions check deterministic facts — never LLM prose. Expand carefully;
do not invent numbers that are not verified in the sample dataset.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

# user ids from fleet/users.json
MICHAEL = "U-201"
JESSICA = "U-202"
TYLER = "U-204"
JAKE = "U-102"
LAURA = "U-401"


def _wells_from_visual(env) -> list[str]:
    d = env.visual.data if env.visual else None
    if isinstance(d, list):
        out = []
        for row in d:
            if isinstance(row, dict):
                w = row.get("well") or row.get("Well")
                if w:
                    out.append(w)
        return out
    if isinstance(d, dict):
        for key in ("not_producing", "rows", "top", "pins", "spills"):
            if key in d and isinstance(d[key], list):
                return _wells_from_visual(type("E", (), {"visual": type("V", (), {"data": d[key]})()})())
    return []


def _claim_text(env) -> str:
    parts = [env.summary or ""]
    for c in env.claims or []:
        parts.append(c.text or "")
    return "\n".join(parts).lower()


CheckFn = Callable[[Any], tuple[bool, str]]


PHASE1: list[dict[str, Any]] = [
    {
        "id": "T01",
        "user": MICHAEL,
        "q": "Is WELL-0001 producing oil right now? When was it last inspected, and by whom? Show me its status card.",
        "expect_visual": "status_card",
        "checks": [
            ("not_producing", lambda e: (e.visual.data.get("producing") is False, f"producing={e.visual.data.get('producing')}")),
            ("insp", lambda e: ("ins-0001-0203" in _claim_text(e) or e.visual.data.get("inspection_id") == "INS-0001-0203", "missing INS-0001-0203")),
            ("delta", lambda e: (abs(float(e.visual.data.get("delta_c") or 0) - 3.2) < 0.05, f"delta={e.visual.data.get('delta_c')}")),
        ],
    },
    {
        "id": "T02",
        "user": MICHAEL,
        "q": "Which wells in Northeast Block 8 are not producing oil right now, and why? Show them in a table.",
        "expect_visual": "table",
        "checks": [
            (
                "four_wells",
                lambda e: (
                    set(_wells_from_visual(e)) == {"WELL-0164", "WELL-0170", "WELL-0172", "WELL-0175"},
                    f"got={_wells_from_visual(e)}",
                ),
            ),
        ],
    },
    {
        "id": "T03",
        "user": MICHAEL,
        "q": "Show a line chart of WELL-0001's wellhead temperature against air temperature for the last 13 weeks, and mark when it was not producing oil.",
        "expect_visual": "line",
        "checks": [
            (
                "13_points",
                lambda e: (
                    len(e.visual.data) == 13
                    if isinstance(e.visual.data, list)
                    else len((e.visual.data or {}).get("points") or (e.visual.data or {}).get("series") or []) == 13
                    or len(e.visual.data or []) == 13,
                    f"n={len(e.visual.data) if isinstance(e.visual.data, list) else e.visual.data}",
                ),
            ),
        ],
    },
    {
        "id": "T04",
        "user": MICHAEL,
        "q": "How many oil spills has WELL-0001 had in the last four years, and how much oil in total? List them in a table.",
        "expect_visual": "table",
        "checks": [
            (
                "6_spills_15_1",
                lambda e: (
                    e.claims
                    and e.claims[0].value
                    and int(e.claims[0].value.get("count") if isinstance(e.claims[0].value, dict) else -1) == 6
                    and abs(float(e.claims[0].value.get("bbl") if isinstance(e.claims[0].value, dict) else -1) - 15.1) < 0.05,
                    f"value={e.claims[0].value if e.claims else None}",
                ),
            ),
        ],
    },
    {
        "id": "T05",
        "user": MICHAEL,
        "q": "How many days was WELL-0001 down in 2025?",
        "expect_visual": None,
        "checks": [
            ("21_days", lambda e: (e.claims and e.claims[0].value == 21, f"value={e.claims[0].value if e.claims else None}")),
        ],
    },
    {
        "id": "T06",
        "user": MICHAEL,
        "q": "Which three wells in Northeast Block 7 had the most downtime in the last four months? Show a bar chart.",
        "expect_visual": "bar",
        "checks": [
            (
                "ranking",
                lambda e: (
                    [r.get("well") for r in (e.visual.data or [])] == ["WELL-0121", "WELL-0138", "WELL-0107"]
                    and [r.get("days") for r in (e.visual.data or [])] == [49, 42, 42],
                    f"got={e.visual.data}",
                ),
            ),
        ],
    },
    {
        "id": "T07",
        "user": MICHAEL,
        "q": "Show on a map every well in Northeast Block 8 with a real spill in the last 90 days.",
        "expect_visual": "map",
        "checks": [
            (
                "four_pins",
                lambda e: (
                    len(e.visual.data or []) == 4
                    and set(_wells_from_visual(e)) == {"WELL-0151", "WELL-0165", "WELL-0175", "WELL-0186"},
                    f"got={_wells_from_visual(e)}",
                ),
            ),
        ],
    },
    {
        "id": "T08",
        "user": MICHAEL,
        "q": "Show me a heatmap of 2026 spills by geographic area and month.",
        "expect_visual": "heatmap",
        "checks": [
            (
                "totals",
                lambda e: (
                    {
                        r["area"]: r["total"]
                        for r in (e.visual.data or {}).get("rows", [])
                    }
                    == {
                        "Northeast Block 7": 37,
                        "Northeast Block 8": 26,
                        "Southwest Block 23": 35,
                        "Southwest Block 24": 43,
                    },
                    f"got={[(r['area'], r['total']) for r in (e.visual.data or {}).get('rows', [])]}",
                ),
            ),
        ],
    },
    {
        "id": "T09",
        "user": MICHAEL,
        "q": "Which rules has WELL-0001 broken in the last 12 months, and what is still open?",
        "expect_visual": "table",
        "checks": [
            ("sr01", lambda e: ("sr-01" in _claim_text(e) and "41" in _claim_text(e), "missing SR-01/41h")),
            ("sr02", lambda e: ("sr-02" in _claim_text(e) and "7" in _claim_text(e), "missing SR-02/~7h")),
            ("sr03", lambda e: ("sr-03" in _claim_text(e), "missing SR-03")),
            ("rc04", lambda e: ("rc-04" in _claim_text(e), "missing RC-04")),
            ("fine", lambda e: ("5000" in _claim_text(e), "missing fine 5000")),
            ("not_breach_actions", lambda e: ("not a breach" in _claim_text(e) or "open action" in _claim_text(e), "missing open-action framing")),
        ],
    },
    {
        "id": "T10",
        "user": MICHAEL,
        "q": "In Southwest Block 24, which spills in the last 90 days were not contained within the SOP time limit?",
        "expect_visual": "table",
        "checks": [
            (
                "two_wells",
                lambda e: (
                    set(_wells_from_visual(e)) == {"WELL-0082", "WELL-0100"},
                    f"got={_wells_from_visual(e)}",
                ),
            ),
        ],
    },
]
