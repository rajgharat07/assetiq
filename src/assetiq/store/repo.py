"""Repository — structured queries over MySQL. Numbers are queried, not embedded."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import Session

from . import schema as S


class Repository:
    def __init__(self, session: Session):
        self.s = session

    # --- lookups ---
    def get_well(self, asset_id: str) -> Optional[S.Well]:
        return self.s.get(S.Well, asset_id)

    def get_user(self, user_id: str) -> Optional[S.User]:
        return self.s.get(S.User, user_id)

    def get_user_by_name(self, name: str) -> Optional[S.User]:
        return self.s.execute(
            select(S.User).where(func.lower(S.User.name) == name.lower())
        ).scalar_one_or_none()

    def list_users(self) -> list[S.User]:
        return list(self.s.scalars(select(S.User).order_by(S.User.name)))

    def get_area_by_name(self, name: str) -> Optional[S.Area]:
        return self.s.execute(
            select(S.Area).where(func.lower(S.Area.name) == name.lower())
        ).scalar_one_or_none()

    def get_area(self, area_id: str) -> Optional[S.Area]:
        return self.s.get(S.Area, area_id)

    def wells_in_area(self, area_id: str) -> list[S.Well]:
        return list(
            self.s.scalars(select(S.Well).where(S.Well.area_id == area_id).order_by(S.Well.asset_id))
        )

    def get_inspection(self, inspection_id: str) -> Optional[S.Inspection]:
        return self.s.get(S.Inspection, inspection_id)

    def latest_inspection(self, asset_id: str) -> Optional[S.Inspection]:
        return self.s.execute(
            select(S.Inspection)
            .where(S.Inspection.asset_id == asset_id)
            .order_by(S.Inspection.inspected_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    def inspections_in_range(
        self, asset_id: str, start: datetime, end: datetime
    ) -> list[S.Inspection]:
        return list(
            self.s.scalars(
                select(S.Inspection)
                .where(
                    S.Inspection.asset_id == asset_id,
                    S.Inspection.inspected_at >= start,
                    S.Inspection.inspected_at <= end,
                )
                .order_by(S.Inspection.inspected_at.asc())
            )
        )

    def inspections_for_area_range(
        self, area_id: str, start: datetime, end: datetime
    ) -> list[S.Inspection]:
        wells = [w.asset_id for w in self.wells_in_area(area_id)]
        if not wells:
            return []
        return list(
            self.s.scalars(
                select(S.Inspection)
                .where(
                    S.Inspection.asset_id.in_(wells),
                    S.Inspection.inspected_at >= start,
                    S.Inspection.inspected_at <= end,
                )
                .order_by(S.Inspection.inspected_at.asc())
            )
        )

    def all_inspections_in_range(self, start: datetime, end: datetime) -> list[S.Inspection]:
        return list(
            self.s.scalars(
                select(S.Inspection)
                .where(
                    S.Inspection.inspected_at >= start,
                    S.Inspection.inspected_at <= end,
                )
                .order_by(S.Inspection.inspected_at.asc())
            )
        )

    def maintenance_for_asset(
        self, asset_id: str, start: Optional[datetime] = None, end: Optional[datetime] = None
    ) -> list[S.Maintenance]:
        q = select(S.Maintenance).where(S.Maintenance.asset_id == asset_id)
        if start is not None:
            q = q.where(S.Maintenance.started_at >= start)
        if end is not None:
            q = q.where(S.Maintenance.started_at <= end)
        return list(self.s.scalars(q.order_by(S.Maintenance.started_at.asc())))

    def get_maintenance(self, maintenance_id: str) -> Optional[S.Maintenance]:
        return self.s.get(S.Maintenance, maintenance_id)

    def regulatory_for_asset(self, asset_id: str) -> list[S.RegulatoryEvent]:
        return list(
            self.s.scalars(
                select(S.RegulatoryEvent)
                .where(S.RegulatoryEvent.asset_id == asset_id)
                .order_by(S.RegulatoryEvent.event_date.asc())
            )
        )

    def notes_for_asset(self, asset_id: str) -> list[S.ContextNote]:
        return list(
            self.s.scalars(
                select(S.ContextNote)
                .where(S.ContextNote.asset_id == asset_id)
                .order_by(S.ContextNote.created_at.asc())
            )
        )

    def correction_notes_for_inspection(self, inspection_id: str) -> list[S.ContextNote]:
        return list(
            self.s.scalars(
                select(S.ContextNote).where(
                    S.ContextNote.inspection_id == inspection_id,
                    S.ContextNote.note_type == "correction",
                )
            )
        )

    def report_by_file(self, report_file: str) -> Optional[S.ReportDoc]:
        # match by basename or full relative path
        rows = list(
            self.s.scalars(
                select(S.ReportDoc).where(
                    or_(
                        S.ReportDoc.report_file == report_file,
                        S.ReportDoc.report_file.endswith(report_file.replace("\\", "/").split("/")[-1]),
                    )
                )
            )
        )
        return rows[0] if rows else None

    def report_for_maintenance(self, maintenance_id: str) -> Optional[S.ReportDoc]:
        return self.s.execute(
            select(S.ReportDoc).where(S.ReportDoc.maintenance_id == maintenance_id).limit(1)
        ).scalar_one_or_none()

    def linked_from_maintenance(self, maintenance_id: str) -> dict[str, Any]:
        m = self.get_maintenance(maintenance_id)
        if not m:
            return {}
        insp = self.get_inspection(m.triggered_by_inspection_id) if m.triggered_by_inspection_id else None
        report = None
        if m.report_file:
            report = self.report_by_file(m.report_file)
        if report is None:
            report = self.report_for_maintenance(maintenance_id)
        return {"maintenance": m, "inspection": insp, "report": report}

    def active_corrections(
        self, target_id: Optional[str] = None, field_name: Optional[str] = None
    ) -> list[S.Correction]:
        q = select(S.Correction)
        if target_id:
            q = q.where(S.Correction.target_id == target_id)
        if field_name:
            q = q.where(S.Correction.field_name == field_name)
        return list(self.s.scalars(q.order_by(S.Correction.created_at.asc())))

    def effective_inspection_field(self, insp: S.Inspection, field: str) -> Any:
        """Apply formal corrections at read time; keep original on the row."""
        raw = getattr(insp, field, None)
        corrs = self.active_corrections(insp.inspection_id, field)
        if not corrs:
            return raw
        # latest correction wins
        last = corrs[-1]
        val = last.corrected_value
        if field in ("wellhead_temp_c", "ambient_temp_c", "spill_est_volume_bbl", "spill_area_pct"):
            try:
                return float(val)
            except ValueError:
                return val
        if field == "spill_detected":
            return val.lower() in ("1", "true", "yes")
        return val
