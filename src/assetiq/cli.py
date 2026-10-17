"""AssetIQ CLI — ingest, ask, eval."""
from __future__ import annotations

import argparse
import json
import sys

from assetiq.config import load_settings
from assetiq.ingest.loader import ingest_dataset
from assetiq.store.schema import make_session_factory
from assetiq.agent.copilot import Copilot
from assetiq.qa.harness import validate_envelope


def cmd_ingest(args: argparse.Namespace) -> int:
    settings = load_settings()
    root = args.path or str(settings.data_root)
    tag = args.tag
    Session, engine = make_session_factory(settings.mysql_url)
    session = Session()
    try:
        stats = ingest_dataset(session, root, dataset_tag=tag, well_limit=args.limit)
        print(json.dumps({"ok": True, "dataset_tag": tag, "stats": stats}, indent=2))
        return 0
    finally:
        session.close()
        engine.dispose()


def cmd_ask(args: argparse.Namespace) -> int:
    settings = load_settings()
    Session, engine = make_session_factory(settings.mysql_url)
    session = Session()
    try:
        bot = Copilot(session, settings)
        env = bot.ask(args.question, user_id=args.user)
        qa = validate_envelope(session, env)
        out = env.to_dict()
        out["qa"] = qa.to_dict()
        print(json.dumps(out, indent=2, default=str))
        return 0 if qa.ok else 2
    finally:
        session.close()
        engine.dispose()


DEMO_PREWARM = [
    "Is WELL-0001 producing oil right now? When was it last inspected, and by whom?",
    "Which wells in Northeast Block 8 are not producing oil right now, and why? Show them in a table.",
    "Which 3 wells in Northeast Block 7 had the most downtime in the last 4 months? Show a bar chart.",
    "How many oil spills has WELL-0001 had in the last 4 years, and how much oil in total? List them in a table.",
    "How many days was WELL-0001 down in 2025?",
]


def cmd_prewarm(args: argparse.Namespace) -> int:
    """Load Gemma into memory and cache deterministic answers for the demo set."""
    import time

    from assetiq.agent.llm import GemmaClient
    from assetiq.cache import put_cached

    settings = load_settings()
    print("prewarm: loading Gemma…")
    t0 = time.perf_counter()
    try:
        llm = GemmaClient(settings)
        reply = llm.prewarm()
        print(f"model={llm.last_model} reply={reply[:80]!r} load_ms={int((time.perf_counter()-t0)*1000)}")
    except Exception as e:
        print(f"model_warm_failed={e} (continuing with facts cache)")

    Session, engine = make_session_factory(settings.mysql_url)
    session = Session()
    try:
        bot = Copilot(session, settings)
        user = args.user
        for q in DEMO_PREWARM:
            t1 = time.perf_counter()
            env = bot.answer_facts(q, user_id=user)
            qa = validate_envelope(session, env)
            out = env.to_dict()
            out["qa"] = qa.to_dict()
            put_cached(session, q, user, out, model=None)
            print(f"cached facts_ms={env.facts_ms} total_ms={int((time.perf_counter()-t1)*1000)} q={q[:56]}…")
        print("prewarm_ok")
        return 0
    finally:
        session.close()
        engine.dispose()


def cmd_gate0(args: argparse.Namespace) -> int:
    settings = load_settings()
    # MySQL
    Session, engine = make_session_factory(settings.mysql_url)
    session = Session()
    try:
        from sqlalchemy import text

        row = session.execute(text("SELECT 1")).scalar()
        print(f"mysql_ok={row}")
    finally:
        session.close()
        engine.dispose()

    # thin vertical slice: ingest WELL-0001 only if needed, compute producing
    Session, engine = make_session_factory(settings.mysql_url)
    session = Session()
    try:
        from pathlib import Path
        from assetiq.ingest.loader import ingest_fleet, ingest_well
        from assetiq.rules.registry import RuleRegistry
        from assetiq.derived.facts import producing_status_now
        from assetiq.store.repo import Repository
        from assetiq.agent.llm import GemmaClient

        ingest_fleet(session, settings.data_root, "sample")
        ingest_well(session, Path(settings.data_root) / "assets" / "WELL-0001", "sample")
        session.commit()
        repo = Repository(session)
        rules = RuleRegistry()
        st = producing_status_now(repo, "WELL-0001", rules)
        print("producing_slice=", json.dumps(st, default=str)[:500])

        llm = GemmaClient(settings)
        # prefer gemini for gate0 confirmation of hosted id
        settings_gemini = settings
        text = llm.complete(
            "Reply briefly.",
            "Say exactly: ASSETIQ_OK and name the well that is the reference well in one short clause.",
        )
        print(f"gemma_model={llm.last_model}")
        print(f"gemma_reply={text[:200]}")
        return 0
    finally:
        session.close()
        engine.dispose()


def cmd_reset_runtime(args: argparse.Namespace) -> int:
    """Clear corrections, private memory, shared notes, conflicts, and answer cache."""
    from sqlalchemy import delete
    from assetiq.store import schema as S
    from assetiq.cache import bump_state_version

    settings = load_settings()
    Session, engine = make_session_factory(settings.mysql_url)
    session = Session()
    try:
        for table in (S.AnswerCache, S.ConflictClaim, S.SharedKnowledge, S.UserMemory, S.Correction):
            session.execute(delete(table))
        session.commit()
        ver = bump_state_version(session)
        print(json.dumps({"ok": True, "state_version": ver, "cleared": True}, indent=2))
        return 0
    finally:
        session.close()
        engine.dispose()


def cmd_eval(args: argparse.Namespace) -> int:
    """Run golden Phase 1+2 eval (facts only)."""
    import runpy
    from pathlib import Path

    script = Path(__file__).resolve().parents[2] / "eval" / "run_eval.py"
    # run as __main__
    glob = runpy.run_path(str(script), run_name="__not_main__")
    return int(glob["main"]())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="assetiq", description="Asset Intelligence Copilot")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p0 = sub.add_parser("gate0", help="MySQL + WELL-0001 slice + one Gemma call")
    p0.set_defaults(func=cmd_gate0)

    pi = sub.add_parser("ingest", help="Idempotent ingest (sample or test tag)")
    pi.add_argument("--path", default=None, help="Path to sample-data (fleet+assets)")
    pi.add_argument("--tag", default="sample", help="dataset_tag (sample|test)")
    pi.add_argument("--limit", type=int, default=None, help="Optional well limit for smoke")
    pi.set_defaults(func=cmd_ingest)

    pa = sub.add_parser("ask", help="Ask a question")
    pa.add_argument("question")
    pa.add_argument("--user", default="U-201", help="user_id from fleet/users.json")
    pa.set_defaults(func=cmd_ask)

    pw = sub.add_parser("prewarm", help="Warm Gemma + cache demo questions for Turbo Mode")
    pw.add_argument("--user", default="U-201", help="user_id for cache keys")
    pw.set_defaults(func=cmd_prewarm)

    pr = sub.add_parser("reset-runtime", help="Clear corrections/memory/conflicts/cache")
    pr.set_defaults(func=cmd_reset_runtime)

    pe = sub.add_parser("eval", help="Run golden 18-question eval (facts)")
    pe.set_defaults(func=cmd_eval)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
