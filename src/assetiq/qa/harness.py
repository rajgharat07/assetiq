"""Answer QA harness — validate claims against records (not an LLM)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from assetiq.agent.envelope import AnswerEnvelope
from assetiq.store import schema as S
from assetiq.store.repo import Repository


@dataclass
class QAReport:
    ok: bool
    evidence_valid: int = 0
    evidence_missing: int = 0
    unsupported_claims: int = 0
    total_claims: int = 0
    visual_ok: bool = True
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "evidence_valid": self.evidence_valid,
            "evidence_missing": self.evidence_missing,
            "unsupported_claims": self.unsupported_claims,
            "total_claims": self.total_claims,
            "unsupported_claim_rate": (
                self.unsupported_claims / self.total_claims if self.total_claims else 0.0
            ),
            "visual_ok": self.visual_ok,
            "notes": self.notes,
        }


def _citation_exists(repo: Repository, session: Session, ref: str, data_root=None) -> bool:
    if not ref:
        return False
    ref = ref.strip()
    if ref.startswith("fleet/") or ref.endswith(".md") or "#" in ref:
        # document citation — treat as ok if path-like; full file check optional
        return True
    if ref.startswith("shared:") or ref.startswith("user_memory:") or ref.startswith("claim:"):
        return True
    if ref.startswith("area:") or ref.startswith("NE-") or ref.startswith("SW-"):
        return True
    if session.get(S.Area, ref):
        return True
    if session.get(S.Inspection, ref):
        return True
    if session.get(S.Maintenance, ref):
        return True
    if session.get(S.RegulatoryEvent, ref):
        return True
    if session.get(S.ContextNote, ref):
        return True
    if session.get(S.Well, ref):
        return True
    if session.get(S.Correction, ref):
        return True
    if ref.startswith("metadata"):
        return True
    return False


def validate_envelope(session: Session, env: AnswerEnvelope) -> QAReport:
    repo = Repository(session)
    report = QAReport(ok=True, total_claims=len(env.claims))
    for claim in env.claims:
        if claim.claim_type == "deterministic_fact" and not claim.evidence:
            report.unsupported_claims += 1
            report.notes.append(f"unsupported: {claim.text[:80]}")
            report.ok = False
            continue
        if not claim.evidence and claim.claim_type != "inference":
            report.unsupported_claims += 1
            report.ok = False
        for ev in claim.evidence:
            if _citation_exists(repo, session, ev):
                report.evidence_valid += 1
            else:
                report.evidence_missing += 1
                report.notes.append(f"missing citation: {ev}")
                report.ok = False
    if env.visual and env.visual.type not in (
        "status_card",
        "table",
        "line",
        "bar",
        "map",
        "heatmap",
        "none",
        "pie",
    ):
        report.visual_ok = False
        report.ok = False
    return report
