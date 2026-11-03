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

## Common commands
```bash
python -m pytest                          # offline tests
python -m market_signals.catalogue validate
python run.py list                        # collectors and their status
python run.py collect --dry-run           # show planned requests; no network
python run.py collect --sources wikipedia,frankfurter   # live collection, on demand
```
