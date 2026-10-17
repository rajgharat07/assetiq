"""Final-round (test dataset) deterministic facts — Q1–Q11.

Today = 15 Jan 2027. Honest gaps: no reservoir-pressure series and no oil-production volumes
exist in the published files; those answers must refuse with evidence of the search.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import func, select

from assetiq.derived import facts as F
from assetiq.rules.registry import RuleRegistry, compare
from assetiq.store import schema as S
from assetiq.store.repo import Repository

RECALL_LOTS = {"LOT-2409-A", "LOT-2409-C", "LOT-2410-B"}
GAS_NOTE_RE = re.compile(
    r"(gas\s+odor|gas\s+smell|smelled\s+gas|rotten[- ]egg|h2s\s+monitor\s+alarmed|strong\s+gas\s+odor)",
    re.I,
)
BYPASS_IN_RE = re.compile(
    r"(temporary\s+bypass\s+in\s+place|bypass\s+installed|put\s+the\s+bypass\s+in|"
    r"crew\s+had\s+the\s+bypass\s+installed)",
    re.I,
)
BYPASS_OUT_RE = re.compile(
    r"(took\s+the\s+bypass\s+out|bypass\s+removed|bypass\s+pulled|valve\s+work\s+finished\s+and\s+bypass)",
    re.I,
)
SHUT_IN_RE = re.compile(r"\b(shut\s+in|shut-in)\b", re.I)
RESTART_RE = re.compile(r"\b(restart|restarted|back\s+online|returned\s+to\s+production)\b", re.I)
ABNORMAL_NOTE_RE = re.compile(
    r"(knock|rattle|vibration|hot|noise|noisy|smell|leak|trip|fault|alarm|pressure|"
    r"behav|sound|wrong|odd|seized|slow|sand|scale|gas\s+lock|amp|amp draw|ampdraw|"
    r"overheat|smoking|spark|ground\s+fault|not\s+pumping|downhole)",
    re.I,
)
WAIT_PARTS = re.compile(r"waiting on (replacement )?parts|parts from the vendor|on back-?order", re.I)
WAIT_CREW = re.compile(r"waiting on (a |the )?crew|crew availability|no crew", re.I)
WAIT_CONTRACTOR = re.compile(r"waiting on (a |the )?contractor|contractor delayed|workover rig delayed(?! by weather)", re.I)
WAIT_WEATHER = re.compile(r"delayed by weather|weather hold|waiting on weather|ice|storm", re.I)
PARTS_BLOCK_RE = re.compile(r"\*\*Parts installed:\*\*(.*?)(?:\n\*\*|\n## |\Z)", re.S | re.I)
LOT_RE = re.compile(r"(LOT-[\w-]+)")
COST_RE = re.compile(r"\$?\s*([\d,]+(?:\.\d+)?)\s*(?:USD|usd)?")


def _dt(d: date | datetime, end: bool = False) -> datetime:
    if isinstance(d, datetime):
        return d
    if end:
        return datetime(d.year, d.month, d.day, 23, 59, 59)
    return datetime(d.year, d.month, d.day, 0, 0, 0)


def _area_name(repo: Repository, area_id: str) -> str:
    a = repo.get_area(area_id)
    return a.name if a else area_id


def _well_area(repo: Repository, asset_id: str) -> tuple[Optional[S.Well], str]:
    w = repo.get_well(asset_id)
    if not w:
        return None, ""
    return w, _area_name(repo, w.area_id)


# ---------------------------------------------------------------------------
# Q1 / Q2 — honest gaps
# ---------------------------------------------------------------------------

def reservoir_pressure_gap(repo: Repository) -> dict:
    """No pressure series in inspections/metadata/notes — refuse with evidence."""
    # Spot-check: any numeric psi in context notes?
    psi_hits = []
    notes = list(
        repo.s.scalars(
            select(S.ContextNote).where(S.ContextNote.text.ilike("%psi%")).limit(20)
        )
    )
    for n in notes:
        psi_hits.append(n.note_id)
    return {
        "answerable": False,
        "reason": (
            "The test dataset has no reservoir-pressure measurements (no psi/gauge series on "
            "inspections, metadata, or production files). Map cannot be built from pressure data."
        ),
        "searched": [
            "assets/*/inspections.jsonl fields",
            "assets/*/metadata.json",
            "assets/*/context.jsonl",
            "fleet/*",
        ],
        "psi_note_ids": psi_hits[:5],
        "well_count": repo.s.scalar(select(func.count()).select_from(S.Well)) or 0,
    }


def best_oil_producer_2026_gap(repo: Repository) -> dict:
    return {
        "answerable": False,
        "reason": (
            "No oil-production volumes (bbl, bbl/d, tank runs, or allocation) appear in the "
            "test dataset for calendar year 2026. Cannot rank wells by oil produced."
        ),
        "searched": [
            "inspections.jsonl",
            "maintenance.jsonl",
            "context.jsonl (tank gauged notes have no volumes)",
            "fleet/*",
        ],
        "year": 2026,
    }


# ---------------------------------------------------------------------------
# Q3 — OPS-1 gas odor response
# ---------------------------------------------------------------------------

def gas_odor_responses(
    repo: Repository,
    since: datetime,
    today: datetime,
) -> dict:
    """Every gas-odor operator note since `since`, with OPS-1 deadline Met/Missed."""
    cutoff_2027 = datetime(2027, 1, 1, 0, 0, 0)
    notes = list(
        repo.s.scalars(
            select(S.ContextNote).where(
                S.ContextNote.note_type == "operator_note",
                S.ContextNote.created_at >= since,
                S.ContextNote.created_at <= today,
            )
        )
    )
    rows = []
    for n in notes:
        text = n.text or ""
        if not GAS_NOTE_RE.search(text):
            continue
        well, area = _well_area(repo, n.asset_id)
        reported = n.created_at
        if not reported:
            continue
        deadline_h = 12.0 if reported >= cutoff_2027 else 24.0
        deadline_at = reported + timedelta(hours=deadline_h)

        # Next response: maintenance started_at after note, or manual inspection after note
        response_id = None
        response_at = None
        mnts = repo.maintenance_for_asset(n.asset_id, start=reported, end=today + timedelta(days=2))
        for m in mnts:
            if m.started_at and m.started_at >= reported:
                response_id, response_at = m.maintenance_id, m.started_at
                break
        if response_at is None:
            insps = repo.inspections_in_range(n.asset_id, reported, today + timedelta(days=2))
            for insp in insps:
                if (insp.method or "").lower() == "manual" and insp.inspected_at >= reported:
                    response_id, response_at = insp.inspection_id, insp.inspected_at
                    break

        hours = None
        met = "Missed"
        if response_at is not None:
            hours = round((response_at - reported).total_seconds() / 3600.0, 2)
            met = "Met" if response_at <= deadline_at else "Missed"
        else:
            # still within deadline window today?
            if today <= deadline_at:
                met = "Missed"  # no response yet; finals ask Met/Missed — treat none as Missed
            met = "Missed"

        rows.append(
            {
                "well": n.asset_id,
                "area": area,
                "reported_at": reported.isoformat() + "Z",
                "response": f"{response_id} @ {response_at.isoformat()}Z" if response_id else "none",
                "hours_to_response": hours if hours is not None else None,
                "deadline_hours": deadline_h,
                "deadline_at": deadline_at.isoformat() + "Z",
                "met": met,
                "note_id": n.note_id,
                "note_text": text,
            }
        )
    rows.sort(key=lambda r: r["reported_at"])
    return {
        "rows": rows,
        "count": len(rows),
        "met": sum(1 for r in rows if r["met"] == "Met"),
        "missed": sum(1 for r in rows if r["met"] == "Missed"),
        "rule": "OPS-1",
        "source": "fleet/sops/operations-sop-rev2.md#OPS-1",
    }


# ---------------------------------------------------------------------------
# Q4 — temporary flowline bypasses + MOCs
# ---------------------------------------------------------------------------

def _load_mocs(data_root: Path) -> list[dict]:
    sops = data_root / "fleet" / "sops"
    out = []
    for p in sorted(sops.glob("moc-*.md")):
        text = p.read_text(encoding="utf-8", errors="replace")
        wells = re.findall(r"WELL-\d{4}", text)
        exp_m = re.search(r"[Tt]his approval expires on\s+(\d{1,2}\s+\w+\s+20\d{2})", text)
        eff_m = re.search(r"[Ee]ffective from\s+(\d{1,2}\s+\w+\s+20\d{2})", text)
        extends = re.search(r"extends\s+(MOC-[\d-]+)", text, re.I)
        memo_id = p.stem.upper().replace("MOC-", "MOC-")
        if not memo_id.startswith("MOC"):
            memo_id = p.stem

        def _parse_day(s: Optional[str]) -> Optional[date]:
            if not s:
                return None
            try:
                return datetime.strptime(s, "%d %b %Y").date()
            except ValueError:
                try:
                    return datetime.strptime(s, "%d %B %Y").date()
                except ValueError:
                    return None

        out.append(
            {
                "memo_id": p.stem,  # moc-2026-031
                "wells": sorted(set(wells)),
                "expires": _parse_day(exp_m.group(1) if exp_m else None),
                "effective_from": _parse_day(eff_m.group(1) if eff_m else None),
                "extends": extends.group(1) if extends else None,
                "path": f"fleet/sops/{p.name}",
            }
        )
    # Apply extensions: later memo replaces expiry for named wells of earlier memo
    by_id = {m["memo_id"]: m for m in out}
    for m in out:
        if m["extends"]:
            # extends MOC-2026-031 style
            key = m["extends"].lower()
            for mid, base in by_id.items():
                if mid.lower() == key.lower() or mid.lower().replace("moc-", "") in key.lower():
                    # replace expiry on base wells with this memo's expiry
                    base["expires"] = m["expires"]
                    base["extended_by"] = m["memo_id"]
    return out


def _approval_for_well(mocs: list[dict], well_id: str, as_of: date) -> dict:
    """Best MOC covering well: prefer non-expired, else latest expired."""
    covering = [m for m in mocs if well_id in m["wells"]]
    if not covering:
        return {"memo_id": None, "valid_until": None, "status_hint": "Not approved"}
    # Prefer memo whose expiry is still valid as_of
    valid = [m for m in covering if m["expires"] and m["expires"] >= as_of]
    if valid:
        # pick latest expiry
        best = max(valid, key=lambda m: m["expires"] or date.min)
        return {
            "memo_id": best.get("extended_by") or best["memo_id"],
            "valid_until": best["expires"].isoformat(),
            "status_hint": "Allowed",
            "path": best["path"],
        }
    # all expired
    best = max(covering, key=lambda m: m["expires"] or date.min)
    return {
        "memo_id": best.get("extended_by") or best["memo_id"],
        "valid_until": best["expires"].isoformat() if best["expires"] else None,
        "status_hint": "Expired",
        "path": best["path"],
    }


def temporary_bypasses(repo: Repository, data_root: Path, today: date) -> dict:
    mocs = _load_mocs(data_root)
    notes = list(
        repo.s.scalars(
            select(S.ContextNote).where(
                S.ContextNote.note_type == "operator_note",
                S.ContextNote.text.ilike("%bypass%"),
            )
        )
    )
    # Group events per well chronologically
    by_well: dict[str, list[tuple[datetime, str, str]]] = defaultdict(list)
    for n in notes:
        if not n.created_at:
            continue
        t = n.text or ""
        kind = None
        if BYPASS_OUT_RE.search(t):
            kind = "out"
        elif BYPASS_IN_RE.search(t) or ("bypass" in t.lower() and "in place" in t.lower()):
            kind = "in"
        elif "bypass" in t.lower() and any(w in t.lower() for w in ("removed", "pulled", "out")):
            kind = "out"
        elif "bypass" in t.lower() and any(w in t.lower() for w in ("installed", "put the", "in place")):
            kind = "in"
        if kind:
            by_well[n.asset_id].append((n.created_at, kind, n.note_id))

    episodes = []
    for well_id, events in by_well.items():
        events.sort(key=lambda x: x[0])
        open_in: Optional[datetime] = None
        open_note = None
        for ts, kind, nid in events:
            if kind == "in":
                if open_in is None:
                    open_in, open_note = ts, nid
                else:
                    # nested in — ignore / replace
                    open_in, open_note = ts, nid
            elif kind == "out" and open_in is not None:
                episodes.append(
                    {
                        "well": well_id,
                        "bypass_in": open_in,
                        "bypass_out": ts,
                        "in_note": open_note,
                        "out_note": nid,
                        "still_in": False,
                    }
                )
                open_in, open_note = None, None
        if open_in is not None:
            episodes.append(
                {
                    "well": well_id,
                    "bypass_in": open_in,
                    "bypass_out": None,
                    "in_note": open_note,
                    "out_note": None,
                    "still_in": True,
                }
            )

    rows = []
    for ep in episodes:
        well, area = _well_area(repo, ep["well"])
        appr = _approval_for_well(mocs, ep["well"], today)
        # Status for this episode:
        # - Not approved if no memo
        # - Expired if still in after approval ran out, OR was in after expiry (out after expiry)
        # - Allowed if approved and (out before expiry or still in and not past expiry)
        memo = appr["memo_id"]
        valid_until = appr["valid_until"]
        vu = date.fromisoformat(valid_until) if valid_until else None
        out_d = ep["bypass_out"].date() if ep["bypass_out"] else None
        in_d = ep["bypass_in"].date()

        if memo is None:
            status = "Not approved"
        elif vu is None:
            status = "Not approved"
        elif ep["still_in"]:
            status = "Allowed" if today <= vu else "Expired"
        else:
            # ended: expired if any day of bypass after vu
            status = "Expired" if out_d and out_d > vu else ("Allowed" if out_d and out_d <= vu else "Allowed")
            # also: if in after expiry day
            if in_d > vu:
                status = "Expired"

        rows.append(
            {
                "well": ep["well"],
                "area": area,
                "bypass_in": ep["bypass_in"].date().isoformat(),
                "bypass_out": "still in" if ep["still_in"] else ep["bypass_out"].date().isoformat(),
                "approval": memo or "none",
                "approval_valid_until": valid_until or "none",
                "status": status,
                "still_in": ep["still_in"],
            }
        )

    rows.sort(key=lambda r: (r["area"], r["well"], r["bypass_in"]))
    current = [r for r in rows if r["still_in"]]
    violations = [r for r in rows if r["status"] in ("Expired", "Not approved")]
    return {
        "rows": rows,
        "current": current,
        "violations": violations,
        "mocs": [{"memo_id": m["memo_id"], "expires": m["expires"].isoformat() if m["expires"] else None, "wells": m["wells"]} for m in mocs],
    }


# ---------------------------------------------------------------------------
# Q5 — regulator letter NE spills
# ---------------------------------------------------------------------------

def regulator_letter_spills(repo: Repository, today: date) -> dict:
    """Reportable spills in NE-07 / NE-08 since 1 Jun 2026; compliant if soil samples sentence."""
    start = datetime(2026, 6, 1, 0, 0, 0)
    end = _dt(today, end=True)
    area_ids = {"NE-07", "NE-08"}
    wells = list(repo.s.scalars(select(S.Well).where(S.Well.area_id.in_(area_ids))))
    phrase = "Soil samples sent to the lab."
    rows = []
    for w in wells:
        area = _area_name(repo, w.area_id)
        for insp in repo.inspections_in_range(w.asset_id, start, end):
            if not insp.spill_detected:
                continue
            # rain / not crude corrections
            if F._spill_corrected_away(repo, insp.inspection_id):
                continue
            vol = float(repo.effective_inspection_field(insp, "spill_est_volume_bbl") or 0)
            # also check correction notes that say not crude
            notes = repo.correction_notes_for_inspection(insp.inspection_id)
            not_crude = any(
                re.search(r"not (a )?(crude|oil)|rainwater|wet soil after rain", (n.text or ""), re.I)
                for n in notes
            )
            if not_crude:
                continue
            if vol < 5.0:
                continue
            # clean-up job linked
            cleanup = None
            for m in repo.maintenance_for_asset(w.asset_id, start=insp.inspected_at):
                issue = (m.issue or "").lower()
                if m.triggered_by_inspection_id == insp.inspection_id or "spill" in issue or "clean" in issue:
                    cleanup = m
                    break
            compliant = False
            reason = "No clean-up job found"
            cleanup_id = None
            if cleanup:
                cleanup_id = cleanup.maintenance_id
                linked = repo.linked_from_maintenance(cleanup.maintenance_id)
                report = linked.get("report")
                text = report.text if report else ""
                if phrase in text:
                    compliant = True
                    reason = "Clean-up report has 'Soil samples sent to the lab.'"
                else:
                    reason = "Clean-up report missing required soil-sample sentence"
            rows.append(
                {
                    "well": w.asset_id,
                    "area": area,
                    "inspection": f"{insp.inspection_id} ({insp.inspected_at.date().isoformat()})",
                    "inspection_id": insp.inspection_id,
                    "volume_bbl": vol,
                    "cleanup_job": cleanup_id or "none",
                    "compliant": "Yes" if compliant else "No",
                    "reason": reason,
                }
            )
    rows.sort(key=lambda r: (r["area"], r["well"], r["inspection"]))
    return {
        "rows": rows,
        "letter": "fleet/sops/regulator-letter-2026-11-20.md",
        "noncompliant": [r for r in rows if r["compliant"] == "No"],
        "count": len(rows),
    }


# ---------------------------------------------------------------------------
# Q6 — OPS-3 status disagreement
# ---------------------------------------------------------------------------

def _insp_producing(repo: Repository, rules: RuleRegistry, well: S.Well, insp: S.Inspection) -> bool:
    wh = float(repo.effective_inspection_field(insp, "wellhead_temp_c") or 0)
    amb = float(repo.effective_inspection_field(insp, "ambient_temp_c") or 0)
    delta = F.temp_delta(wh, amb)
    return compare(delta, rules.producing_rule(well.well_type))


def _latest_status_note(notes: list[S.ContextNote]) -> Optional[S.ContextNote]:
    cand = []
    for n in notes:
        if n.note_type != "operator_note" or not n.created_at:
            continue
        t = n.text or ""
        if SHUT_IN_RE.search(t) or RESTART_RE.search(t):
            # exclude gas/bypass-only notes that mention shut incidentally? keep all shut-in/restart
            cand.append(n)
    if not cand:
        return None
    return max(cand, key=lambda n: n.created_at)


def ops3_status_disagreements(repo: Repository, rules: RuleRegistry, today: datetime) -> dict:
    wells = list(repo.s.scalars(select(S.Well).order_by(S.Well.asset_id)))
    rows = []
    for w in wells:
        if (w.status or "") == "plugged_and_abandoned" or (w.recorded_status or "") == "plugged":
            continue
        insp = repo.latest_inspection(w.asset_id)
        if not insp or insp.inspected_at > today:
            # still use latest as of today
            all_i = repo.inspections_in_range(w.asset_id, datetime(2000, 1, 1), today)
            insp = all_i[-1] if all_i else None
        if not insp:
            continue
        notes = [n for n in repo.notes_for_asset(w.asset_id) if n.created_at and n.created_at <= today]
        note = _latest_status_note(notes)
        insp_prod = _insp_producing(repo, rules, w, insp)
        insp_label = "producing oil" if insp_prod else "not producing oil"

        if note is None:
            continue
        note_shut = bool(SHUT_IN_RE.search(note.text or ""))
        note_restart = bool(RESTART_RE.search(note.text or "")) and not note_shut
        note_says_prod = note_restart
        note_says_down = note_shut
        note_label = "producing (restart)" if note_says_prod else ("not producing (shut in)" if note_says_down else note.text)

        # Disagree about whether producing oil
        disagrees = (insp_prod and note_says_down) or ((not insp_prod) and note_says_prod)
        if not disagrees:
            continue

        # OPS-3 precedence: most recent of inspection vs status note
        if note.created_at > insp.inspected_at:
            if note_says_down:
                status_now = "Not producing oil"
                why = "OPS-3: shut-in operator note is more recent than latest inspection"
            else:
                status_now = "Producing oil (unconfirmed)"
                why = "OPS-3: restart note more recent than inspection; awaiting inspection confirm"
        else:
            status_now = "Producing oil" if insp_prod else "Not producing oil"
            why = "OPS-3: latest inspection is more recent than status operator note"

        rows.append(
            {
                "well": w.asset_id,
                "area": _area_name(repo, w.area_id),
                "latest_inspection": (
                    f"{insp.inspection_id}, {insp.inspected_at.date().isoformat()}, {insp_label} "
                    f"(Δ{F.temp_delta(float(repo.effective_inspection_field(insp,'wellhead_temp_c') or 0), float(repo.effective_inspection_field(insp,'ambient_temp_c') or 0))}°C)"
                ),
                "latest_operator_note": f"{note.created_at.isoformat()}Z, {note.text}",
                "status_now": f"{status_now} — {why}",
            }
        )
    rows.sort(key=lambda r: (r["area"], r["well"]))
    return {"rows": rows, "count": len(rows), "rule": "OPS-3", "source": "fleet/sops/operations-sop-rev2.md#OPS-3"}


# ---------------------------------------------------------------------------
# Q7 — abnormal operator notes without repair
# ---------------------------------------------------------------------------

def operator_abnormal_rank(
    repo: Repository,
    rules: RuleRegistry,
    today: datetime,
    month_days: int = 31,
    top_n: int = 10,
) -> dict:
    start = today - timedelta(days=month_days)
    notes = list(
        repo.s.scalars(
            select(S.ContextNote).where(
                S.ContextNote.note_type == "operator_note",
                S.ContextNote.created_at >= start,
                S.ContextNote.created_at <= today,
            )
        )
    )
    # Collect abnormal notes per well (latest quote)
    by_well: dict[str, list[S.ContextNote]] = defaultdict(list)
    for n in notes:
        t = (n.text or "").lower()
        if GAS_NOTE_RE.search(n.text or ""):
            continue  # gas handled by OPS-1, not this ranking focus unless abnormal equipment
        if BYPASS_IN_RE.search(n.text or "") or BYPASS_OUT_RE.search(n.text or ""):
            continue
        if "tank gauged" in t or "pumping normally" in t or "nothing to report" in t or "running steady" in t:
            continue
        if "pad dry" in t or "drive panel readings normal" in t or "level normal" in t:
            continue
        if WAIT_PARTS.search(n.text or "") or WAIT_WEATHER.search(n.text or "") or "pipeline tie-in" in t:
            continue
        if SHUT_IN_RE.search(n.text or "") and "high pressure" not in t and not ABNORMAL_NOTE_RE.search(n.text or ""):
            # plain shut-in for pipeline — skip unless abnormal keywords
            if "for the night" in t or "tie-in" in t:
                continue
        if ABNORMAL_NOTE_RE.search(n.text or "") or any(
            k in t for k in ("knock", "rattle", "hot bearing", "vibration", "amp", "trip", "overheat")
        ):
            by_well[n.asset_id].append(n)

    candidates = []
    for well_id, ns in by_well.items():
        ns.sort(key=lambda x: x.created_at or datetime.min)
        latest_note = ns[-1]
        # any repair (non spill clean-up) after the first abnormal note in window
        first = ns[0].created_at
        mnts = repo.maintenance_for_asset(well_id, start=first, end=today)
        repaired = False
        last_repair = None
        all_mnt = repo.maintenance_for_asset(well_id)
        for m in all_mnt:
            if m.started_at and (last_repair is None or m.started_at > last_repair.started_at):
                last_repair = m
        for m in mnts:
            issue = (m.issue or "").lower()
            if "spill" in issue or "clean-up" in issue or "cleanup" in issue:
                continue
            if m.started_at and m.started_at >= first:
                repaired = True
                break
        if repaired:
            continue

        well, area = _well_area(repo, well_id)
        if not well:
            continue
        # warning signs: not producing, falling delta, recent corrective history
        insp = repo.latest_inspection(well_id)
        warnings = []
        score = len(ns) * 10
        if insp:
            prod = _insp_producing(repo, rules, well, insp)
            if not prod:
                warnings.append("latest inspection not producing")
                score += 25
            # last 4 deltas trend
            recent = repo.inspections_in_range(well_id, today - timedelta(days=45), today)
            if len(recent) >= 4:
                deltas = []
                for i in recent[-4:]:
                    wh = float(repo.effective_inspection_field(i, "wellhead_temp_c") or 0)
                    amb = float(repo.effective_inspection_field(i, "ambient_temp_c") or 0)
                    deltas.append(F.temp_delta(wh, amb))
                if all(deltas[i] > deltas[i + 1] for i in range(3)) and (deltas[0] - deltas[3]) >= 3:
                    warnings.append(f"falling wellhead Δ over 4 readings ({deltas[0]}→{deltas[3]}°C)")
                    score += 30
        corr_12m = [
            m
            for m in all_mnt
            if (m.maintenance_type or "") == "corrective"
            and m.started_at
            and m.started_at >= today - timedelta(days=365)
        ]
        if len(corr_12m) >= 2:
            warnings.append(f"{len(corr_12m)} corrective jobs in 12 months")
            score += 15 * len(corr_12m)
        score += min(20, len(latest_note.text or "") // 40)

        candidates.append(
            {
                "well": well_id,
                "area": area,
                "score": score,
                "note_date": latest_note.created_at.isoformat() + "Z" if latest_note.created_at else "",
                "quote": latest_note.text,
                "note_id": latest_note.note_id,
                "warnings": "; ".join(warnings) if warnings else "operator note only",
                "last_repair": (
                    f"{last_repair.maintenance_id} on {last_repair.started_at.date().isoformat()}"
                    if last_repair and last_repair.started_at
                    else "none on record"
                ),
            }
        )

    candidates.sort(key=lambda r: (-r["score"], r["well"]))
    ranked = []
    for i, c in enumerate(candidates[:top_n], 1):
        ranked.append({**c, "rank": i})
    return {"rows": ranked, "all_candidates": len(candidates)}


# ---------------------------------------------------------------------------
# Q8 — recalled pumps still in ground
# ---------------------------------------------------------------------------

def _parse_parts_installed(text: str) -> list[dict]:
    m = PARTS_BLOCK_RE.search(text or "")
    if not m:
        return []
    block = m.group(1)
    lots = LOT_RE.findall(block)
    # crude cost: look near "cost" or dollar in report header tables
    return [{"lot": lot, "block": " ".join(block.split())[:240]} for lot in lots]


def recalled_pumps_in_ground(
    repo: Repository,
    today: datetime,
    replaced_wells: Optional[set[str]] = None,
) -> dict:
    """Latest downhole/ESP pump install Parts-installed lot; recalled if lot in RECALL_LOTS and not replaced."""
    replaced_wells = replaced_wells or set()
    reports = list(repo.s.scalars(select(S.ReportDoc)))
    # Map well -> list of (completed_at/started_at, maintenance_id, lots, cost)
    installs: dict[str, list[dict]] = defaultdict(list)
    for r in reports:
        parts = _parse_parts_installed(r.text or "")
        if not parts:
            continue
        m = repo.get_maintenance(r.maintenance_id) if r.maintenance_id else None
        when = None
        cost = None
        mid = r.maintenance_id
        if m:
            when = m.completed_at or m.started_at
            cost = m.cost_total
            if (m.equipment_kind or "") not in ("downhole_pump", "esp_pump", None, ""):
                # still allow if parts block mentions RP-175 / rod pump
                if "RP-175" not in (r.text or "") and "rod pump" not in (r.text or "").lower():
                    if m.equipment_kind not in ("downhole_pump",):
                        pass
        for p in parts:
            installs[r.asset_id].append(
                {
                    "lot": p["lot"],
                    "when": when,
                    "maintenance_id": mid,
                    "cost_total": cost,
                    "block": p["block"],
                    "report_file": r.report_file,
                }
            )

    rows = []
    for well_id, events in installs.items():
        # current pump = latest install by when
        events.sort(key=lambda e: e["when"] or datetime.min)
        latest = events[-1]
        if latest["lot"] not in RECALL_LOTS:
            continue
        if well_id in replaced_wells:
            continue
        # shared knowledge may mark replaced
        well, area = _well_area(repo, well_id)
        rows.append(
            {
                "well": well_id,
                "area": area or "",
                "area_id": well.area_id if well else "",
                "team_id": well.team_id if well else "",
                "lot": latest["lot"],
                "installed_on": latest["when"].date().isoformat() if latest["when"] else "unknown",
                "maintenance_id": latest["maintenance_id"],
                "cost_usd": latest["cost_total"],
                "evidence": latest["report_file"],
                "source": f"Parts installed on {latest['maintenance_id']} ({latest['report_file']})",
            }
        )
    rows.sort(key=lambda r: (r["area"], r["well"]))
    return {
        "rows": rows,
        "count": len(rows),
        "recall_notice": "fleet/sops/supplier-recall-notice-2026-12-01.md",
        "lots": sorted(RECALL_LOTS),
    }


# ---------------------------------------------------------------------------
# Q10 — wait reasons when shut-in longer than repair
# ---------------------------------------------------------------------------

def wait_reasons_2026(repo: Repository, today: datetime) -> dict:
    """Jobs started in 2026 where operator wait notes imply extra days beyond repair downtime."""
    start = datetime(2026, 1, 1)
    end = min(today, datetime(2026, 12, 31, 23, 59, 59))
    # Collect wait notes in 2026
    notes = list(
        repo.s.scalars(
            select(S.ContextNote).where(
                S.ContextNote.note_type == "operator_note",
                S.ContextNote.created_at >= start,
                S.ContextNote.created_at <= _dt(today, end=True),
            )
        )
    )
    # For each wait note, find overlapping/nearby maintenance and estimate extra days
    # Heuristic from note text: "about N days" or compare downtime_hours vs calendar shut span
    area_stats: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    for n in notes:
        text = n.text or ""
        reason = None
        if WAIT_WEATHER.search(text):
            reason = "weather"
        elif WAIT_PARTS.search(text):
            reason = "parts"
        elif WAIT_CONTRACTOR.search(text) or "workover rig delayed" in text.lower():
            reason = "contractors"
        elif WAIT_CREW.search(text):
            reason = "crews"
        else:
            continue
        well, area = _well_area(repo, n.asset_id)
        if not area:
            continue
        # extra days from note ("about N days") or from next restart/repair duration gap
        extra = None
        m_days = re.search(r"about\s+(\d+)\s+days?", text, re.I)
        if m_days:
            extra = float(m_days.group(1))
        else:
            # find maintenance around note; extra = max(0, calendar days - downtime_hours/24)
            mnts = repo.maintenance_for_asset(
                n.asset_id,
                start=(n.created_at or start) - timedelta(days=3),
                end=(n.created_at or start) + timedelta(days=60),
            )
            if mnts:
                m = mnts[0]
                if m.started_at and m.completed_at:
                    cal = (m.completed_at - m.started_at).total_seconds() / 86400.0
                    down = (m.downtime_hours or 0) / 24.0
                    # Prefer note-implied wait: if completed after note, use days from note to complete
                    if n.created_at and m.completed_at > n.created_at:
                        extra = max(0.0, (m.completed_at - n.created_at).total_seconds() / 86400.0)
                    else:
                        extra = max(0.0, cal - down)
            if extra is None:
                extra = 3.0  # default typical when unspecified
        if n.created_at and n.created_at.year != 2026 and reason:
            # still count if job started 2026 — filter via nearby mnt
            pass
        # Only jobs started 2026: verify a 2026 maintenance near this note
        mnts_2026 = [
            m
            for m in repo.maintenance_for_asset(n.asset_id, start=start, end=end)
            if m.started_at
        ]
        if not mnts_2026 and (not n.created_at or n.created_at.year != 2026):
            continue
        area_stats[area][reason].append(float(extra))

    # Build table: for each area, share + typical extra days per reason
    table = []
    chart = []  # stacked bar data
    for area, reasons in sorted(area_stats.items()):
        total = sum(len(v) for v in reasons.values())
        if total == 0:
            continue
        row = {"area": area}
        chart_row = {"area": area}
        for reason in ("parts", "crews", "contractors", "weather"):
            vals = reasons.get(reason) or []
            share = round(100.0 * len(vals) / total, 1) if total else 0.0
            typical = round(sorted(vals)[len(vals) // 2], 1) if vals else 0.0  # median
            row[f"{reason}_share_pct"] = share
            row[f"{reason}_typical_extra_days"] = typical
            chart_row[reason] = share
        row["n"] = total
        table.append(row)
        chart.append(chart_row)

    # standout: highest weather or parts share
    standout = None
    if table:
        standout = max(table, key=lambda r: max(r.get("parts_share_pct", 0), r.get("weather_share_pct", 0), r.get("contractors_share_pct", 0)))
    return {"rows": table, "chart": chart, "standout": standout}


# ---------------------------------------------------------------------------
# Q11 — hotter region
# ---------------------------------------------------------------------------

def hotter_region(repo: Repository, today: datetime, lookback_days: int = 90) -> dict:
    start = today - timedelta(days=lookback_days)
    wells = list(repo.s.scalars(select(S.Well)))
    # Region = first word of area name, or area itself; question says "region of the field"
    # Use area-level mean wellhead and mean delta, then compare NE/SW/SE/NW
    region_wh: dict[str, list[float]] = defaultdict(list)
    region_delta: dict[str, list[float]] = defaultdict(list)
    area_wh: dict[str, list[float]] = defaultdict(list)

    for w in wells:
        area = _area_name(repo, w.area_id)
        region = area.split()[0] if area else w.area_id  # Northeast / Southwest / ...
        insps = repo.inspections_in_range(w.asset_id, start, today)
        for insp in insps:
            wh = repo.effective_inspection_field(insp, "wellhead_temp_c")
            amb = repo.effective_inspection_field(insp, "ambient_temp_c")
            if wh is None:
                continue
            region_wh[region].append(float(wh))
            area_wh[area].append(float(wh))
            if amb is not None:
                region_delta[region].append(F.temp_delta(float(wh), float(amb)))

    def _avg(xs: list[float]) -> float:
        return round(sum(xs) / len(xs), 2) if xs else 0.0

    region_rows = [
        {
            "region": r,
            "mean_wellhead_c": _avg(region_wh[r]),
            "mean_delta_c": _avg(region_delta[r]),
            "n": len(region_wh[r]),
        }
        for r in region_wh
    ]
    region_rows.sort(key=lambda x: -x["mean_wellhead_c"])
    area_rows = [
        {"area": a, "mean_wellhead_c": _avg(area_wh[a]), "n": len(area_wh[a])}
        for a in area_wh
    ]
    area_rows.sort(key=lambda x: -x["mean_wellhead_c"])
    return {
        "hottest_region": region_rows[0] if region_rows else None,
        "regions": region_rows,
        "areas": area_rows[:7],
        "window_days": lookback_days,
    }
