# Contributing to AssetIQ

Thanks for wanting to help. Keep the thesis intact: **the field records the facts; Gemma explains them.**

## Ground rules

1. Numbers, IDs, dates, and thresholds come from records or manuals — never invent them.
2. Cite the record or `file#section` on every deterministic claim.
3. Formal **corrections** keep the original and apply at read time. A user **claim** that disagrees with data is a conflict, not a silent overwrite.
4. Do not commit `.env`, `/private`, or the raw challenge dataset.

## Dev setup

```powershell
cd assetiq
python -m venv .venv
.\.venv\Scripts\pip install -e ".[dev]"
copy .env.example .env   # fill MYSQL_* and GEMINI_API_KEY
.\.venv\Scripts\assetiq ingest
.\.venv\Scripts\assetiq ask "Is WELL-0001 producing oil right now?"
```

## Good first issues

See [docs/GOOD_FIRST_ISSUES.md](docs/GOOD_FIRST_ISSUES.md).

## Tests

```powershell
.\.venv\Scripts\pytest -q
```
