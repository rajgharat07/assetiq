"""FastAPI surface — thin layer over the engine. Turbo Mode: /ask/stream."""
from __future__ import annotations

import json
import time
from typing import Iterator, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from assetiq.agent.copilot import Copilot
from assetiq.cache import get_cached, put_cached
from assetiq.config import load_settings
from assetiq.qa.harness import validate_envelope
from assetiq.store.repo import Repository
from assetiq.store.schema import make_session_factory

settings = load_settings()
SessionLocal, engine = make_session_factory(settings.mysql_url)

app = FastAPI(title="AssetIQ", version="0.1.0", description="The field records the facts. Gemma explains them.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str
    user_id: str = Field(default="U-201")


class IngestRequest(BaseModel):
    path: Optional[str] = None
    tag: str = "sample"
    limit: Optional[int] = None


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@app.get("/health")
def health():
    return {
        "ok": True,
        "challenge_date": settings.challenge_date.isoformat(),
        "thesis": "The field records the facts. Gemma explains them.",
        "turbo": True,
    }


@app.get("/users")
def users():
    session = SessionLocal()
    try:
        repo = Repository(session)
        return [
            {"user_id": u.user_id, "name": u.name, "role": u.role, "team_id": u.team_id}
            for u in repo.list_users()
        ]
    finally:
        session.close()


@app.post("/ask")
def ask(req: AskRequest):
    session = SessionLocal()
    try:
        cached = get_cached(session, req.question, req.user_id)
        if cached:
            cached["cache_hit"] = True
            return cached
        bot = Copilot(session, settings)
        env = bot.ask(req.question, user_id=req.user_id)
        qa = validate_envelope(session, env)
        out = env.to_dict()
        out["qa"] = qa.to_dict()
        put_cached(session, req.question, req.user_id, out, model=env.model)
        return out
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        session.close()


@app.post("/ask/stream")
def ask_stream(req: AskRequest):
    """SSE: trace -> facts (+ QA) -> token* -> done. Facts never wait on Gemma."""

    def gen() -> Iterator[str]:
        session = SessionLocal()
        t0 = time.perf_counter()
        try:
            cached = get_cached(session, req.question, req.user_id)
            if cached:
                cached["cache_hit"] = True
                trace = list(cached.get("trace") or [])
                yield _sse("trace", {"steps": trace, "facts_ms": cached.get("facts_ms") or 0, "cache_hit": True})
                yield _sse("facts", cached)
                # stream cached summary as one token so UI path stays unified
                summary = cached.get("summary") or ""
                if summary:
                    yield _sse("token", {"text": summary})
                yield _sse(
                    "done",
                    {
                        "model": cached.get("model"),
                        "cache_hit": True,
                        "total_ms": int((time.perf_counter() - t0) * 1000),
                    },
                )
                return

            bot = Copilot(session, settings)
            env = bot.answer_facts(req.question, user_id=req.user_id)
            qa = validate_envelope(session, env)
            facts_payload = env.to_dict()
            facts_payload["qa"] = qa.to_dict()

            yield _sse(
                "trace",
                {"steps": env.trace, "facts_ms": env.facts_ms, "cache_hit": False},
            )
            yield _sse("facts", facts_payload)

            # Stream Gemma on top of already-correct facts
            import os

            skip = os.getenv("ASSETIQ_SKIP_LLM", "").strip() in ("1", "true", "yes")
            explanation_parts: list[str] = []
            if not skip:
                try:
                    for chunk in bot.explain_stream(req.question, env):
                        explanation_parts.append(chunk)
                        yield _sse("token", {"text": chunk})
                    if explanation_parts:
                        from assetiq.agent.copilot import sanitize_llm_summary

                        raw = "".join(explanation_parts).strip()
                        env.summary = sanitize_llm_summary(raw) or env.summary
                        env.model = bot.llm.last_model
                        # Push cleaned summary so UI replaces any raw markdown tokens
                        if env.summary and env.summary != raw:
                            yield _sse("token", {"text": "\n", "replace": True, "full": env.summary})
                except Exception as e:
                    env.warnings.append(f"Gemma stream failed ({e}); keeping deterministic summary.")
                    yield _sse("token", {"text": env.summary})
            else:
                yield _sse("token", {"text": env.summary})

            bot.remember_turn(req.user_id, req.question, env)
            out = env.to_dict()
            out["qa"] = qa.to_dict()
            put_cached(session, req.question, req.user_id, out, model=env.model)
            yield _sse(
                "done",
                {
                    "model": env.model,
                    "cache_hit": False,
                    "warnings": env.warnings,
                    "summary": env.summary,
                    "total_ms": int((time.perf_counter() - t0) * 1000),
                },
            )
        except Exception as e:
            yield _sse("error", {"detail": str(e)})
        finally:
            session.close()

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/ingest")
def ingest(req: IngestRequest):
    from pathlib import Path

    from assetiq.ingest.loader import ingest_dataset

    session = SessionLocal()
    try:
        root = Path(req.path) if req.path else settings.data_root
        if req.tag == "test" and settings.test_data_root and not req.path:
            root = settings.test_data_root
        stats = ingest_dataset(session, root, dataset_tag=req.tag, well_limit=req.limit)
        return {"ok": True, "tag": req.tag, "stats": stats}
    finally:
        session.close()
