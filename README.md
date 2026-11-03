# Apple-Market-Research

Independent external market-signal dataset for the Indian iPhone market, producing two interpretable weekly indicators: **Overall Market Sentiment (MS)** and **Demand Pressure (DP)**.

- Spec: [`docs/iPhone 18 Demand Alt-Data Signal Plan.md`](docs/iPhone%2018%20Demand%20Alt-Data%20Signal%20Plan.md)
- Progress: [`docs/IMPLEMENTATION_STATUS.md`](docs/IMPLEMENTATION_STATUS.md)
- Working rules: [`CLAUDE.md`](CLAUDE.md)

## Setup
Linux/macOS:
```bash
python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
```
Windows (PowerShell):
```powershell
py -m venv .venv; .venv\Scripts\Activate.ps1; pip install -e ".[dev]"
```
Extras: `.[sources]` (yfinance), `.[curation]` (parsing/silver libraries, later), `.[browser]` (Playwright, later).

## Layout
```
run.py                 single entry point
code/scraping/         collectors, fetch utilities, SKU matching, catalogue builder (package `scraping`)
config/                sources.yaml, active_scope.yaml, model_specs.yaml, products.csv, reference_models.csv, listings.csv
data/raw|processed|final   runtime outputs (git-ignored; created when a run writes them)
docs/                  approved plan, implementation status
tests/                 offline tests
```

## Common commands
```bash
python -m pytest                          # offline tests
python run.py catalogue validate          # check config/products.csv against config/model_specs.yaml
python run.py list                        # collectors and their status
python run.py collect --dry-run           # show planned requests; no network
python run.py collect --sources wikipedia,frankfurter   # live collection, on demand
```
