"""Idempotent ingest. dataset_tag lets the ~4pm test folder load alongside sample."""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from assetiq.store import schema as S


def _parse_dt(val: Any) -> Optional[datetime]:
    if val is None or val == "":
        return None
    if isinstance(val, datetime):
        return val
    s = str(val).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s).replace(tzinfo=None)
    except ValueError:
        return None


def _parse_date(val: Any) -> Optional[date]:
    if val is None or val == "":
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    try:
        return date.fromisoformat(str(val)[:10])
    except ValueError:
        return None


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _upsert(session: Session, model, pk_value, defaults: dict):
    obj = session.get(model, pk_value)
    if obj is None:
        obj = model(**{list(defaults.keys())[0] if False else next(iter([c.key for c in model.__table__.columns if c.primary_key][0:1])): pk_value})
        # simpler:
        pk_name = [c.key for c in model.__table__.columns if c.primary_key][0]
        obj = model(**{pk_name: pk_value})
        session.add(obj)
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


def ingest_fleet(session: Session, data_root: Path, dataset_tag: str = "sample") -> dict:
    fleet = data_root / "fleet"
    stats = {"areas": 0, "teams": 0, "users": 0}

    areas_path = fleet / "areas.json"
    if areas_path.exists():
        payload = json.loads(areas_path.read_text(encoding="utf-8"))
        for a in payload.get("areas", []):
            center = a.get("center") or {}
            obj = session.get(S.Area, a["area_id"])
            if obj is None:
                obj = S.Area(area_id=a["area_id"])
                session.add(obj)
            obj.name = a.get("name", a["area_id"])
            obj.team_id = a.get("team_id", "")
            obj.lat = center.get("lat")
            obj.lon = center.get("lon")
            obj.dataset_tag = dataset_tag
            stats["areas"] += 1
        for t in payload.get("teams", []):
            obj = session.get(S.Team, t["team_id"])
            if obj is None:
                obj = S.Team(team_id=t["team_id"])
                session.add(obj)
            obj.name = t.get("name", t["team_id"])
            obj.lead_user_id = t.get("lead_user_id")
            obj.dataset_tag = dataset_tag
            stats["teams"] += 1

    users_path = fleet / "users.json"
    if users_path.exists():
        payload = json.loads(users_path.read_text(encoding="utf-8"))
        users = payload if isinstance(payload, list) else payload.get("users", [])
        for u in users:
            obj = session.get(S.User, u["user_id"])
            if obj is None:
                obj = S.User(user_id=u["user_id"])
                session.add(obj)
            obj.name = u.get("name", u["user_id"])
            obj.role = u.get("role", "")
            obj.team_id = u.get("team_id")
            obj.dataset_tag = dataset_tag
            stats["users"] += 1

    session.flush()
    return stats


