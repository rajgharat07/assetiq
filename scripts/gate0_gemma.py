"""Gate 0: one real hosted Gemma 4 call. Honest — prints model id + reply."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

api_key = os.getenv("GEMINI_API_KEY", "").strip()
model = os.getenv("GEMINI_MODEL", "gemma-4-26b-a4b-it").strip()
if not api_key:
    print("FAIL: GEMINI_API_KEY missing")
    sys.exit(1)

from google import genai

client = genai.Client(api_key=api_key)
resp = client.models.generate_content(model=model, contents="Reply with exactly: ASSETIQ_OK")
text = (resp.text or "").strip()
print(f"model={model}")
print(f"reply={text}")
if "ASSETIQ_OK" not in text and "OK" not in text.upper():
    print("WARN: unexpected reply shape (still a real call)")
sys.exit(0)
