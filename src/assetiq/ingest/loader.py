"""Idempotent ingest. dataset_tag lets the ~4pm test folder load alongside sample.

Fast path: after a wipe, tables are empty — use bulk inserts + periodic commits.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.dialects.mysql import insert as mysql_insert
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


def _bulk_upsert(session: Session, table, rows: list[dict], pk: str) -> None:
    if not rows:
        return
    # chunk to keep packet size sane
    chunk = 500
    for i in range(0, len(rows), chunk):
        part = rows[i : i + chunk]
        stmt = mysql_insert(table).values(part)
        update = {c.name: stmt.inserted[c.name] for c in table.c if c.name != pk}
        session.execute(stmt.on_duplicate_key_update(**update))


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
        obj.status = m.get("status")
        obj.decommissioned_on = m.get("decommissioned_on")
        obj.type_history_json = m.get("type_history")
        obj.team_history_json = m.get("team_history")
        obj.last_inspection_id = li.get("inspection_id")
        obj.last_inspected_at = _parse_dt(li.get("inspected_at"))
        obj.equipment_json = m.get("equipment")
        obj.dataset_tag = dataset_tag

    insp_rows = []
    for row in _read_jsonl(well_dir / "inspections.jsonl"):
        insp_rows.append(
            {
                "inspection_id": row["inspection_id"],
                "asset_id": row.get("asset_id", asset_id),
                "inspected_at": _parse_dt(row.get("inspected_at")) or datetime(1970, 1, 1),
                "inspector_user_id": row.get("inspector_user_id"),
                "method": row.get("method"),
                "ambient_temp_c": row.get("ambient_temp_c"),
                "wellhead_temp_c": row.get("wellhead_temp_c"),
                "spill_detected": bool(row.get("spill_detected")),
                "spill_area_pct": row.get("spill_area_pct"),
                "spill_est_volume_bbl": row.get("spill_est_volume_bbl"),
                "evidence_images_json": row.get("evidence_images"),
                "notes": row.get("notes") or "",
                "recorded_at": _parse_dt(row.get("recorded_at")),
                "dataset_tag": dataset_tag,
            }
        )
    _bulk_upsert(session, S.Inspection.__table__, insp_rows, "inspection_id")
    stats["inspections"] = len(insp_rows)

    mnt_rows = []
    for row in _read_jsonl(well_dir / "maintenance.jsonl"):
        cost = row.get("cost_usd") or {}
        mnt_rows.append(
            {
                "maintenance_id": row["maintenance_id"],
                "asset_id": row.get("asset_id", asset_id),
                "started_at": _parse_dt(row.get("started_at")) or datetime(1970, 1, 1),
                "completed_at": _parse_dt(row.get("completed_at")),
                "maintenance_type": row.get("maintenance_type"),
                "equipment_kind": row.get("equipment_kind"),
                "issue": row.get("issue"),
                "action_taken": row.get("action_taken"),
                "technician_user_id": row.get("technician_user_id"),
                "contractor": row.get("contractor"),
                "downtime_hours": row.get("downtime_hours"),
                "cost_labor": cost.get("labor"),
                "cost_parts": cost.get("parts"),
                "cost_total": cost.get("total"),
                "triggered_by_inspection_id": row.get("triggered_by_inspection_id"),
                "report_file": row.get("report_file"),
                "recorded_at": _parse_dt(row.get("recorded_at")),
                "cost_revision_json": row.get("cost_revision"),
                "dataset_tag": dataset_tag,
            }
        )
    _bulk_upsert(session, S.Maintenance.__table__, mnt_rows, "maintenance_id")
    stats["maintenance"] = len(mnt_rows)

    reg_rows = []
    for row in _read_jsonl(well_dir / "regulatory-events.jsonl"):
        reg_rows.append(
            {
                "event_id": row["event_id"],
                "asset_id": row.get("asset_id", asset_id),
                "event_date": _parse_date(row.get("date")),
                "agency": row.get("agency"),
                "event_type": row.get("event_type"),
                "protocol_id": row.get("protocol_id"),
                "related_inspection_id": row.get("related_inspection_id"),
                "hours_to_report": row.get("hours_to_report"),
                "detail": row.get("detail"),
                "fine_usd": row.get("fine_usd"),
                "status": row.get("status"),
                "dataset_tag": dataset_tag,
            }
        )
    _bulk_upsert(session, S.RegulatoryEvent.__table__, reg_rows, "event_id")
    stats["regs"] = len(reg_rows)

    note_rows = []
    corr_rows = []
    for row in _read_jsonl(well_dir / "context.jsonl"):
        nid = row["note_id"]
        ov = row.get("original_value")
        cv = row.get("corrected_value")
        note_rows.append(
            {
                "note_id": nid,
                "asset_id": row.get("asset_id", asset_id),
                "created_at": _parse_dt(row.get("created_at")),
                "author_user_id": row.get("author_user_id"),
                "note_type": row.get("note_type"),
                "inspection_id": row.get("inspection_id"),
                "text": row.get("text"),
                "field_name": row.get("field"),
                "original_value": None if ov is None else str(ov),
                "corrected_value": None if cv is None else str(cv),
                "valid_from": row.get("valid_from"),
                "valid_to": row.get("valid_to"),
                "dataset_tag": dataset_tag,
            }
        )
        if (row.get("note_type") or "") == "data_correction" and row.get("inspection_id") and row.get("field"):
            corr_rows.append(
                {
                    "correction_id": f"DC-{nid}",
                    "target_type": "inspection_field",
                    "target_id": row["inspection_id"],
                    "field_name": row["field"],
                    "original_value": None if ov is None else str(ov),
                    "corrected_value": "" if cv is None else str(cv),
                    "author_user_id": row.get("author_user_id") or "system",
                    "reason": row.get("text") or "data_correction",
                    "scope": "asset",
                    "scope_key": asset_id,
                    "created_at": _parse_dt(row.get("created_at")) or datetime(1970, 1, 1),
                    "valid_from": row.get("valid_from"),
                    "valid_to": row.get("valid_to"),
                }
            )
    _bulk_upsert(session, S.ContextNote.__table__, note_rows, "note_id")
    _bulk_upsert(session, S.Correction.__table__, corr_rows, "correction_id")
    stats["notes"] = len(note_rows)

    reports_dir = well_dir / "maintenance-reports"
    if reports_dir.exists():
        for md in reports_dir.glob("*.md"):
            text = md.read_text(encoding="utf-8", errors="replace")
            rel = f"maintenance-reports/{md.name}"
            stem = md.stem
            maint_id = stem if stem.startswith("MNT-") else None
            session.add(
                S.ReportDoc(
                    asset_id=asset_id,
                    maintenance_id=maint_id,
                    report_file=rel,
                    text=text,
                    dataset_tag=dataset_tag,
                )
            )
            stats["reports"] += 1

    return stats


def ingest_dataset(
    session: Session,
    data_root: Path,
    dataset_tag: str = "sample",
    well_limit: Optional[int] = None,
) -> dict:
    """Load fleet + assets. Upserts on natural keys. Commits every 25 wells."""
    data_root = Path(data_root)
    totals = {"fleet": {}, "wells": 0, "inspections": 0, "maintenance": 0, "regs": 0, "notes": 0, "reports": 0}
    totals["fleet"] = ingest_fleet(session, data_root, dataset_tag)
    session.commit()
    print(f"fleet_ok areas={totals['fleet'].get('areas')} users={totals['fleet'].get('users')}", flush=True)

    assets = data_root / "assets"
    well_dirs = sorted([p for p in assets.iterdir() if p.is_dir()]) if assets.exists() else []
    if well_limit is not None:
        well_dirs = well_dirs[:well_limit]

    for i, wd in enumerate(well_dirs, 1):
        st = ingest_well(session, wd, dataset_tag)
        totals["wells"] += 1
        for k in ("inspections", "maintenance", "regs", "notes", "reports"):
            totals[k] += st[k]
        if i % 25 == 0 or i == len(well_dirs):
            session.commit()
            print(
                f"ingest_progress wells={i}/{len(well_dirs)} "
                f"insp={totals['inspections']} mnt={totals['maintenance']} "
                f"notes={totals['notes']} reports={totals['reports']}",
                flush=True,
            )

    session.commit()
    return totals
