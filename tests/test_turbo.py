"""Turbo Mode: cache keys, state bumps, trace from real evidence, answer_facts speed."""
from __future__ import annotations

from assetiq.agent.copilot import build_trace
from assetiq.agent.envelope import AnswerEnvelope, Claim, VisualSpec
from assetiq.cache import make_cache_key, normalize_question


def test_normalize_question_stable():
    assert normalize_question("  Hello   WELL-0001  ") == normalize_question("hello well-0001")


def test_cache_key_changes_with_state_version():
    a = make_cache_key("Is WELL-0001 producing?", "U-201", "sample", 1)
    b = make_cache_key("Is WELL-0001 producing?", "U-201", "sample", 2)
    c = make_cache_key("Is WELL-0001 producing?", "U-201", "sample", 1)
    assert a == c
    assert a != b


def test_build_trace_only_uses_real_refs():
    env = AnswerEnvelope(
        question="Is WELL-0001 producing oil right now?",
        summary="not producing",
        claims=[
            Claim(
                text="not producing",
                claim_type="deterministic_fact",
                evidence=["INS-0001-0203", "fleet/well-types/T200.md#9.3"],
                rule_id="T200_PRODUCING_DELTA",
            )
        ],
        visual=VisualSpec(type="status_card", title="WELL-0001"),
        citations=["INS-0001-0203"],
    )
    steps = build_trace(env)
    joined = " | ".join(steps)
    assert "INS-0001-0203" in joined
    assert "T200" in joined or "T200_PRODUCING_DELTA" in joined
    assert "status card" in joined
    # never invent a fake inspection id
    assert "INS-9999" not in joined


def test_answer_facts_q1_fast_and_correct():
    import time
    import os

    os.environ["ASSETIQ_SKIP_LLM"] = "1"
    from assetiq.config import load_settings
    from assetiq.store.schema import make_session_factory
    from assetiq.agent.copilot import Copilot

    settings = load_settings()
    Session, engine = make_session_factory(settings.mysql_url)
    session = Session()
    try:
        bot = Copilot(session, settings)
        t0 = time.perf_counter()
        env = bot.answer_facts(
            "Is WELL-0001 producing oil right now? When was it last inspected, and by whom?",
            user_id="U-201",
        )
        elapsed = time.perf_counter() - t0
        assert env.claims, "expected claims"
        producing = None
        for c in env.claims:
            if c.value is False or (isinstance(c.value, bool) and c.value is False):
                producing = False
                break
            if "not producing" in (c.text or "").lower():
                producing = False
                break
        assert producing is False
        assert any("INS-0001-0203" in (e or "") for c in env.claims for e in (c.evidence or []))
        assert env.trace
        assert env.facts_ms is not None
        # generous bound — machine load varies; still must not look like LLM wait
        assert elapsed < 5.0, f"answer_facts too slow: {elapsed:.2f}s"
    finally:
        session.close()
        engine.dispose()


def test_cache_roundtrip_and_invalidation():
    from assetiq.config import load_settings
    from assetiq.store.schema import make_session_factory
    from assetiq.cache import get_cached, put_cached, bump_state_version, get_state_version

    settings = load_settings()
    Session, engine = make_session_factory(settings.mysql_url)
    session = Session()
    try:
        q = "Turbo cache probe WELL-0001 producing?"
        user = "U-CACHE-TEST"
        payload = {
            "question": q,
            "summary": "probe",
            "claims": [],
            "visual": {"type": "none"},
            "citations": [],
            "trace": ["Scoped to WELL-0001"],
            "qa": {"ok": True},
        }
        put_cached(session, q, user, payload, model=None)
        hit = get_cached(session, q, user)
        assert hit is not None
        assert hit["summary"] == "probe"
        before = get_state_version(session)
        after = bump_state_version(session)
        assert after == before + 1
        miss = get_cached(session, q, user)
        assert miss is None, "cache must miss after state_version bump"
    finally:
        session.close()
        engine.dispose()
