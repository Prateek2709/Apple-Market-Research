"""Wikipedia pageviews collector (plan Tier A). Global attention proxy, not India-specific.

Implemented from the public Wikimedia REST pageviews documentation:
  GET <base>/<project>/<access>/<agent>/<article>/daily/<YYYYMMDD>/<YYYYMMDD>
  -> {"items": [{"article", "timestamp": "YYYYMMDD00", "views", ...}]}
Never run live: live_verification required. Article titles in config are unverified; a 404 is logged as a
failed fetch and does not advance the incremental window.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from urllib.parse import quote

from .base import Collector, Fetcher, Summary, Target, yesterday_utc


def parse_pageviews(content: bytes) -> list[dict]:
    items = json.loads(content.decode("utf-8"))["items"]
    return [{"article": i["article"], "date": f"{i['timestamp'][:4]}-{i['timestamp'][4:6]}-{i['timestamp'][6:8]}",
             "views": int(i["views"]), "access": i.get("access", ""), "agent": i.get("agent", "")} for i in items]


class Wikipedia(Collector):
    name = "wikipedia"

    def _window(self, title: str) -> tuple[date, date] | None:
        end = yesterday_utc(self.ctx)  # today's counts are incomplete
        if self.ctx.since:
            start = date.fromisoformat(self.ctx.since)
        else:
            covered = self.ctx.state.get(f"wikipedia:{title}")
            start = (date.fromisoformat(covered) + timedelta(days=1)) if covered else date.fromisoformat(
                str(self.cfg.opts.get("default_start", "2015-07-01")))
        return (start, end) if start <= end else None

    def _target(self, title: str, start: date, end: date) -> Target:
        o = self.cfg.opts
        url = (f"{o['base_url']}/{o.get('project', 'en.wikipedia')}/{o.get('access', 'all-access')}/"
               f"{o.get('agent', 'user')}/{quote(title, safe='')}/daily/{start:%Y%m%d}/{end:%Y%m%d}")
        return Target(self.name, f"wikipedia|{title}|{start}|{end}", url, ext="json",
                      meta={"article": title, "start": start.isoformat(), "end": end.isoformat()})

    def plan(self) -> list[Target]:
        out = []
        for title in self.cfg.opts.get("articles") or []:
            w = self._window(title)
            if w:
                out.append(self._target(title, *w))
        return out

    def collect(self) -> Summary:
        titles = list(self.cfg.opts.get("articles") or [])
        summary = self._summary(planned=len(titles))
        fetcher = Fetcher(self.cfg, self.ctx)
        try:
            for title in titles:
                w = self._window(title)
                if not w:
                    summary.skipped_up_to_date += 1
                    continue
                out = fetcher.fetch(self._target(title, *w), validate=lambda c: len(parse_pageviews(c)) > 0)
                if out.ok:
                    summary.fetched += 1
                    self.ctx.state.set(f"wikipedia:{title}", w[1].isoformat())
                else:
                    summary.failed += 1
        finally:
            fetcher.close()
        summary.status = "ok" if not summary.failed else ("partial" if summary.fetched else "failed")
        if not titles:
            summary.status, summary.note = "skipped", "no articles configured"
        return summary
