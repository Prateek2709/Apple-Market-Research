# Implementation status

Spec: `docs/iPhone 18 Demand Alt-Data Signal Plan.md`. Update this file at the end of every task.

## Current state
- **Last completed:** Task 2 – active iPhone SKU catalogue (2026-11-03, Claude Code Web), branch `claude/task2-active-sku-catalogue` (branched from Task 1 branch `claude/keen-ramanujan-a6bsaz`; neither is merged to `main` yet).
- **Next:** awaiting Task 3 instructions. Remaining plan step 1 items: Android candidate list per competitor group, aliases, events; then step 2 (source access checks).

## Task log

### Task 1 – Project scaffold ✅
- `pyproject.toml`: Python ≥ 3.11; core deps from the plan (httpx, selectolax, beautifulsoup4, tenacity, pandas, pyarrow, duckdb, rapidfuzz, pydantic, pyyaml); extras `sources`, `browser`, `dev`.
- `market_signals/config.py`: portable project paths, data-layer dirs (`raw/bronze/silver/gold/meta`, override via `MARKET_SIGNALS_DATA_DIR`), `model_key()` and `load_active_scope()`.
- `config/active_scope.yaml`: active and reference-only models exactly as in the plan.
- `.gitignore` (secrets, venvs, data, generated outputs), `.gitattributes` (LF line endings), `.env.example`, `data/README.md`.
- `CLAUDE.md` project rules.
- Tests: `tests/test_config.py` – 11 passed.

### Task 2 – Active iPhone SKU catalogue ✅
- `catalogue/model_specs.yaml`: hand-curated India facts (storage → launch MRP, colours, launch date, predecessor, Apple store status, unverified fields). Single input to the build.
- `market_signals/catalogue.py`: `build_catalogue()`, `validate_catalogue()`, CSV writer/reader, CLI. Scope comes from `config/active_scope.yaml` (add/remove a model there, no code change; a scoped model missing from the specs is an error).
- `catalogue/products.csv`: **111 active SKUs** (28 price_keys, 9 models) = 81 for 18 Pro/Pro Max, 17 Pro/Pro Max, 17, 17e, Air + 15 (iPhone 16) + 15 (iPhone 15).
- `catalogue/reference_models.csv`: 13 price_key rows for reference-only models (14, 16e, 16 Pro, 16 Pro Max). Kept in a separate file because they have no colour grain; products.csv holds only `scope_status=active`.
- Keys: `sku_id = model|storage|colour`, `price_key = model|storage`, `model_key`; storage tokens `128gb`…`1tb`, `2tb`; colour slugs lower-case hyphenated.
- Predecessor mapping by exact storage only: 18 Pro 2TB, 17 Pro Max 2TB and all Air rows map to `none`.
- Commands: `python -m market_signals.catalogue build` (regenerates CSVs) and `... validate` (also fails if CSVs are stale vs the specs).
- Tests: `tests/test_catalogue.py`; full suite **62 passed**.

#### Task 2 verification caveats
- **Apple India (apple.com/in) and most retailer/news hosts were blocked** from the cloud environment (`apple.com`, `croma.com`, `91mobiles.com`, `businesstoday.in`, etc. do not resolve). Nothing was verified on the Apple India configurator. All values come from Indian press/retailer coverage seen through web search on 2026-11-03; each row says so in `verified_source`.
- **Unverified for every row:** Apple configurator confirmation, colour × storage availability (full cross-product assumed), part numbers/ASIN/FSN/Croma/Reliance ids (columns not created yet), `apple_delisted_date` (blank everywhere).
- **Unverified Apple store status:** iPhone 17 Pro Max, iPhone 15 (delisted per plan only); iPhone 14 and 16e `unknown`.
- iPhone 15 and 16 base storage (128/256/512) and colours are now supported by launch coverage, but still not by Apple's configurator, so the plan's `?` stays open.
- Sep 2026 price rises (17, 17e, Air, 16) are not in the catalogue: it stores launch MRP only. Current MRPs belong in collected Apple India observations.
- Naming: the Task 2 brief refers to `docs/market_signal_plan.md`; the file in the repo is `docs/iPhone 18 Demand Alt-Data Signal Plan.md` (used as the spec).
- `generation` for the Air is `air` and tier for base models is `Base`; the plan does not define these, adjust if a different convention is wanted.

## Plan sequence (from the spec)
| # | Step | Status |
|---|------|--------|
| 1 | Finalise catalogue and active-SKU list | iPhone SKUs, reference rows and predecessor mappings done (press-verified); Android candidates and configurator confirmation pending |
| 2 | Verify source access and historical coverage | Not started |
| 3 | Run extraction | Not started |
| 4 | Clean, standardise, curate | Not started |
| 5 | Engineer features | Not started |
| 6 | Construct MS and DP | Not started |
| 7 | Exploratory analysis | Later |

## Open items / blockers
- Allow `apple.com` (and retailer/news hosts) in the environment network settings, or run `build` checks locally on Windows, to confirm configurations on the Apple India configurator and fill part numbers.
- Confirm Apple delisting dates for the 15, 17 Pro and 17 Pro Max.
- Google Trends API alpha application and YouTube API key not yet obtained (manual, owner action).
- Retailer robots.txt/terms checks pending; retailers may block cloud IPs, so first real fetches are better run from the local Windows machine.

## Environment notes
- Developed so far in Claude Code Web (Linux, Python 3.13). Target local: Windows + Claude Desktop.
- After cloning on Windows: create `.venv`, `pip install -e ".[dev]"`, run `python -m pytest`.
