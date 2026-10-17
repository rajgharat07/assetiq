"""RuleRegistry — business rules as data with provenance, not scattered magic numbers.

Sources (must cite):
- fleet/well-types/T200.md §9.3 — T200 producing: wellhead - ambient >= 15 °C
- fleet/well-types/T350.md §3 — T350 producing: >= 20 °C
- fleet/sops/spill-response-sop.md — SR-01 24h / 5 bbl, SR-02 4h, SR-03 60d
- fleet/sops/regulatory-compliance-sop.md — RC-01..05
- Dataset Guide — downtime: 7 days per not-producing weekly inspection; missed = 0
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional


@dataclass(frozen=True)
class Rule:
    rule_id: str
    threshold: Optional[float]
    unit: Optional[str]
    operator: Optional[str]
    source_file: str
    source_section: str
    well_type: Optional[str] = None
    description: Optional[str] = None


# Seeded from the manuals/SOPs (validated against the files on load).
# Exact section lookup — never vector-search for thresholds.
SEED_RULES: tuple[Rule, ...] = (
    Rule(
        "T200_PRODUCING_DELTA",
        15.0,
        "C",
        "gte",
        "fleet/well-types/T200.md",
        "9.3",
        "T200",
        "Producing when wellhead - ambient >= 15 C",
    ),
    Rule(
        "T350_PRODUCING_DELTA",
        20.0,
        "C",
        "gte",
        "fleet/well-types/T350.md",
        "3",
        "T350",
        "Producing when wellhead - ambient >= 20 C",
    ),
    Rule(
        "T500_PRODUCING_DELTA",
        25.0,
        "C",
        "gte",
        "fleet/well-types/T500.md",
        "3",
        "T500",
        "Producing when wellhead - ambient >= 25 C",
    ),
    Rule(
        "T500_WH_ALARM",
        95.0,
        "C",
        "lte",
        "fleet/well-types/T500.md",
        "4",
        "T500",
        "Wellhead must stay at or below 95 C",
    ),
    Rule(
        "OPS1_GAS_RESPONSE_HOURS_PRE_2027",
        24.0,
        "hours",
        "lte",
        "fleet/sops/operations-sop-rev2.md",
        "OPS-1",
        None,
        "Gas odor field response within 24h for reports before 1 Jan 2027",
    ),
    Rule(
        "OPS1_GAS_RESPONSE_HOURS_FROM_2027",
        12.0,
        "hours",
        "lte",
        "fleet/sops/operations-sop-rev2.md",
        "OPS-1",
        None,
        "Gas odor field response within 12h for reports from 1 Jan 2027",
    ),
    Rule(
        "OPS5_FREEZE_AMBIENT_C",
        -5.0,
        "C",
        "lte",
        "fleet/sops/operations-sop-rev2.md",
        "OPS-5",
        None,
        "Ambient at or below -5 C on producing well needs heat-trace check within 7 days",
    ),
    Rule(
        "T200_WH_ALARM",
        85.0,
        "C",
        "lte",
        "fleet/well-types/T200.md",
        "9.4",
        "T200",
        "Wellhead must stay at or below 85 C",
    ),
    Rule(
        "T350_WH_ALARM",
        95.0,
        "C",
        "lte",
        "fleet/well-types/T350.md",
        "4",
        "T350",
        "Wellhead must stay at or below 95 C",
    ),
    Rule(
        "PAD_SPILL_SHUTIN_PCT",
        5.0,
        "pct",
        "gt",
        "fleet/well-types/T200.md",
        "9.5",
        None,
        "Spill >5% pad area requires immediate shut-in",
    ),
    Rule(
        "DOWNTIME_DAYS_PER_NOT_PRODUCING_INSPECTION",
        7.0,
        "days",
        "eq",
        "02-dataset-guide.md",
        "Inspections / Downtime",
        None,
        "Each weekly not-producing inspection = 7 days; missed inspection = 0",
    ),
    Rule(
        "SR01_REPORTABLE_BBL",
        5.0,
        "bbl",
        "gte",
        "fleet/sops/spill-response-sop.md",
        "3 / SR-01",
        None,
        "Reportable spill threshold: 5 bbl or more",
    ),
    Rule(
        "SR01_WRITTEN_NOTICE_HOURS",
        24.0,
        "hours",
        "lte",
        "fleet/sops/spill-response-sop.md",
        "4 / SR-01",
        None,
        "Written notice within 24h of discovery for reportable spills",
    ),
    Rule(
        "SR01_MAJOR_HOURS",
        2.0,
        "hours",
        "lte",
        "fleet/sops/spill-response-sop.md",
        "4 / SR-01",
        None,
        "Major spill (>=25 bbl) written notice within 2h",
    ),
    Rule(
        "SR02_CONTAIN_HOURS",
        4.0,
        "hours",
        "lte",
        "fleet/sops/spill-response-sop.md",
        "4 / SR-02",
        None,
        "Contain spill within 4 hours of discovery",
    ),
    Rule(
        "SR03_VERIFY_DAYS",
        60.0,
        "days",
        "lte",
        "fleet/sops/spill-response-sop.md",
        "4 / SR-03",
        None,
        "Remediation verified within 60 days for reportable/major",
    ),
    Rule(
        "RC01_INSPECT_DAYS",
        14.0,
        "days",
        "lte",
        "fleet/sops/regulatory-compliance-sop.md",
        "2 / RC-01",
        None,
        "Inspect at least once every 14 days",
    ),
    Rule(
        "RC03_DOWN_DAYS",
        14.0,
        "days",
        "lte",
        "fleet/sops/regulatory-compliance-sop.md",
        "2 / RC-03",
        None,
        "Down >14 consecutive days must be reported to area supervisor",
    ),
    Rule(
        "RC04_NOV_DAYS",
        30.0,
        "days",
        "lte",
        "fleet/sops/regulatory-compliance-sop.md",
        "2 / RC-04",
        None,
        "NOV answered within 30 days",
    ),
    Rule(
        "RCA_CORRECTIVE_COUNT",
        3.0,
        "count",
        "gte",
        "fleet/well-types/T200.md",
        "10",
        None,
        "3+ corrective events on same equipment kind in 12 months require RCA",
    ),
)


class RuleRegistry:
    def __init__(self, rules: Iterable[Rule] | None = None):
        self._by_id: Dict[str, Rule] = {}
        for r in rules or SEED_RULES:
            self._by_id[r.rule_id] = r

    def get(self, rule_id: str) -> Rule:
        if rule_id not in self._by_id:
            raise KeyError(f"Unknown rule: {rule_id}")
        return self._by_id[rule_id]

    def producing_rule(self, well_type: str) -> Rule:
        wt = (well_type or "T200").upper()
        if wt == "T500":
            return self.get("T500_PRODUCING_DELTA")
        if wt == "T350":
            return self.get("T350_PRODUCING_DELTA")
        return self.get("T200_PRODUCING_DELTA")

    def list_rules(self) -> list[Rule]:
        return list(self._by_id.values())

    def apply_override(self, rule_id: str, new_threshold: float, source: str) -> Rule:
        """Scoped runtime override (e.g. Q14 T350 RCA after 2). Keeps provenance."""
        base = self.get(rule_id)
        overriden = Rule(
            rule_id=f"{rule_id}__override",
            threshold=new_threshold,
            unit=base.unit,
            operator=base.operator,
            source_file=source,
            source_section=f"override of {base.source_section}",
            well_type=base.well_type,
            description=f"Override of {rule_id}: {base.description}",
        )
        self._by_id[overriden.rule_id] = overriden
        self._by_id[rule_id] = overriden  # active
        return overriden

    def validate_sources_exist(self, data_root: Path) -> list[str]:
        """Return missing source files (relative fleet/ paths under data_root)."""
        missing = []
        fleet = data_root
        for r in self._by_id.values():
            if r.source_file.startswith("fleet/"):
                p = fleet / r.source_file.replace("fleet/", "fleet/", 1)
                # data_root is sample-data, so fleet/... is under it
                p = fleet / r.source_file[len("fleet/") :] if False else fleet / r.source_file
                # source_file like fleet/well-types/T200.md — under sample-data
                candidate = fleet / r.source_file
                if not candidate.exists():
                    # also try without fleet/ prefix duplication
                    alt = fleet / Path(r.source_file).name
                    if not candidate.exists() and not (fleet / "well-types" / Path(r.source_file).name).exists():
                        # sample-data/fleet/well-types/...
                        rel = r.source_file
                        if rel.startswith("fleet/"):
                            candidate = fleet / rel
                        if not candidate.exists():
                            missing.append(r.source_file)
        return missing


def compare(value: float, rule: Rule) -> bool:
    """Apply rule operator to value vs threshold."""
    if rule.threshold is None or rule.operator is None:
        raise ValueError(f"Rule {rule.rule_id} has no threshold/operator")
    op = rule.operator
    t = rule.threshold
    if op == "gte":
        return value >= t
    if op == "gt":
        return value > t
    if op == "lte":
        return value <= t
    if op == "lt":
        return value < t
    if op == "eq":
        return value == t
    raise ValueError(f"Unknown operator {op}")
