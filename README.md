# Apple-Market-Research

Independent external market-signal dataset for the Indian iPhone market, producing two interpretable weekly indicators: **Overall Market Sentiment (MS)** and **Demand Pressure (DP)**.

- Spec: [`docs/iPhone 18 Demand Alt-Data Signal Plan.md`](docs/iPhone%2018%20Demand%20Alt-Data%20Signal%20Plan.md)
- Progress: [`docs/IMPLEMENTATION_STATUS.md`](docs/IMPLEMENTATION_STATUS.md)
- Working rules: [`CLAUDE.md`](CLAUDE.md)

## Setup
```bash
python -m venv .venv
. .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m pytest
```
