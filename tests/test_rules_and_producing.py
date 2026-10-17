"""Unit tests that do not need a full DB — RuleRegistry + producing math."""
from __future__ import annotations

from assetiq.rules.registry import RuleRegistry, compare
from assetiq.derived.facts import temp_delta, is_producing, parse_containment_hours


def test_t200_threshold_from_manual():
    rules = RuleRegistry()
    r = rules.producing_rule("T200")
    assert r.threshold == 15.0
    assert "T200.md" in r.source_file
    assert r.source_section == "9.3"


def test_t350_threshold_from_manual():
    rules = RuleRegistry()
    r = rules.producing_rule("T350")
    assert r.threshold == 20.0


def test_producing_delta_q1_shape():
    # WELL-0001 latest: 25.6 - 22.4 = 3.2 < 15 → not producing
    delta = temp_delta(25.6, 22.4)
    assert delta == 3.2
    rules = RuleRegistry()
    producing, fact = is_producing(delta, "T200", rules)
    assert producing is False
    assert fact.rule_id == "T200_PRODUCING_DELTA"


def test_hot_day_idle_well_still_not_producing():
    # Q5 style: 51.6 - 43.1 = 8.5 < 15
    delta = temp_delta(51.6, 43.1)
    producing, _ = is_producing(delta, "T200", RuleRegistry())
    assert producing is False


def test_containment_hours_parse():
    text = "The spill was contained after about 7.1 hours using berms and absorbents."
    assert parse_containment_hours(text) == 7.1
    text2 = "The release was contained about 7.1 hours after the inspection."
    assert parse_containment_hours(text2) == 7.1



def test_sr02_rule():
    r = RuleRegistry().get("SR02_CONTAIN_HOURS")
    assert r.threshold == 4.0
    assert compare(7.1, r) is False  # 7.1 is NOT <= 4
