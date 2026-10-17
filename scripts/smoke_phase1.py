"""Quick Phase 1 + Q12 smoke (ASSETIQ_SKIP_LLM=1)."""
from __future__ import annotations

import os

os.environ.setdefault("ASSETIQ_SKIP_LLM", "1")

from assetiq.agent.copilot import Copilot
from assetiq.cache import bump_state_version
from assetiq.config import load_settings
from assetiq.store.schema import make_session_factory


def rows_of(env):
    d = env.visual.data if env.visual else None
    if isinstance(d, dict):
        for k in ("not_producing", "rows", "top", "pins", "spills", "points"):
            if k in d and isinstance(d[k], list):
                return d[k]
        return d
    return d


def main():
    s = load_settings()
    Session, _ = make_session_factory(s.mysql_url)
    with Session() as sess:
        bump_state_version(sess)
        bot = Copilot(sess, s)

        env = bot.answer_facts(
            "Which wells in Northeast Block 8 are not producing oil right now, and why? Show them in a table.",
            "U-201",
        )
        print(
            "T2",
            [
                (r.get("well"), r.get("wellhead_above_air"), (r.get("reason") or "")[:70])
                for r in rows_of(env) or []
            ],
        )

        env = bot.answer_facts(
            "Show a line chart of WELL-0001's wellhead temperature against air temperature "
            "for the last 13 weeks, and mark when it was not producing oil.",
            "U-201",
        )
        pts = rows_of(env) or env.visual.data
        n = len(pts) if isinstance(pts, list) else (pts.get("points") if isinstance(pts, dict) else pts)
        print("T3 type", env.visual.type, "n", n if not isinstance(n, list) else len(n), "data_keys", list(env.visual.data) if isinstance(env.visual.data, dict) else type(env.visual.data))

        env = bot.answer_facts(
            "How many oil spills has WELL-0001 had in the last four years, and how much oil in total? List them in a table.",
            "U-201",
        )
        print("T4", env.claims[0].text if env.claims else env.summary)

        env = bot.answer_facts("How many days was WELL-0001 down in 2025?", "U-201")
        print(
            "T5",
            env.claims[0].text if env.claims else env.summary,
            env.claims[0].value if env.claims else None,
        )

        env = bot.answer_facts(
            "Which three wells in Northeast Block 7 had the most downtime in the last four months? Show a bar chart.",
            "U-201",
        )
        print("T6", rows_of(env) or env.visual.data)

        env = bot.answer_facts(
            "Show on a map every well in Northeast Block 8 with a real spill in the last 90 days.",
            "U-201",
        )
        pins = rows_of(env) or env.visual.data
        print("T7 pins", len(pins) if isinstance(pins, list) else pins)
        if isinstance(pins, list):
            print(" ", [(p.get("well"), p.get("date"), p.get("bbl")) for p in pins])

        env = bot.answer_facts(
            "Show me a heatmap of 2026 spills by geographic area and month.",
            "U-201",
        )
        print("T8", [(r["area"], r["total"]) for r in env.visual.data["rows"]])

        env = bot.answer_facts(
            "Which rules has WELL-0001 broken in the last 12 months, and what is still open?",
            "U-201",
        )
        print("T9", (env.summary or "")[:220])
        for c in (env.claims or [])[:8]:
            print(" ", c.claim_type, (c.text or "")[:110])

        env = bot.answer_facts(
            "In Southwest Block 24, which spills in the last 90 days were not contained within the SOP time limit?",
            "U-201",
        )
        print("T10", rows_of(env) or env.visual.data)

        # Q12
        q12 = (
            "The 15 October reading for WELL-0164 is wrong. The handheld thermal gun "
            "used in that inspection was faulty; the field crew re-measured the wellhead at 41.0°C."
        )
        env = bot.answer_facts(q12, "U-201")
        print("Q12", env.summary)
        print("Q12 card", env.visual.data if env.visual else None)

        env = bot.answer_facts(
            "Is WELL-0164 producing oil right now? Show the calculation, the original reading, "
            "the corrected reading, and any conflicting evidence.",
            "U-201",
        )
        print("Q12b", (env.summary or "")[:280])
        print("Q12b st", env.visual.data if env.visual else None)

        env = bot.answer_facts(
            "Which wells in Northeast Block 8 are not producing oil right now, and why? Show them in a table.",
            "U-201",
        )
        print("T2-after", [r.get("well") for r in rows_of(env) or []])

        # Q13 spill volume
        q13 = (
            "The AI estimated the 24 September spill at WELL-0151 as 4.5 barrels. "
            "The field crew measured 5.4 barrels. Correct the volume and reassess the compliance status."
        )
        env = bot.answer_facts(q13, "U-201")
        print("Q13", env.summary)
        for c in env.claims or []:
            print(" ", c.text[:120])


if __name__ == "__main__":
    main()
