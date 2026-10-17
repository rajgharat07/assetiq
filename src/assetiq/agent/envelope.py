"""Typed Answer Envelope — grounding is structural, not a prompt hope."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Optional

ClaimType = Literal["deterministic_fact", "inference", "discrepancy"]
VisualType = Literal["status_card", "table", "line", "bar", "map", "heatmap", "none", "pie"]


@dataclass
class Claim:
    text: str
    claim_type: ClaimType
    value: Any = None
    evidence: list[str] = field(default_factory=list)
    rule_id: Optional[str] = None


@dataclass
class VisualSpec:
    type: VisualType
    title: str = ""
    data: Any = None
    columns: list[str] = field(default_factory=list)


@dataclass
class AnswerEnvelope:
    question: str
    summary: str
    claims: list[Claim] = field(default_factory=list)
    visual: VisualSpec = field(default_factory=lambda: VisualSpec(type="none"))
    citations: list[str] = field(default_factory=list)
    user_id: Optional[str] = None
    warnings: list[str] = field(default_factory=list)
    model: Optional[str] = None
    trace: list[str] = field(default_factory=list)
    facts_ms: Optional[int] = None
    cache_hit: bool = False

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "summary": self.summary,
            "claims": [asdict(c) for c in self.claims],
            "visual": asdict(self.visual),
            "citations": self.citations,
            "user_id": self.user_id,
            "warnings": self.warnings,
            "model": self.model,
            "trace": list(self.trace),
            "facts_ms": self.facts_ms,
            "cache_hit": self.cache_hit,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AnswerEnvelope":
        claims = [
            Claim(
                text=c.get("text", ""),
                claim_type=c.get("claim_type", "deterministic_fact"),
                value=c.get("value"),
                evidence=list(c.get("evidence") or []),
                rule_id=c.get("rule_id"),
            )
            for c in (data.get("claims") or [])
        ]
        v = data.get("visual") or {}
        visual = VisualSpec(
            type=v.get("type") or "none",
            title=v.get("title") or "",
            data=v.get("data"),
            columns=list(v.get("columns") or []),
        )
        return cls(
            question=data.get("question", ""),
            summary=data.get("summary", ""),
            claims=claims,
            visual=visual,
            citations=list(data.get("citations") or []),
            user_id=data.get("user_id"),
            warnings=list(data.get("warnings") or []),
            model=data.get("model"),
            trace=list(data.get("trace") or []),
            facts_ms=data.get("facts_ms"),
            cache_hit=bool(data.get("cache_hit")),
        )


def pick_visual(question: str, default: VisualType) -> VisualType:
    q = question.lower()
    if "heatmap" in q:
        return "heatmap"
    if "map" in q:
        return "map"
    if "line chart" in q or "line graph" in q:
        return "line"
    if "bar chart" in q or "bar graph" in q:
        return "bar"
    if "pie" in q:
        return "pie"
    if "table" in q:
        return "table"
    if "card" in q or "status" in q:
        return "status_card"
    return default
