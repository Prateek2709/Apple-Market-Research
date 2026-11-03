"""Wayback Machine collector (plan Tier A): archived snapshots of Apple/retailer pages for past MRP/prices.

Implemented from the public CDX Server API documentation (parameters url, from, to, output=json, fl,
filter, collapse; first JSON row is the header) and the raw-snapshot URL form /web/<timestamp>id_/<url>.
Never run against the live service: live_verification required.

Incremental: per page URL the covered-through timestamp and the list of snapshots already downloaded are
kept in state, so each snapshot is fetched once. Snapshot downloads per run are capped by max_snapshots_per_run.
CDX pagination (resumeKey) is not used; windows are bounded with from/to and the response is limited by `limit`.
"""

from __future__ import annotations

import json

from .base import Collector, Fetcher, Summary, Target, short_hash
from .retail import load_listings


def parse_cdx(content: bytes) -> list[dict[str, str]]:
    """CDX output=json -> list of dicts keyed by the header row. Empty result is `[]`."""
    rows = json.loads(content.decode("utf-8") or "[]")
    if not rows:
        return []
    header, body = rows[0], rows[1:]
    return [dict(zip(header, r)) for r in body]


class Wayback(Collector):
    name = "wayback"
    listings_path = None

    def _urls(self) -> list[dict[str, str]]:
        wanted = set(self.cfg.opts.get("url_sources") or [])
        return [r for r in load_listings(self.listings_path) if r["source"] in wanted]

    def _cdx_target(self, row: dict[str, str]) -> Target:
        key = f"cdx|{row['url']}"
        state = self.ctx.state.get(f"wayback:{short_hash(row['url'])}", {})
        params = {"url": row["url"], "output": "json", "fl": "timestamp,original,mimetype,statuscode,digest,length",
                  "filter": "statuscode:200", "collapse": "digest", "limit": int(self.cfg.opts.get("cdx_limit", 5000))}
        start = (self.ctx.since or "").replace("-", "") or state.get("covered_through", "")
        if start:
            params["from"] = start[:8]
        params["to"] = self.ctx.now().strftime("%Y%m%d")
        return Target(self.name, key, self.cfg.opts["cdx_url"], params, ext="json",
                      meta={"page_source": row["source"], "page_url": row["url"], "price_key": row["price_key"],
                            "listing_id": row["listing_id"]})

    def plan(self) -> list[Target]:
        return [self._cdx_target(r) for r in self._urls()]

    def collect(self) -> Summary:
        rows = self._urls()
        summary = self._summary(planned=len(rows))
        if not rows:
            summary.status, summary.note = "skipped", "no listings for configured url_sources"
            return summary
        fetcher = Fetcher(self.cfg, self.ctx)
        budget = int(self.cfg.opts.get("max_snapshots_per_run", 50))
        try:
            for row in rows:
                state_key = f"wayback:{short_hash(row['url'])}"
                state = self.ctx.state.get(state_key, {"downloaded": [], "covered_through": ""})
                target = self._cdx_target(row)
                out = fetcher.fetch(target, validate=lambda c: isinstance(parse_cdx(c), list))
                if not out.ok:
                    summary.failed += 1
                    continue
                summary.fetched += 1
                snaps = parse_cdx(out.content)
                done = set(state["downloaded"])
                complete = True
                for snap in snaps:
                    ts = snap["timestamp"]
                    if ts in done:
                        summary.skipped_up_to_date += 1
                        continue
                    if budget <= 0:
                        complete = False
                        break
                    budget -= 1
                    snap_url = self.cfg.opts["snapshot_url_template"].format(timestamp=ts, original=snap["original"])
                    got = fetcher.fetch(Target(self.name, f"snap|{row['url']}|{ts}", snap_url, ext="html",
                                               meta={"snapshot_timestamp": ts, "page_url": row["url"],
                                                     "page_source": row["source"], "price_key": row["price_key"],
                                                     "digest": snap.get("digest", "")}))
                    if got.ok:
                        summary.fetched += 1
                        done.add(ts)
                    else:
                        summary.failed += 1
                        complete = False
                state["downloaded"] = sorted(done)
                if complete:  # only advance the window when every listed snapshot is in hand
                    state["covered_through"] = self.ctx.now().strftime("%Y%m%d")
                self.ctx.state.set(state_key, state)
        finally:
            fetcher.close()
        summary.status = "ok" if not summary.failed else ("partial" if summary.fetched else "failed")
        return summary
