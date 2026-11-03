"""YouTube Data API v3 collector (plan Tier A): review/unboxing videos, view snapshots, comments.

Implemented from the public API reference: search.list (100 units), videos.list (1 unit per call, up to 50
ids), commentThreads.list (1 unit per page, 100 per page, order=time -> newest first). Never run live:
live_verification required. Needs YOUTUBE_API_KEY in the environment; without it the collector is skipped.

* Quota ledger: units used are persisted per Pacific date (the API quota resets at Pacific midnight) and a
  run stops cleanly before exceeding daily_quota - quota_reserve.
* Video discovery runs per model only when none is known or search_refresh_days have passed; every run takes
  a fresh views/likes snapshot (view counts have no history).
* Comments: paged newest-first until a comment already collected is reached, or the per-video page cap.
  When capped/out of quota the nextPageToken is stored and resumed next run, so a backfill finishes
  across runs. Author names are not kept.
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from .base import Collector, Fetcher, Summary, Target

PACIFIC = ZoneInfo("America/Los_Angeles")
COST_SEARCH, COST_VIDEOS, COST_COMMENTS = 100, 1, 1
API_KEY_ENV = "YOUTUBE_API_KEY"


class QuotaExceeded(Exception):
    pass


def parse_search(content: bytes) -> list[str]:
    return [i["id"]["videoId"] for i in json.loads(content.decode("utf-8")).get("items", [])
            if i.get("id", {}).get("videoId")]


def parse_videos(content: bytes) -> list[dict]:
    rows = []
    for i in json.loads(content.decode("utf-8")).get("items", []):
        st = i.get("statistics", {})
        rows.append({"video_id": i["id"], "title": i["snippet"]["title"], "published_at": i["snippet"]["publishedAt"],
                     "view_count": int(st["viewCount"]) if "viewCount" in st else None,
                     "like_count": int(st["likeCount"]) if "likeCount" in st else None,
                     "comment_count": int(st["commentCount"]) if "commentCount" in st else None})
    return rows


def parse_comments(content: bytes) -> tuple[list[dict], str | None]:
    body = json.loads(content.decode("utf-8"))
    rows = []
    for it in body.get("items", []):
        top = it["snippet"]["topLevelComment"]["snippet"]
        rows.append({"comment_id": it["id"], "video_id": it["snippet"].get("videoId", ""),
                     "text": top.get("textOriginal") or top.get("textDisplay", ""),
                     "published_at": top["publishedAt"], "like_count": int(top.get("likeCount", 0)),
                     "reply_count": int(it["snippet"].get("totalReplyCount", 0))})
    return rows, body.get("nextPageToken")


class YouTube(Collector):
    name = "youtube"

    def __init__(self, cfg, ctx):
        super().__init__(cfg, ctx)
        self.api_key = os.environ.get(API_KEY_ENV, "")

    # --- quota ledger
    def _ledger_key(self) -> str:
        return f"youtube:quota:{self.ctx.now().astimezone(PACIFIC).date().isoformat()}"

    def _budget(self) -> int:
        o = self.cfg.opts
        return int(o.get("daily_quota", 10000)) - int(o.get("quota_reserve", 200)) - int(self.ctx.state.get(self._ledger_key(), 0))

    def _charge(self, units: int) -> None:
        if units > self._budget():
            raise QuotaExceeded(f"{units} units would exceed today's budget")
        self.ctx.state.set(self._ledger_key(), int(self.ctx.state.get(self._ledger_key(), 0)) + units)

    # --- targets
    def _models(self) -> dict[str, str]:
        from market_signals import catalogue

        names: dict[str, str] = {}
        for path in (catalogue.PRODUCTS_PATH, catalogue.REFERENCE_PATH):
            df = catalogue.read_csv(path)
            names.update(df.drop_duplicates("model_key").set_index("model_key")["model"].to_dict())
        return names

    def _target(self, key: str, endpoint: str, params: dict) -> Target:
        return Target(self.name, key, f"{self.cfg.opts['base_url']}/{endpoint}",
                      {**params, "key": self.api_key}, secret_params=("key",), ext="json",
                      meta={"endpoint": endpoint})

    def _search_target(self, model_key: str, model: str) -> Target:
        o = self.cfg.opts
        q = str(o["search_query_template"]).format(model=model)
        return self._target(f"youtube|search|{model_key}", "search", {
            "part": "snippet", "q": q, "type": "video", "maxResults": int(o.get("max_videos_per_model", 5)),
            "regionCode": o.get("region_code", "IN"), "order": "relevance"})

    def plan(self) -> list[Target]:
        """Targets that would be requested for discovery (comment/video calls depend on discovered ids)."""
        return [self._search_target(k, m) for k, m in self._models().items() if self._needs_search(k)]

    def _needs_search(self, model_key: str) -> bool:
        st = self.ctx.state.get(f"youtube:videos:{model_key}")
        if not st or not st.get("ids"):
            return True
        last = date.fromisoformat(st["searched_on"])
        return (self.ctx.now().date() - last) >= timedelta(days=int(self.cfg.opts.get("search_refresh_days", 28)))

    # --- run
    def collect(self) -> Summary:
        summary = self._summary()
        if not self.api_key:
            summary.status, summary.note = "skipped", f"{API_KEY_ENV} is not set"
            return summary
        fetcher = Fetcher(self.cfg, self.ctx)
        try:
            self._run(fetcher, summary)
        except QuotaExceeded as exc:
            summary.status, summary.note = "partial", f"stopped cleanly: {exc}"
        finally:
            fetcher.close()
        if summary.status == "ok" and summary.failed:
            summary.status = "partial" if summary.fetched else "failed"
        return summary

    def _run(self, fetcher: Fetcher, summary: Summary) -> None:
        all_ids: list[str] = []
        for model_key, model in self._models().items():
            skey = f"youtube:videos:{model_key}"
            st = self.ctx.state.get(skey) or {"ids": [], "searched_on": ""}
            if self._needs_search(model_key):
                self._charge(COST_SEARCH)
                out = fetcher.fetch(self._search_target(model_key, model),
                                    validate=lambda c: isinstance(parse_search(c), list))
                if out.ok:
                    summary.fetched += 1
                    st = {"ids": sorted(set(st["ids"]) | set(parse_search(out.content))),
                          "searched_on": self.ctx.now().date().isoformat()}
                    self.ctx.state.set(skey, st)
                else:
                    summary.failed += 1
            all_ids += st["ids"]
        ids = sorted(set(all_ids))
        summary.planned = len(ids)

        for i in range(0, len(ids), 50):  # snapshot views/likes for every known video, every run
            self._charge(COST_VIDEOS)
            out = fetcher.fetch(self._target(f"youtube|videos|{i}", "videos",
                                             {"part": "snippet,statistics", "id": ",".join(ids[i:i + 50])}),
                                validate=lambda c: len(parse_videos(c)) > 0)
            summary.fetched += out.ok
            summary.failed += not out.ok

        max_pages = int(self.cfg.opts.get("max_comment_pages_per_video", 5))
        for vid in ids:
            self._comments(fetcher, summary, vid, max_pages)

    def _comments(self, fetcher: Fetcher, summary: Summary, vid: str, max_pages: int) -> None:
        skey = f"youtube:comments:{vid}"
        st = self.ctx.state.get(skey) or {"newest_ts": "", "resume_token": None, "pending_newest": ""}
        token = st["resume_token"]
        for page in range(max_pages):
            self._charge(COST_COMMENTS)
            params = {"part": "snippet", "videoId": vid, "maxResults": 100, "order": "time", "textFormat": "plain"}
            if token:
                params["pageToken"] = token
            out = fetcher.fetch(self._target(f"youtube|comments|{vid}|{token or 'first'}", "commentThreads", params),
                                validate=lambda c: isinstance(parse_comments(c)[0], list))
            if not out.ok:
                summary.failed += 1
                self.ctx.state.set(skey, st)
                return
            summary.fetched += 1
            rows, nxt = parse_comments(out.content)
            if rows:
                st["pending_newest"] = max(st["pending_newest"], max(r["published_at"] for r in rows))
            reached_known = bool(st["newest_ts"]) and any(r["published_at"] <= st["newest_ts"] for r in rows)
            if reached_known or not nxt:  # caught up (or no more pages): this pass is complete
                st["newest_ts"] = max(st["newest_ts"], st["pending_newest"])
                st["resume_token"], st["pending_newest"] = None, ""
                self.ctx.state.set(skey, st)
                return
            token = nxt
            st["resume_token"] = token
            self.ctx.state.set(skey, st)  # persist the cursor so an interrupted backfill resumes next run
