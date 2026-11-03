# Implementation status

Spec: `docs/iPhone 18 Demand Alt-Data Signal Plan.md`. Update this file at the end of every task.

## Current state
- **Last completed:** Task 1 – project scaffold (2026-11-03, Claude Code Web).
- **Next:** awaiting Task 2 instructions. Per the plan's implementation sequence, step 1 is the independent catalogue (`catalogue/products.csv`, predecessor mappings, Android candidates).

## Task log

### Task 1 – Project scaffold ✅
- `pyproject.toml`: Python ≥ 3.11; core deps from the plan (httpx, selectolax, beautifulsoup4, tenacity, pandas, pyarrow, duckdb, rapidfuzz, pydantic, pyyaml); extras `sources`, `browser`, `dev`.
- `market_signals/config.py`: portable project paths, data-layer dirs (`raw/bronze/silver/gold/meta`, override via `MARKET_SIGNALS_DATA_DIR`), `model_key()` and `load_active_scope()`.
- `config/active_scope.yaml`: active and reference-only models exactly as in the plan.
- `.gitignore` (secrets, venvs, data, generated outputs), `.gitattributes` (LF line endings), `.env.example`, `data/README.md`.
- `CLAUDE.md` project rules.
- Tests: `tests/test_config.py` – 11 passed.

## Plan sequence (from the spec)
| # | Step | Status |
|---|------|--------|
| 1 | Finalise catalogue and active-SKU list | Not started (scope config done) |
| 2 | Verify source access and historical coverage | Not started |
| 3 | Run extraction | Not started |
| 4 | Clean, standardise, curate | Not started |
| 5 | Engineer features | Not started |
| 6 | Construct MS and DP | Not started |
| 7 | Exploratory analysis | Later |

## Open items / blockers
- iPhone 15 and 16 base storage and colours still unverified (plan marks them `?`).
- Google Trends API alpha application and YouTube API key not yet obtained (manual, owner action).
- Retailer robots.txt/terms checks pending; retailers may block cloud IPs, so first real fetches are better run from the local Windows machine.

## Environment notes
- Developed so far in Claude Code Web (Linux, Python 3.13). Target local: Windows + Claude Desktop.
- After cloning on Windows: create `.venv`, `pip install -e ".[dev]"`, run `python -m pytest`.
