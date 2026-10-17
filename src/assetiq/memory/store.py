"""Two-level memory + scoped corrections. Correction != unconfirmed claim."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from assetiq.store import schema as S


class MemoryStore:
    def __init__(self, session: Session):
        self.s = session

    # --- private per-user conversation ---
    def add_turn(
        self,
        user_id: str,
        role: str,
        content: str,
        meta: Optional[dict] = None,
        session_key: str = "default",
    ) -> None:
        self.s.add(
            S.UserMemory(
                user_id=user_id,
                session_key=session_key,
                role=role,
                content=content,
                meta_json=meta,
                created_at=datetime.utcnow(),
            )
        )
        self.s.commit()

    def recent_turns(self, user_id: str, limit: int = 20, session_key: str = "default") -> list[S.UserMemory]:
        from sqlalchemy import select

        return list(
            self.s.scalars(
                select(S.UserMemory)
                .where(S.UserMemory.user_id == user_id, S.UserMemory.session_key == session_key)
                .order_by(S.UserMemory.created_at.desc())
                .limit(limit)
            )
        )[::-1]

    def discussed_wells(self, user_id: str) -> list[str]:
        """Resolve 'the three wells we discussed yesterday' from THIS user's history only.

        Prefer the most recent assistant turn that listed multiple wells (e.g. top-N downtime).
        """
        import re

        turns = self.recent_turns(user_id, limit=50)
        # walk newest → oldest looking for a multi-well assistant answer
        for turn in reversed(turns):
            if turn.role != "assistant":
                continue
            meta = turn.meta_json or {}
            meta_wells = []
            seen_m = set()
            for w in meta.get("wells") or []:
                if w and w not in seen_m:
                    seen_m.add(w)
                    meta_wells.append(w)
            if len(meta_wells) >= 2:
                return meta_wells[:3]
            found = re.findall(r"WELL-\d{4}", turn.content or "")
            # unique preserve order
            uniq = []
            seen = set()
            for w in found:
                if w not in seen:
                    seen.add(w)
                    uniq.append(w)
            if len(uniq) >= 2:
                return uniq[:3]
        # fallback: only if this user discussed multiple wells together
        wells: list[str] = []
        seen = set()
        for turn in turns:
            for m in re.findall(r"WELL-\d{4}", turn.content or ""):
                if m not in seen:
                    seen.add(m)
                    wells.append(m)
        return wells if len(wells) >= 2 else []

    # --- shared well knowledge ---
    def add_shared(
        self,
        asset_id: str,
        author_user_id: str,
        text: str,
        valid_from: Optional[str] = None,
        valid_to: Optional[str] = None,
    ) -> S.SharedKnowledge:
        row = S.SharedKnowledge(
            asset_id=asset_id,
            author_user_id=author_user_id,
            text=text,
            created_at=datetime.utcnow(),
            valid_from=valid_from,
            valid_to=valid_to,
        )
        self.s.add(row)
        self.s.commit()
        from assetiq.cache import bump_state_version

        bump_state_version(self.s)
        return row

    def shared_for(self, asset_id: str) -> list[S.SharedKnowledge]:
        from sqlalchemy import select

        return list(
            self.s.scalars(
                select(S.SharedKnowledge)
                .where(S.SharedKnowledge.asset_id == asset_id)
                .order_by(S.SharedKnowledge.created_at.asc())
            )
        )

    # --- formal corrections (apply in shared read pipeline) ---
    def add_correction(
        self,
        *,
        target_id: str,
        field_name: str,
        original_value: Any,
        corrected_value: Any,
        author_user_id: str,
        reason: str,
        scope: str = "asset",
        scope_key: Optional[str] = None,
        target_type: str = "inspection_field",
    ) -> S.Correction:
        row = S.Correction(
            correction_id=f"CORR-{uuid.uuid4().hex[:10]}",
            target_type=target_type,
            target_id=target_id,
            field_name=field_name,
            original_value=str(original_value) if original_value is not None else None,
            corrected_value=str(corrected_value),
            author_user_id=author_user_id,
            reason=reason,
            scope=scope,
            scope_key=scope_key,
            created_at=datetime.utcnow(),
        )
        self.s.add(row)
        self.s.commit()
        from assetiq.cache import bump_state_version

        bump_state_version(self.s)
        return row

    def add_conflict_claim(
        self,
        author_user_id: str,
        claim_text: str,
        data_side: str,
        asset_id: Optional[str] = None,
    ) -> S.ConflictClaim:
        row = S.ConflictClaim(
            asset_id=asset_id,
            author_user_id=author_user_id,
            claim_text=claim_text,
            data_side=data_side,
            status="unconfirmed",
            created_at=datetime.utcnow(),
        )
        self.s.add(row)
        self.s.commit()
        from assetiq.cache import bump_state_version

        bump_state_version(self.s)
        return row

    def conflicts_for(self, asset_id: str) -> list[S.ConflictClaim]:
        from sqlalchemy import select

        return list(
            self.s.scalars(
                select(S.ConflictClaim)
                .where(S.ConflictClaim.asset_id == asset_id)
                .order_by(S.ConflictClaim.created_at.asc())
            )
        )
