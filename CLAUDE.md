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

## Collectors
- Never write an HTML selector, API endpoint or response schema that has not been seen in a real response or official documentation. If it cannot be done reliably, ship a clearly marked incomplete implementation (see `collectors/retail.py`, `collectors/trends.py`).
- Do not run live collection, call live APIs or generate datasets unless the task explicitly asks. Tests use only small, labelled in-memory fixtures and mocked HTTP.
- Retail/scraped sources stay `enabled: false, terms_checked: false` in `config/sources.yaml` until their robots.txt and terms have been reviewed.
- Secrets (API keys) are request parameters listed in `Target.secret_params`, so they never reach logs or provenance files.

## Testing and commits
- Setup commands are in README.md. Run `python -m pytest` before every commit; keep tests offline (no network calls in tests).
- Commit small, descriptive changes; GitHub is the source of truth.