def ingest_well(session: Session, well_dir: Path, dataset_tag: str = "sample") -> dict:
    asset_id = well_dir.name
    stats = {"inspections": 0, "maintenance": 0, "regs": 0, "notes": 0, "reports": 0}

    meta_path = well_dir / "metadata.json"
    if meta_path.exists():
        m = json.loads(meta_path.read_text(encoding="utf-8"))
        loc = m.get("location") or {}
        li = m.get("last_inspection") or {}
        obj = session.get(S.Well, asset_id)
        if obj is None:
            obj = S.Well(asset_id=asset_id)
            session.add(obj)
        obj.name = m.get("name", asset_id)
        obj.well_type = m.get("well_type", "T200")
        obj.area_id = m.get("area_id", "")
        obj.team_id = m.get("team_id", "")
        obj.in_charge_user_id = m.get("in_charge_user_id")
        obj.lat = loc.get("lat")
        obj.lon = loc.get("lon")
        obj.installed_on = m.get("installed_on")
        obj.recorded_status = m.get("recorded_status")
        obj.last_inspection_id = li.get("inspection_id")
        obj.last_inspected_at = _parse_dt(li.get("inspected_at"))
        obj.equipment_json = m.get("equipment")
        obj.dataset_tag = dataset_tag

    for row in _read_jsonl(well_dir / "inspections.jsonl"):
        iid = row["inspection_id"]
        obj = session.get(S.Inspection, iid)
        if obj is None:
            obj = S.Inspection(inspection_id=iid)
            session.add(obj)
        obj.asset_id = row.get("asset_id", asset_id)
        obj.inspected_at = _parse_dt(row.get("inspected_at")) or datetime(1970, 1, 1)
        obj.inspector_user_id = row.get("inspector_user_id")
        obj.method = row.get("method")
        obj.ambient_temp_c = row.get("ambient_temp_c")
        obj.wellhead_temp_c = row.get("wellhead_temp_c")
        obj.spill_detected = bool(row.get("spill_detected"))
        obj.spill_area_pct = row.get("spill_area_pct")
        obj.spill_est_volume_bbl = row.get("spill_est_volume_bbl")
        obj.evidence_images_json = row.get("evidence_images")
        obj.notes = row.get("notes") or ""
        obj.dataset_tag = dataset_tag
        stats["inspections"] += 1

    for row in _read_jsonl(well_dir / "maintenance.jsonl"):
        mid = row["maintenance_id"]
        obj = session.get(S.Maintenance, mid)
        if obj is None:
            obj = S.Maintenance(maintenance_id=mid)
            session.add(obj)
        cost = row.get("cost_usd") or {}
        obj.asset_id = row.get("asset_id", asset_id)
        obj.started_at = _parse_dt(row.get("started_at")) or datetime(1970, 1, 1)
        obj.completed_at = _parse_dt(row.get("completed_at"))
        obj.maintenance_type = row.get("maintenance_type")
        obj.equipment_kind = row.get("equipment_kind")
        obj.issue = row.get("issue")
        obj.action_taken = row.get("action_taken")
        obj.technician_user_id = row.get("technician_user_id")
        obj.contractor = row.get("contractor")
        obj.downtime_hours = row.get("downtime_hours")
        obj.cost_labor = cost.get("labor")
        obj.cost_parts = cost.get("parts")
        obj.cost_total = cost.get("total")
        obj.triggered_by_inspection_id = row.get("triggered_by_inspection_id")
        obj.report_file = row.get("report_file")
        obj.dataset_tag = dataset_tag
        stats["maintenance"] += 1

    for row in _read_jsonl(well_dir / "regulatory-events.jsonl"):
        eid = row["event_id"]
        obj = session.get(S.RegulatoryEvent, eid)
        if obj is None:
            obj = S.RegulatoryEvent(event_id=eid)
            session.add(obj)
        obj.asset_id = row.get("asset_id", asset_id)
        obj.event_date = _parse_date(row.get("date"))
        obj.agency = row.get("agency")
        obj.event_type = row.get("event_type")
        obj.protocol_id = row.get("protocol_id")
        obj.related_inspection_id = row.get("related_inspection_id")
        obj.hours_to_report = row.get("hours_to_report")
        obj.detail = row.get("detail")
        obj.fine_usd = row.get("fine_usd")
        obj.status = row.get("status")
        obj.dataset_tag = dataset_tag
        stats["regs"] += 1

    for row in _read_jsonl(well_dir / "context.jsonl"):
        nid = row["note_id"]
        obj = session.get(S.ContextNote, nid)
        if obj is None:
            obj = S.ContextNote(note_id=nid)
            session.add(obj)
        obj.asset_id = row.get("asset_id", asset_id)
        obj.created_at = _parse_dt(row.get("created_at"))
        obj.author_user_id = row.get("author_user_id")
        obj.note_type = row.get("note_type")
        obj.inspection_id = row.get("inspection_id")
        obj.text = row.get("text")
        obj.valid_from = row.get("valid_from")
        obj.valid_to = row.get("valid_to")
        obj.dataset_tag = dataset_tag
        stats["notes"] += 1

    reports_dir = well_dir / "maintenance-reports"
    if reports_dir.exists():
        for md in reports_dir.glob("*.md"):
            text = md.read_text(encoding="utf-8", errors="replace")
            rel = f"maintenance-reports/{md.name}"
            # find matching maintenance by report_file
            maint_id = None
            for m in session.query(S.Maintenance).filter(S.Maintenance.asset_id == asset_id).all():
                if m.report_file and (md.name in m.report_file or m.report_file.endswith(md.name)):
                    maint_id = m.maintenance_id
                    break
            existing = (
                session.query(S.ReportDoc)
                .filter(S.ReportDoc.report_file == rel, S.ReportDoc.dataset_tag == dataset_tag)
                .one_or_none()
            )
            if existing is None:
                # also try full path variants
                existing = (
                    session.query(S.ReportDoc)
                    .filter(S.ReportDoc.report_file.endswith(md.name), S.ReportDoc.dataset_tag == dataset_tag)
                    .one_or_none()
                )
            if existing is None:
                existing = S.ReportDoc(
                    asset_id=asset_id,
                    maintenance_id=maint_id,
                    report_file=rel,
                    text=text,
                    dataset_tag=dataset_tag,
                )
                session.add(existing)
            else:
                existing.text = text
                existing.maintenance_id = maint_id or existing.maintenance_id
                existing.asset_id = asset_id
            stats["reports"] += 1

    session.flush()
    return stats


def ingest_dataset(
    session: Session,
    data_root: Path,
    dataset_tag: str = "sample",
    well_limit: Optional[int] = None,
) -> dict:
    """Load fleet + assets. Upserts on natural keys. Safe to re-run / load test alongside."""
    data_root = Path(data_root)
    totals = {"fleet": {}, "wells": 0, "inspections": 0, "maintenance": 0, "regs": 0, "notes": 0, "reports": 0}
    totals["fleet"] = ingest_fleet(session, data_root, dataset_tag)

    assets = data_root / "assets"
    well_dirs = sorted([p for p in assets.iterdir() if p.is_dir()]) if assets.exists() else []
    if well_limit is not None:
        well_dirs = well_dirs[:well_limit]

    for wd in well_dirs:
        st = ingest_well(session, wd, dataset_tag)
        totals["wells"] += 1
        for k in ("inspections", "maintenance", "regs", "notes", "reports"):
            totals[k] += st[k]

    session.commit()
    return totals
