"""Hybrid doc retrieval: exact section + keyword over manuals/SOPs/reports.

Vector search is optional later; exact IDs and report_file links are the winning path
(SR-02 containment times live only in free-text reports).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from assetiq.store import schema as S


def _score(text: str, terms: list[str]) -> int:
    lower = text.lower()
    return sum(lower.count(t.lower()) for t in terms if t)


def search_reports(session: Session, query: str, asset_id: Optional[str] = None, limit: int = 5) -> list[dict]:
    terms = [t for t in re.split(r"\W+", query) if len(t) > 2]
    q = select(S.ReportDoc)
    if asset_id:
        q = q.where(S.ReportDoc.asset_id == asset_id)
    rows = list(session.scalars(q))
    scored = []
    for r in rows:
        s = _score(r.text or "", terms)
        if s > 0:
            scored.append((s, r))
    scored.sort(key=lambda x: -x[0])
    out = []
    for s, r in scored[:limit]:
        out.append(
            {
                "asset_id": r.asset_id,
                "maintenance_id": r.maintenance_id,
                "report_file": r.report_file,
                "score": s,
                "excerpt": (r.text or "")[:800],
            }
        )
    return out


def load_manual_section(data_root: Path, relative: str, section_hint: str = "") -> dict:
    """Exact file + optional section header lookup — never invent thresholds."""
    path = data_root / relative
    if not path.exists():
        # try fleet/... under sample-data
        path = data_root / relative.replace("fleet/", "fleet/")
    if not path.exists():
        return {"error": f"missing {relative}"}
    text = path.read_text(encoding="utf-8")
    if not section_hint:
        return {"file": relative, "text": text[:2000]}
    # grab section starting at hint
    lines = text.splitlines()
    start = 0
    for i, line in enumerate(lines):
        if section_hint in line:
            start = i
            break
    chunk = "\n".join(lines[start : start + 40])
    return {"file": relative, "section": section_hint, "text": chunk}


def keyword_search_fleet_docs(data_root: Path, query: str, limit: int = 5) -> list[dict]:
    terms = [t for t in re.split(r"\W+", query) if len(t) > 2]
    hits = []
    fleet = data_root / "fleet"
    if not fleet.exists():
        return hits
    for path in list(fleet.rglob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        s = _score(text, terms)
        if s > 0:
            rel = str(path.relative_to(data_root)).replace("\\", "/")
            hits.append({"file": rel, "score": s, "excerpt": text[:600]})
    hits.sort(key=lambda x: -x["score"])
    return hits[:limit]
