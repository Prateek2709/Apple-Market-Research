# data/

Local data store. Everything here except this file is git-ignored.

- `raw/<source>/<yyyy-mm-dd>/` – pages/JSON exactly as fetched (append-only, never modified)
- `bronze/` – parsed fields, no cleaning
- `silver/` – cleaned, typed, matched to `sku_id` / `price_key`
- `gold/` – weekly feature tables and the final SKU table
- `meta/` – run metadata

Set `MARKET_SIGNALS_DATA_DIR` to keep data elsewhere.
