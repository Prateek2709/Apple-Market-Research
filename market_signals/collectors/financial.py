"""Financial context (plan Tier A): only AAPL and USD/INR.

* yfinance: unofficial client library (history(start, end, auto_adjust=False)); end is exclusive.
* Frankfurter: central-bank reference rates, documented time-series form GET /<start>..<end>?from=USD&to=INR
  -> {"rates": {"YYYY-MM-DD": {"INR": value}}}.
Neither has been run live: live_verification required. Frankfurter's base URL is config (the plan cites
frankfurter.app).

Each parsed row keeps market_date and available_ist_date. AAPL: close dated D is available in India on D+1
(plan). Frankfurter: available the same IST evening. For INR=X via yfinance the plan gives no availability
rule, so available_ist_date is None (NA downstream) rather than a guess.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import date, timedelta
from typing import Callable

from .base import Collector, Fetcher, Summary, Target, yesterday_utc


def parse_frankfurter(content: bytes, base: str = "USD", quote: str = "INR") -> list[dict]:
    rates = json.loads(content.decode("utf-8"))["rates"]
    return [{"series": f"{base}{quote}_frankfurter", "market_date": d, "close": float(v[quote]),
             "adj_close": None, "available_ist_date": d} for d, v in sorted(rates.items())]


def parse_yfinance_csv(content: bytes, symbol: str) -> list[dict]:
    rows = []
    for r in csv.DictReader(io.StringIO(content.decode("utf-8"))):
        d = r["Date"][:10]
        avail = (date.fromisoformat(d) + timedelta(days=1)).isoformat() if symbol == "AAPL" else None
        rows.append({"series": symbol, "market_date": d, "close": float(r["Close"]),
                     "adj_close": float(r["Adj Close"]) if r.get("Adj Close") else None,
                     "available_ist_date": avail})
    return rows


def _window(ctx, key: str, default_start: str) -> tuple[date, date] | None:
    end = yesterday_utc(ctx)
    if ctx.since:
        start = date.fromisoformat(ctx.since)
    else:
        covered = ctx.state.get(key)
        start = date.fromisoformat(covered) + timedelta(days=1) if covered else date.fromisoformat(default_start)
    return (start, end) if start <= end else None


class Frankfurter(Collector):
    name = "frankfurter"

    def _target(self, start: date, end: date) -> Target:
        o = self.cfg.opts
        return Target(self.name, f"frankfurter|USDINR|{start}|{end}", f"{o['base_url']}/{start}..{end}",
                      {"from": "USD", "to": "INR"}, ext="json", meta={"start": str(start), "end": str(end)})

    def plan(self) -> list[Target]:
        w = _window(self.ctx, "frankfurter:USDINR", str(self.cfg.opts.get("default_start", "2021-01-01")))
        return [self._target(*w)] if w else []

    def collect(self) -> Summary:
        summary = self._summary(planned=1)
        w = _window(self.ctx, "frankfurter:USDINR", str(self.cfg.opts.get("default_start", "2021-01-01")))
        if not w:
            summary.skipped_up_to_date, summary.status = 1, "ok"
            return summary
        fetcher = Fetcher(self.cfg, self.ctx)
        try:
            out = fetcher.fetch(self._target(*w), validate=lambda c: len(parse_frankfurter(c)) > 0)
        finally:
            fetcher.close()
        if out.ok:
            summary.fetched = 1
            self.ctx.state.set("frankfurter:USDINR", w[1].isoformat())
        else:
            summary.failed, summary.status = 1, "failed"
        return summary


def _default_history(symbol: str, start: date, end: date) -> str:
    """Lazy yfinance call -> CSV text. Imported only when collecting, so tests and planning never need it."""
    import yfinance as yf  # noqa: PLC0415

    df = yf.Ticker(symbol).history(start=start.isoformat(), end=end.isoformat(), auto_adjust=False, actions=False)
    return df.reset_index().to_csv(index=False)


class Yfinance(Collector):
    name = "yfinance"
    history_fn: Callable[[str, date, date], str] = staticmethod(_default_history)

    def _symbols(self) -> list[str]:
        return list(self.cfg.opts.get("symbols") or [])

    def _target(self, symbol: str, start: date, end: date) -> Target:
        return Target(self.name, f"yfinance|{symbol}|{start}|{end}", f"yfinance://{symbol}", ext="csv",
                      meta={"symbol": symbol, "start": str(start), "end": str(end)})

    def plan(self) -> list[Target]:
        out = []
        for s in self._symbols():
            w = _window(self.ctx, f"yfinance:{s}", str(self.cfg.opts.get("default_start", "2021-01-01")))
            if w:
                out.append(self._target(s, *w))
        return out

    def collect(self) -> Summary:
        symbols = self._symbols()
        summary = self._summary(planned=len(symbols))
        fetcher = Fetcher(self.cfg, self.ctx)
        try:
            for s in symbols:
                w = _window(self.ctx, f"yfinance:{s}", str(self.cfg.opts.get("default_start", "2021-01-01")))
                if not w:
                    summary.skipped_up_to_date += 1
                    continue
                fetcher.limiter.wait()
                target = self._target(s, *w)
                try:
                    # yfinance's `end` is exclusive: ask for end + 1 day to include the last closed day.
                    text = type(self).history_fn(s, w[0], w[1] + timedelta(days=1))
                    out = fetcher.record_external(target, text.encode("utf-8"),
                                                  validate=lambda c, s=s: len(parse_yfinance_csv(c, s)) > 0)
                except Exception as exc:  # noqa: BLE001 - unofficial client may raise anything
                    out = fetcher.record_external(target, b"", error=repr(exc))
                if out.ok:
                    summary.fetched += 1
                    self.ctx.state.set(f"yfinance:{s}", w[1].isoformat())
                else:
                    summary.failed += 1
        finally:
            fetcher.close()
        summary.status = "ok" if not summary.failed else ("partial" if summary.fetched else "failed")
        return summary
