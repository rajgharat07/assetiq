"""Gemma 4 backends: Ollama local default, Gemini hosted fallback. Streaming + keep-alive for Turbo."""
from __future__ import annotations

import os
from typing import Iterator, Optional

from assetiq.config import Settings


def _max_tokens() -> int:
    try:
        return int(os.getenv("ASSETIQ_MAX_TOKENS", "320"))
    except ValueError:
        return 320


def _keep_alive() -> str:
    return os.getenv("OLLAMA_KEEP_ALIVE", "30m").strip() or "30m"


class GemmaClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.last_model: Optional[str] = None

    def complete(self, system: str, user: str) -> str:
        backend = self.settings.llm_backend
        if backend == "gemini":
            try:
                return self._gemini(system, user)
            except Exception as e:
                try:
                    return self._ollama(system, user)
                except Exception:
                    raise e
        try:
            return self._ollama(system, user)
        except Exception:
            if self.settings.gemini_api_key:
                return self._gemini(system, user)
            raise

    def stream(self, system: str, user: str) -> Iterator[str]:
        """Yield text chunks as they arrive."""
        backend = self.settings.llm_backend
        if backend == "gemini":
            try:
                yield from self._gemini_stream(system, user)
                return
            except Exception:
                yield from self._ollama_stream(system, user)
                return
        try:
            yield from self._ollama_stream(system, user)
        except Exception:
            if self.settings.gemini_api_key:
                yield from self._gemini_stream(system, user)
            else:
                raise

    def prewarm(self) -> str:
        """Load the model into memory (Ollama keep-alive) with a tiny prompt."""
        return self.complete("Reply with exactly: OK", "OK")

    def _ollama(self, system: str, user: str) -> str:
        from openai import OpenAI

        client = OpenAI(base_url=f"{self.settings.ollama_host.rstrip('/')}/v1/", api_key="ollama")
        model = self.settings.ollama_model
        self.last_model = f"ollama:{model}"
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
            max_tokens=_max_tokens(),
            extra_body={"keep_alive": _keep_alive()},
        )
        return (resp.choices[0].message.content or "").strip()

    def _ollama_stream(self, system: str, user: str) -> Iterator[str]:
        from openai import OpenAI

        client = OpenAI(base_url=f"{self.settings.ollama_host.rstrip('/')}/v1/", api_key="ollama")
        model = self.settings.ollama_model
        self.last_model = f"ollama:{model}"
        stream = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
            max_tokens=_max_tokens(),
            stream=True,
            extra_body={"keep_alive": _keep_alive()},
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta

    def _gemini(self, system: str, user: str) -> str:
        from google import genai

        client = genai.Client(api_key=self.settings.gemini_api_key)
        model = self.settings.gemini_model
        self.last_model = f"gemini:{model}"
        prompt = f"System:\n{system}\n\nUser:\n{user}"
        resp = client.models.generate_content(model=model, contents=prompt)
        return (resp.text or "").strip()

    def _gemini_stream(self, system: str, user: str) -> Iterator[str]:
        from google import genai

        client = genai.Client(api_key=self.settings.gemini_api_key)
        model = self.settings.gemini_model
        self.last_model = f"gemini:{model}"
        prompt = f"System:\n{system}\n\nUser:\n{user}"
        # Prefer streaming API when available; fall back to one-shot chunked by words.
        try:
            stream = client.models.generate_content_stream(model=model, contents=prompt)
            for chunk in stream:
                text = getattr(chunk, "text", None) or ""
                if text:
                    yield text
        except Exception:
            full = self._gemini(system, user)
            # Fake-stream in small chunks so UI still updates progressively
            step = 24
            for i in range(0, len(full), step):
                yield full[i : i + step]
