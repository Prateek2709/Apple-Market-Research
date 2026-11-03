# CLAUDE.md – project rules

## Specification
- The approved spec is `docs/iPhone 18 Demand Alt-Data Signal Plan.md`. Follow it; when code and plan disagree, raise it rather than silently diverging.
- Progress and next steps live in `docs/IMPLEMENTATION_STATUS.md`. **Read it at the start of every session and update it at the end of every task.**

## Scope guardrails
- Build an independent external dataset only. Never use, join or infer from the distributor's internal order data.
- Out of scope: forecasting, backtesting, inventory optimisation, dashboards, schedulers/cron/services, DG-specific adjustments.
- Runs are on demand (`python run.py ...` or a notebook). No scheduling code.
- Never fill, interpolate or carry forward unobserved prices/stock/offers. Missing stays NA with a reason; see the plan's "Missing vs zero" table.
- MS and DP are never autoregressive: a week's score never reads earlier MS/DP values.
- Work task by task as instructed. Do not add collectors, features or scoring ahead of the task that asks for them, and do not create empty placeholder modules.

## Portability (cloud now, local Windows + Claude Desktop later)
- Use `pathlib` and paths relative to `market_signals.config.PROJECT_ROOT`; never hard-code absolute paths or `/` / `\` separators.
- Open text files with `encoding="utf-8"` explicitly (Windows defaults differ).
- No cloud-specific dependencies, services or credentials. No shell-only scripts; entry points are Python.
- Secrets come from environment variables / a local `.env` (git-ignored). Template: `.env.example`.
- Data location: `data/` by default, override with `MARKET_SIGNALS_DATA_DIR`.

## Data rules
- `data/raw/` is append-only; raw files are never modified. Everything under `data/` is git-ignored.
- Keys: `sku_id = model|storage|colour`, `price_key = model|storage`, `model_key = model`. Price varies by model × storage, never by colour.
- Weeks are Sunday–Saturday, identified by `week_start`. Timestamps stored in UTC plus IST date.
- Scraping: respect robots.txt and site terms; polite rate limits; stop on any site that prohibits automated access.

## Environment setup
Linux/macOS:
```bash
python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
```
Windows (PowerShell):
```powershell
py -m venv .venv; .venv\Scripts\Activate.ps1; pip install -e ".[dev]"
```
Optional extras: `.[sources]` (API clients), `.[browser]` (Playwright; then `python -m playwright install chromium`).

## Testing and commits
- Run `python -m pytest` before every commit; keep tests offline (no network calls in tests).
- Commit small, descriptive changes; GitHub is the source of truth.
