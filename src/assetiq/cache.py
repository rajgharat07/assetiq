"""Answer cache for Turbo Mode — invalidate when state_version bumps."""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from assetiq.store import schema as S


def cache_enabled() -> bool:
    return os.getenv("ASSETIQ_CACHE", "1").strip().lower() not in ("0", "false", "no", "off")


def normalize_question(q: str) -> str:
    return re.sub(r"\s+", " ", (q or "").strip().lower())


def make_cache_key(question: str, user_id: str, dataset_tag: str, state_version: int) -> str:
    raw = f"{normalize_question(question)}|{user_id}|{dataset_tag}|{state_version}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:48]


def get_state_version(session: Session) -> int:
    row = session.get(S.AppState, 1)
    if row is None:
        row = S.AppState(id=1, state_version=1)
        session.add(row)
        session.commit()
    return int(row.state_version or 1)


def bump_state_version(session: Session) -> int:
    row = session.get(S.AppState, 1)
    if row is None:
        row = S.AppState(id=1, state_version=1)
        session.add(row)
    row.state_version = int(row.state_version or 1) + 1
    session.commit()
    return int(row.state_version)


def get_cached(
    session: Session,
    question: str,
    user_id: str,
    dataset_tag: str = "sample",
) -> Optional[dict[str, Any]]:
    if not cache_enabled():
        return None
    ver = get_state_version(session)
    key = make_cache_key(question, user_id, dataset_tag, ver)
    row = session.get(S.AnswerCache, key)
    if row is None or row.state_version != ver:
        return None
    return dict(row.envelope_json or {})


def put_cached(
    session: Session,
    question: str,
    user_id: str,
    envelope: dict[str, Any],
    model: Optional[str] = None,
    dataset_tag: str = "sample",
) -> str:
    if not cache_enabled():
        return ""
    ver = get_state_version(session)
    key = make_cache_key(question, user_id, dataset_tag, ver)
    row = session.get(S.AnswerCache, key)
    if row is None:
        row = S.AnswerCache(cache_key=key)
        session.add(row)
    row.question = question
    row.user_id = user_id
    row.dataset_tag = dataset_tag
    row.state_version = ver
    row.envelope_json = envelope
    row.model = model
    row.created_at = datetime.utcnow()
    session.commit()
    return key
