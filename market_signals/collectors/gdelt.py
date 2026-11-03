"""GDELT DOC 2.0 collector (plan Tier A): Indian news volume and tone on iPhone price/launch stories.

Implemented from public GDELT DOC API documentation (mode=timelinevol|timelinetone, format=json,
startdatetime/enddatetime as YYYYMMDDHHMMSS). The expected response is
{"timeline": [{"series": ..., "data": [{"date": "YYYYMMDDTHHMMSSZ", "value": n}]}]}.
This shape and the sourcecountry query operator in config are from memory of the docs and have NOT been seen
live: live_verification required. The DOC API only returns a rolling ~3 months, so the window start is
clamped to that; older history needs the BigQuery route (not implemented).
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from .base import Collector, Fetcher, Summary, Target, yesterday_utc

ROLLING_DAYS = 90


def parse_timeline(content: bytes) -> list[dict]:
    rows = []
    for series in json.loads(content.decode("utf-8"))["timeline"]:
        for pt in series["data"]:
            d = pt["date"]
            rows.append({"series": series.get("series", ""), "date": f"{d[:4]}-{d[4:6]}-{d[6:8]}",
                         "value": float(pt["value"])})
    return rows


class Gdelt(Collector):
    name = "gdelt"

    def _window(self, qname: str, mode: str):
        end = yesterday_utc(self.ctx)
        floor = self.ctx.now().date() - timedelta(days=ROLLING_DAYS)
        if self.ctx.since:
            start = date.fromisoformat(self.ctx.since)
        else:
            covered = self.ctx.state.get(f"gdelt:{qname}:{mode}")
            start = date.fromisoformat(covered) + timedelta(days=1) if covered else floor
        start = max(start, floor)
        return (start, end) if start <= end else None

    def _jobs(self):
        for q in self.cfg.opts.get("queries") or []:
            for mode in self.cfg.opts.get("modes") or ["timelinevol", "timelinetone"]:
                yield q["name"], q["query"], mode

    def _target(self, qname: str, query: str, mode: str, start: date, end: date) -> Target:
        params = {"query": query, "mode": mode, "format": "json",
                  "startdatetime": f"{start:%Y%m%d}000000", "enddatetime": f"{end:%Y%m%d}235959"}
        return Target(self.name, f"gdelt|{qname}|{mode}|{start}|{end}", self.cfg.opts["base_url"], params,
                      ext="json", meta={"query_name": qname, "mode": mode, "start": str(start), "end": str(end)})

    def plan(self) -> list[Target]:
        return [self._target(n, q, m, *w) for n, q, m in self._jobs() if (w := self._window(n, m))]

    def collect(self) -> Summary:
        jobs = list(self._jobs())
        summary = self._summary(planned=len(jobs))
        if not jobs:
            summary.status, summary.note = "skipped", "no queries configured"
            return summary
        fetcher = Fetcher(self.cfg, self.ctx)
        try:
            for n, q, m in jobs:
                w = self._window(n, m)
                if not w:
                    summary.skipped_up_to_date += 1
                    continue
                out = fetcher.fetch(self._target(n, q, m, *w), validate=lambda c: len(parse_timeline(c)) > 0)
                if out.ok:
                    summary.fetched += 1
                    self.ctx.state.set(f"gdelt:{n}:{m}", w[1].isoformat())
                else:
                    summary.failed += 1
        finally:
            fetcher.close()
        summary.status = "ok" if not summary.failed else ("partial" if summary.fetched else "failed")
        return summary
