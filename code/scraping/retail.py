"""Retail and spec-site collectors: Apple India, Amazon.in, Flipkart, Croma, Reliance Digital, Vijay Sales,
and the Tier B sites Smartprix, 91mobiles, GSMArena.

STATUS: fetch_only. These collectors read the pages listed in config/listings.csv, check robots.txt and
the per-source gates in config/sources.yaml, and store each response unmodified in the raw layer with
provenance. They do NOT parse pages. The plan's price_obs/offer_obs/stock/delivery/rating/review fields
need each retailer's real markup, and no selector or embedded-JSON path is written here because none has
been seen. parse_page() raises IncompleteCollector until a real saved page exists to write it against
(save one with `python run.py collect --sources <retailer>` once the terms check is done).

Known gaps that also need a live page: pin-code selection for delivery/stock, colour-level listings,
review pagination, "bought in past month" badges, seller selection.
"""

from __future__ import annotations

import csv
from pathlib import Path

from scraping import settings

from .base import Collector, IncompleteCollector, Summary, Target

LISTINGS_PATH: Path = settings.CONFIG_DIR / "listings.csv"
LISTING_COLUMNS = ["source", "url", "listing_id", "price_key", "sku_id", "pin_code", "page_type", "label"]
PAGE_TYPES = {"product", "store", "ranking", "spec"}


def load_listings(path: Path | None = None) -> list[dict[str, str]]:
    """Read config/listings.csv (hand-maintained list of pages to capture). Header-only is valid."""
    path = path or LISTINGS_PATH
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != LISTING_COLUMNS:
            raise ValueError(f"{path.name} columns must be exactly {LISTING_COLUMNS}, got {reader.fieldnames}")
        rows = [{k: (v or "").strip() for k, v in row.items()} for row in reader]
    for i, row in enumerate(rows, start=2):
        if not row["source"] or not row["url"]:
            raise ValueError(f"{path.name} line {i}: source and url are required")
        if row["page_type"] and row["page_type"] not in PAGE_TYPES:
            raise ValueError(f"{path.name} line {i}: page_type must be one of {sorted(PAGE_TYPES)}")
    return rows


def validate_listings(rows: list[dict[str, str]], price_keys: set[str], sku_ids: set[str]) -> list[str]:
    """Check listings against the catalogue. price_key/sku_id may be blank (e.g. Android or ranking pages)."""
    errors = []
    seen = set()
    for i, row in enumerate(rows, start=2):
        if (row["source"], row["url"]) in seen:
            errors.append(f"line {i}: duplicate {row['source']} url")
        seen.add((row["source"], row["url"]))
        if row["price_key"] and row["price_key"] not in price_keys:
            errors.append(f"line {i}: unknown price_key {row['price_key']}")
        if row["sku_id"] and row["sku_id"] not in sku_ids:
            errors.append(f"line {i}: unknown sku_id {row['sku_id']}")
    return errors


class RetailCollector(Collector):
    implementation = "fetch_only"
    live_verification = "required (parser not written; no selectors known)"
    listings_path: Path | None = None  # tests override

    def _rows(self) -> list[dict[str, str]]:
        return [r for r in load_listings(self.listings_path) if r["source"] == self.name]

    def plan(self) -> list[Target]:
        return [
            Target(source=self.name, key=f"{self.name}|{r['url']}", url=r["url"], ext="html",
                   meta={k: r[k] for k in ("listing_id", "price_key", "sku_id", "pin_code", "page_type", "label")})
            for r in self._rows()
        ]

    def collect(self) -> Summary:
        from .base import Fetcher  # local import keeps module import cheap

        targets = self.plan()
        summary = self._summary(planned=len(targets))
        if not targets:
            summary.status, summary.note = "skipped", f"no {self.name} rows in config/listings.csv"
            return summary
        fetcher = Fetcher(self.cfg, self.ctx)
        try:
            for target in targets:  # one fetch per listing per run (plan)
                outcome = fetcher.fetch(target)
                if outcome.ok:
                    summary.fetched += 1
                else:
                    summary.failed += 1
        finally:
            fetcher.close()
        summary.status = "ok" if not summary.failed else ("partial" if summary.fetched else "failed")
        summary.note = "raw pages stored; parser not implemented"
        return summary

    @staticmethod
    def parse_page(content: bytes) -> dict:
        raise IncompleteCollector(
            "No page parser: retailer markup has not been inspected. Save a real page with the fetch-only "
            "collector, then write the parser against it.")


class AppleIn(RetailCollector):
    name = "apple_in"


class AmazonIn(RetailCollector):
    name = "amazon_in"


class Flipkart(RetailCollector):
    name = "flipkart"


class Croma(RetailCollector):
    name = "croma"


class RelianceDigital(RetailCollector):
    name = "reliance_digital"


class VijaySales(RetailCollector):
    name = "vijay_sales"


class Smartprix(RetailCollector):
    name = "smartprix"


class Mobiles91(RetailCollector):
    name = "mobiles91"


class Gsmarena(RetailCollector):
    name = "gsmarena"
