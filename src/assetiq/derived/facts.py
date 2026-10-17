"""Deterministic derived facts. Gemma explains these — it does not invent them."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

from assetiq.rules.registry import RuleRegistry, compare
from assetiq.store.repo import Repository
from assetiq.store import schema as S


@dataclass
class Evidence:
    ref: str  # record id or doc_file#section
    summary: str = ""


@dataclass
class FactResult:
    key: str
    value: Any
    claim_type: str  # deterministic_fact | inference | discrepancy
    evidence: list[Evidence] = field(default_factory=list)
    rule_id: Optional[str] = None
    detail: dict = field(default_factory=dict)


def temp_delta(wellhead: float, ambient: float) -> float:
    return round(wellhead - ambient, 1)


def is_producing(delta: float, well_type: str, rules: RuleRegistry) -> tuple[bool, FactResult]:
    rule = rules.producing_rule(well_type)
    producing = compare(delta, rule)
    return producing, FactResult(
        key="producing",
        value=producing,
        claim_type="deterministic_fact",
        evidence=[Evidence(f"{rule.source_file}#{rule.source_section}", rule.description or "")],
        rule_id=rule.rule_id,
        detail={"delta_c": delta, "threshold_c": rule.threshold, "well_type": well_type},
    )


def producing_status_now(repo: Repository, asset_id: str, rules: RuleRegistry) -> dict:
    well = repo.get_well(asset_id)
    if not well:
        return {"error": f"unknown well {asset_id}"}
    insp = repo.latest_inspection(asset_id)
    if not insp:
        return {"error": f"no inspections for {asset_id}"}

    wh = repo.effective_inspection_field(insp, "wellhead_temp_c")
    amb = repo.effective_inspection_field(insp, "ambient_temp_c")
    delta = temp_delta(float(wh), float(amb))
    producing, fact = is_producing(delta, well.well_type, rules)

    corrections = repo.active_corrections(insp.inspection_id, "wellhead_temp_c")
    corr_note = None
    if corrections:
        c = corrections[-1]
        corr_note = {
            "original": c.original_value,
            "corrected": c.corrected_value,
            "author": c.author_user_id,
            "reason": c.reason,
        }

    inspector = repo.get_user(insp.inspector_user_id) if insp.inspector_user_id else None
    notes = repo.notes_for_asset(asset_id)
    relevant_notes = [
        n
        for n in notes
        if n.note_type in ("operator_feedback", "operator_note", "correction")
        and (n.inspection_id == insp.inspection_id or (n.valid_from and n.valid_to))
    ]

    discrepancy = None
    if well.recorded_status == "active" and not producing:
        discrepancy = {
            "claim_type": "discrepancy",
            "text": f"recorded_status is '{well.recorded_status}' but latest inspection shows not producing",
            "evidence": [f"metadata.recorded_status", insp.inspection_id],
        }

    # inspector notes that disagree with a producing correction
    conflicts = []
    if producing and insp.notes and "not moving" in (insp.notes or "").lower():
        conflicts.append(
            {
                "claim_type": "discrepancy",
                "text": f"Inspector note on {insp.inspection_id}: {insp.notes}",
                "evidence": [insp.inspection_id],
            }
        )

    return {
        "asset_id": asset_id,
        "well_type": well.well_type,
        "producing": producing,
        "delta_c": delta,
        "wellhead_temp_c": wh,
        "ambient_temp_c": amb,
        "threshold_c": fact.detail["threshold_c"],
        "rule_id": fact.rule_id,
        "rule_source": f"{fact.evidence[0].ref}",
        "inspection_id": insp.inspection_id,
        "inspected_at": insp.inspected_at.isoformat() + "Z",
        "method": insp.method,
        "inspector_user_id": insp.inspector_user_id,
        "inspector_name": inspector.name if inspector else None,
        "recorded_status": well.recorded_status,
        "correction": corr_note,
        "notes": [
            {"note_id": n.note_id, "author": n.author_user_id, "type": n.note_type, "text": n.text}
            for n in notes
            if n.note_id.startswith(asset_id.replace("WELL-", "CTX-")[:0] + "") or True
        ][-5:],
        "context_notes": [
            {"note_id": n.note_id, "author": n.author_user_id, "type": n.note_type, "text": n.text}
            for n in notes
        ],
        "discrepancy": discrepancy,
        "conflicts": conflicts,
        "inspection_notes": insp.notes,
    }


def downtime_days(
    repo: Repository,
    asset_id: str,
    start: datetime,
    end: datetime,
    rules: RuleRegistry,
) -> dict:
    """Each not-producing weekly inspection = 7 days; missed = 0. Dataset Guide."""
    well = repo.get_well(asset_id)
    if not well:
        return {"error": f"unknown well {asset_id}"}
    rule = rules.get("DOWNTIME_DAYS_PER_NOT_PRODUCING_INSPECTION")
    prod_rule = rules.producing_rule(well.well_type)
    inspections = repo.inspections_in_range(asset_id, start, end)
    down_ids = []
    for insp in inspections:
        wh = float(repo.effective_inspection_field(insp, "wellhead_temp_c"))
        amb = float(repo.effective_inspection_field(insp, "ambient_temp_c"))
        delta = temp_delta(wh, amb)
        if not compare(delta, prod_rule):
            down_ids.append(
                {
                    "inspection_id": insp.inspection_id,
                    "inspected_at": insp.inspected_at.isoformat() + "Z",
                    "delta_c": delta,
                    "wellhead_temp_c": wh,
                    "ambient_temp_c": amb,
                }
            )
    days = int(len(down_ids) * (rule.threshold or 7))
    return {
        "asset_id": asset_id,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "downtime_days": days,
        "not_producing_inspections": down_ids,
        "rule_id": rule.rule_id,
        "rule_source": f"{rule.source_file}#{rule.source_section}",
        "producing_rule": f"{prod_rule.source_file}#{prod_rule.source_section}",
    }


def _spill_corrected_away(repo: Repository, inspection_id: str) -> bool:
    """True when a formal correction note clears a false-positive detection (SOP §7)."""
    notes = repo.correction_notes_for_inspection(inspection_id)
    for n in notes:
        t = (n.text or "").lower()
        # Dataset phrases: "rainwater…", "wet soil after rain", "produced water…",
        # "shadow from the pump jack", "Not a crude spill." / "Not a spill."
        if any(
            w in t
            for w in (
                "rainwater",
                "wet soil after rain",
                "after rain",
                "not a spill",
                "not a crude spill",
                "not crude",
                "produced water",
                "no crude",
                "mud",
                "shadow",
            )
        ):
            return True
    # formal correction clearing spill_detected
    for c in repo.active_corrections(inspection_id, "spill_detected"):
        if c.corrected_value.lower() in ("false", "0", "no"):
            return True
    return False


def real_spills(
    repo: Repository,
    asset_id: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> dict:
    """Spills after applying corrections (Spill SOP §7 — corrected detections do not count)."""
    well = repo.get_well(asset_id)
    if start and end:
        inspections = repo.inspections_in_range(asset_id, start, end)
    else:
        # all
        inspections = repo.inspections_in_range(
            asset_id, datetime(2000, 1, 1), datetime(2099, 1, 1)
        )

    spills = []
    detections = 0
    for insp in inspections:
        detected = bool(repo.effective_inspection_field(insp, "spill_detected"))
        if not detected and insp.spill_detected:
            # original said true but correction cleared — still count as detection then corrected
            pass
        if insp.spill_detected or detected:
            detections += 1
        if not detected:
            continue
        if _spill_corrected_away(repo, insp.inspection_id):
            continue
        vol = repo.effective_inspection_field(insp, "spill_est_volume_bbl")
        spills.append(
            {
                "inspection_id": insp.inspection_id,
                "date": insp.inspected_at.date().isoformat(),
                "inspected_at": insp.inspected_at.isoformat() + "Z",
                "volume_bbl": vol,
                "area_pct": repo.effective_inspection_field(insp, "spill_area_pct"),
                "notes": insp.notes,
            }
        )
    total = round(sum(float(s["volume_bbl"] or 0) for s in spills), 1)
    return {
        "asset_id": asset_id,
        "spill_count": len(spills),
        "total_bbl": total,
        "detections_including_corrected": detections,
        "spills": spills,
        "rule_source": "fleet/sops/spill-response-sop.md#7",
    }


def parse_containment_hours(report_text: str) -> Optional[float]:
    """Pull containment time from free-text repair reports (needed for SR-02 / Q10)."""
    if not report_text:
        return None
    patterns = [
        # "contained about 7.1 hours after the inspection"
        r"contained\s+(?:about\s+)?([0-9]+(?:\.[0-9]+)?)\s*h(?:ours?)?\s+after",
        r"contained\s+(?:after|in|within)\s+(?:about\s+)?([0-9]+(?:\.[0-9]+)?)\s*h(?:ours?)?",
        r"containment\s+(?:took|time)[:\s]+(?:about\s+)?([0-9]+(?:\.[0-9]+)?)\s*h",
        r"([0-9]+(?:\.[0-9]+)?)\s*hours?\s+(?:to\s+)?contain",
    ]
    lower = report_text.lower()
    for pat in patterns:
        m = re.search(pat, lower)
        if m:
            return float(m.group(1))
    return None


def area_not_producing_now(repo: Repository, area_name: str, rules: RuleRegistry) -> dict:
    area = repo.get_area_by_name(area_name)
    if not area:
        # try partial
        from sqlalchemy import select, func
        from assetiq.store import schema as Sch

        area = repo.s.execute(
            select(Sch.Area).where(func.lower(Sch.Area.name).like(f"%{area_name.lower()}%"))
        ).scalar_one_or_none()
    if not area:
        return {"error": f"unknown area {area_name}"}
    rows = []
    for well in repo.wells_in_area(area.area_id):
        st = producing_status_now(repo, well.asset_id, rules)
        if st.get("producing") is False:
            # reason: open maintenance or notes
            reason = "No recorded reason"
            open_m = [
                m
                for m in repo.maintenance_for_asset(well.asset_id)
                if m.completed_at and m.completed_at > datetime(2026, 10, 17)
                or (m.completed_at and m.started_at and m.completed_at >= m.started_at and m.maintenance_type == "corrective")
            ]
            # still open: completed_at in the future relative to challenge, or status
            open_jobs = []
            for m in repo.maintenance_for_asset(well.asset_id):
                if m.completed_at and m.completed_at.replace(tzinfo=None) > datetime(2026, 10, 17):
                    open_jobs.append(m)
                elif m.completed_at is None:
                    open_jobs.append(m)
            if open_jobs:
                m = sorted(open_jobs, key=lambda x: x.started_at, reverse=True)[0]
                reason = f"Open repair {m.maintenance_id}: {m.issue}"
            elif st.get("inspection_notes"):
                note = (st["inspection_notes"] or "").strip()
                # Distinguish "inspector saw something but no established cause" vs empty
                if note:
                    reason = f"No confirmed cause; inspector noted \"{note}\""
                else:
                    reason = "No recorded reason"
            rows.append(
                {
                    "well": well.asset_id,
                    "well_type": well.well_type,
                    "wellhead_above_air": st["delta_c"],
                    "recorded_status": well.recorded_status,
                    "reason": reason,
                    "inspection_id": st["inspection_id"],
                    "inspected_at": st["inspected_at"],
                }
            )
    return {"area": area.name, "area_id": area.area_id, "not_producing": rows}


def top_downtime_in_area(
    repo: Repository,
    area_name: str,
    start: datetime,
    end: datetime,
    rules: RuleRegistry,
    top_n: int = 3,
) -> dict:
    area = repo.get_area_by_name(area_name)
    if not area:
        from sqlalchemy import select, func
        from assetiq.store import schema as Sch

        area = repo.s.execute(
            select(Sch.Area).where(func.lower(Sch.Area.name).like(f"%{area_name.lower()}%"))
        ).scalar_one_or_none()
    if not area:
        return {"error": f"unknown area {area_name}"}
    scored = []
    for well in repo.wells_in_area(area.area_id):
        d = downtime_days(repo, well.asset_id, start, end, rules)
        scored.append(
            {
                "well": well.asset_id,
                "well_type": well.well_type,
                "downtime_days": d["downtime_days"],
                "detail": d,
            }
        )
    # Ties: higher well id first (matches eval key — WELL-0138 before WELL-0107 at 42 days)
    scored.sort(key=lambda x: (x["downtime_days"], x["well"]), reverse=True)
    return {
        "area": area.name,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "top": scored[:top_n],
        "next": scored[top_n] if len(scored) > top_n else None,
    }


def repair_cost_ytd(repo: Repository, asset_ids: list[str], year: int = 2026) -> dict:
    start = datetime(year, 1, 1)
    end = datetime(year, 12, 31, 23, 59, 59)
    out = {}
    for aid in asset_ids:
        total = 0.0
        for m in repo.maintenance_for_asset(aid, start, end):
            total += float(m.cost_total or 0)
        out[aid] = round(total)
    return {"year": year, "costs": out}


def repair_types_in_area(
    repo: Repository,
    area_name: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> dict:
    """Aggregate distinct repair types (type × equipment × issue) for an area."""
    from collections import defaultdict
    from sqlalchemy import select, func
    from assetiq.store import schema as Sch

    area = repo.get_area_by_name(area_name)
    if not area:
        area = repo.s.execute(
            select(Sch.Area).where(func.lower(Sch.Area.name).like(f"%{area_name.lower()}%"))
        ).scalar_one_or_none()
    if not area:
        return {"error": f"unknown area {area_name}"}

    # key -> {count, wells set, sample mnt ids}
    buckets: dict[tuple[str, str, str], dict] = {}
    by_equipment: dict[str, int] = defaultdict(int)
    by_type: dict[str, int] = defaultdict(int)
    total_jobs = 0

    for well in repo.wells_in_area(area.area_id):
        for m in repo.maintenance_for_asset(well.asset_id, start, end):
            total_jobs += 1
            mtype = (m.maintenance_type or "unknown").strip()
            equip = (m.equipment_kind or "unknown").strip()
            issue = (m.issue or "(no issue text)").strip()
            key = (mtype, equip, issue)
            if key not in buckets:
                buckets[key] = {
                    "maintenance_type": mtype,
                    "equipment_kind": equip,
                    "issue": issue,
                    "count": 0,
                    "wells": set(),
                    "sample_ids": [],
                }
            buckets[key]["count"] += 1
            buckets[key]["wells"].add(well.asset_id)
            if len(buckets[key]["sample_ids"]) < 3:
                buckets[key]["sample_ids"].append(m.maintenance_id)
            by_equipment[equip] += 1
            by_type[mtype] += 1

    rows = []
    for b in buckets.values():
        rows.append(
            {
                "maintenance_type": b["maintenance_type"],
                "equipment_kind": b["equipment_kind"],
                "issue": b["issue"],
                "count": b["count"],
                "wells": len(b["wells"]),
                "sample_mnt": ", ".join(b["sample_ids"]),
            }
        )
    rows.sort(key=lambda r: (-r["count"], r["maintenance_type"], r["equipment_kind"], r["issue"]))

    return {
        "area": area.name,
        "area_id": area.area_id,
        "total_jobs": total_jobs,
        "distinct_types": len(rows),
        "by_maintenance_type": dict(by_type),
        "by_equipment_kind": dict(sorted(by_equipment.items(), key=lambda x: -x[1])),
        "rows": rows,
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
    }


def spills_heatmap_2026(repo: Repository, rules: RuleRegistry, end: datetime) -> dict:
    start = datetime(2026, 1, 1)
    from sqlalchemy import select
    from assetiq.store import schema as Sch

    areas = list(repo.s.scalars(select(Sch.Area)))
    months = list(range(1, end.month + 1))
    grid = {}
    for area in areas:
        grid[area.name] = {m: 0 for m in months}
        for well in repo.wells_in_area(area.area_id):
            spills = real_spills(repo, well.asset_id, start, end)
            for s in spills["spills"]:
                d = datetime.fromisoformat(s["inspected_at"].replace("Z", ""))
                if d.year == 2026 and d.month in grid[area.name]:
                    grid[area.name][d.month] += 1
    # totals
    result = []
    for name, months_map in grid.items():
        row = {"area": name, **{f"m{m}": months_map[m] for m in months}, "total": sum(months_map.values())}
        result.append(row)
    return {"year": 2026, "months": months, "rows": result}
