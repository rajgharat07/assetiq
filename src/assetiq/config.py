"""Runtime config from .env. Challenge date is never the laptop clock."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


@dataclass(frozen=True)
class Settings:
    mysql_host: str
    mysql_port: int
    mysql_user: str
    mysql_password: str
    mysql_database: str
    data_root: Path
    test_data_root: Optional[Path]
    challenge_date: date
    gemini_api_key: str
    gemini_model: str
    ollama_host: str
    ollama_model: str
    ollama_embed_model: str
    llm_backend: str
    chroma_path: Path

    @property
    def mysql_url(self) -> str:
        # URL-encode password — chars like # @ break unquoted DSNs
        from urllib.parse import quote_plus

        user = quote_plus(self.mysql_user)
        password = quote_plus(self.mysql_password)
        return (
            f"mysql+pymysql://{user}:{password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            "?charset=utf8mb4"
        )


def load_settings() -> Settings:
    raw_date = _env("CHALLENGE_DATE", "2026-10-17")
    challenge = date.fromisoformat(raw_date)

    test_root = _env("ASSETIQ_TEST_DATA_ROOT")
    data_root = Path(
        _env(
            "ASSETIQ_DATA_ROOT",
            r"C:\Users\DELL\Desktop\flytbase-ahc-swe-asset-intelligence-dataset\sample-data",
        )
    )

    return Settings(
        mysql_host=_env("MYSQL_HOST", "127.0.0.1"),
        mysql_port=int(_env("MYSQL_PORT", "3306")),
        mysql_user=_env("MYSQL_USER", "root"),
        mysql_password=_env("MYSQL_PASSWORD", ""),
        mysql_database=_env("MYSQL_DATABASE", "assetiq"),
        data_root=data_root,
        test_data_root=Path(test_root) if test_root else None,
        challenge_date=challenge,
        gemini_api_key=_env("GEMINI_API_KEY"),
        gemini_model=_env("GEMINI_MODEL", "gemma-4-26b-a4b-it"),
        ollama_host=_env("OLLAMA_HOST", "http://127.0.0.1:11434"),
        ollama_model=_env("OLLAMA_MODEL", "gemma4:e4b"),
        ollama_embed_model=_env("OLLAMA_EMBED_MODEL", "nomic-embed-text"),
        llm_backend=_env("ASSETIQ_LLM_BACKEND", "ollama").lower(),
        chroma_path=ROOT / "data" / "chroma",
    )


def challenge_datetime(settings: Optional[Settings] = None) -> datetime:
    """End-of-day UTC for the challenge 'today'."""
    s = settings or load_settings()
    return datetime(s.challenge_date.year, s.challenge_date.month, s.challenge_date.day, 23, 59, 59)
