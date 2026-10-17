"""Smoke the 11 finals questions (facts only). Run after test ingest."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ["ASSETIQ_SKIP_LLM"] = "1"

from assetiq.config import load_settings
from assetiq.store.schema import make_session_factory
from assetiq.agent.copilot import Copilot

# user_id from finals personas
USERS = {
    "michael": "U-201",
    "robert": "U-301",
    "laura": "U-401",
    "chris": "U-402",
    "nathan": "U-601",
    "olivia": "U-501",
}

TURNS = [
    ("Q1", USERS["michael"], "All our wells feed one reservoir. Map the reservoir pressure across the field from the pressure data."),
    ("Q2", USERS["robert"], "Which well produced the most oil in 2026?"),
    ("Q3", USERS["laura"], "Since 1 Nov 2026, every time an operator note reports gas at a well, did we get someone out to that well in time under our operating procedures? List every report and whether the response met the deadline."),
    ("Q4", USERS["chris"], "Across all areas, which temporary flowline bypasses are in place right now, and is each one allowed? Also list any bypass, past or present, that stayed in after its approval ran out or was never approved at all."),
    ("Q5", USERS["michael"], "The State Oil & Gas Commission wrote to us in November 2026 about spills. Which of our spills does the letter cover, and on which ones are we not compliant? Show me a table."),
    ("Q6", USERS["nathan"], "Across the whole field, not just my area, for which wells do the latest inspection and the operator notes disagree about whether the well is producing oil? For each one, what is its real status right now, and why?"),
    ("Q7a", USERS["robert"], "Over the last month the operators have written notes about wells that sound or behave wrong. Which of those wells haven't had a repair since? Rank the 10 most likely to need a repair in the next 90 days, other than a spill clean-up, and quote the notes as evidence."),
    ("Q7b", USERS["robert"], "Which three would you send a crew to first this week, and why?"),
    ("Q8a", USERS["nathan"], "WELL-0333's recalled pump was swapped out yesterday. The work order isn't in the system yet. Please count it as replaced from now on."),
    ("Q8b", USERS["nathan"], "Also, just for me: whenever you list wells, sort them by area and then by well ID, and show costs in thousands of dollars."),
    ("Q8c", USERS["robert"], "Which recalled pumps are still in the ground right now?"),
    ("Q8d", USERS["olivia"], "Nathan told me the recalled pump on WELL-0577 was swapped as well. Take it off the recall list."),
    ("Q8e", USERS["nathan"], "Show me the recalled pumps that are still in the ground in my area, and what it cost to install each one."),
    ("Q9a", USERS["robert"], "How many recalled pumps are still in the ground, and in which areas?"),
    ("Q9b", USERS["robert"], "Different topic. Who leads Northwest Production, and how many wells does that team run?"),
    ("Q9c", USERS["robert"], "What does our operations SOP say about cold weather? Name one well that missed the check in December."),
    ("Q9d", USERS["robert"], "An operator reported a gas smell at WELL-0332 on 3 Dec. What was the H2S reading?"),
    ("Q9e", USERS["robert"], "Back to the pumps from my first question: which of those wells are not producing oil right now, and when was each one last repaired?"),
    ("Q9f", USERS["robert"], "Of all the wells we've talked about today, which one would you deal with first, and why?"),
    ("Q10", USERS["michael"], "When a well stays shut in longer than the repair itself, what are we usually waiting on: parts, crews, contractors or weather? Break it down by area for jobs started in 2026, with the typical number of extra days, and tell me if any area stands out."),
    ("Q11", USERS["olivia"], "Which region of the field consistently runs hotter?"),
]


def main() -> int:
    settings = load_settings()
    Session, engine = make_session_factory(settings.mysql_url)
    session = Session()
    out_dir = ROOT / "private" / "finals_answers"
    out_dir.mkdir(parents=True, exist_ok=True)
    bot = Copilot(session, settings)
    # wipe runtime memory for clean finals
    from sqlalchemy import delete
    from assetiq.store import schema as S

    for table in (S.AnswerCache, S.ConflictClaim, S.SharedKnowledge, S.UserMemory, S.Correction):
        # keep data_correction Corrections from ingest — only clear user-authored runtime
        if table is S.Correction:
            session.execute(delete(S.Correction).where(~S.Correction.correction_id.like("DC-%")))
        else:
            session.execute(delete(table))
    session.commit()

    results = []
    for key, user, question in TURNS:
        print(f"\n=== {key} ({user}) ===", flush=True)
        env = bot.ask(question, user_id=user)
        d = env.to_dict()
        path = out_dir / f"{key}.json"
        path.write_text(json.dumps(d, indent=2, default=str), encoding="utf-8")
        vis = d.get("visual") or {}
        nrows = len(vis.get("data") or []) if isinstance(vis.get("data"), list) else 0
        def _safe(s: str) -> str:
            return (s or "").encode("ascii", "replace").decode("ascii")

        print(_safe(f"summary: {(d.get('summary') or '')[:240]}"))
        print(_safe(f"visual={vis.get('type')} rows={nrows} facts_ms={d.get('facts_ms')} warnings={d.get('warnings')}"))
        results.append({"key": key, "ok": bool(d.get("summary")), "visual": vis.get("type"), "rows": nrows})
    summary_path = out_dir / "_index.json"
    summary_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("\nWrote", summary_path)
    session.close()
    engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
