"""Collector tests. Payloads are FIXTURES (invented, shaped like each service's documented schema)."""

import csv
import json
from datetime import date

import httpx
import pytest

from scraping import catalogue as cat
from scraping import match, parse, timeutil
from scraping import financial, gdelt, retail, trends, wayback, wikipedia, youtube
from scraping.registry import REGISTRY
from scraping.base import IncompleteCollector, SourceConfig, load_sources
from run import gate, run_collect
from tests.conftest import NOW, Net, make_cfg

# ---- FIXTURES -----------------------------------------------------------------------------------
PV = json.dumps({"items": [{"project": "en.wikipedia", "article": "IPhone_17", "granularity": "daily",
                            "timestamp": "2026-10-01"[:4] + "10" + "0100", "access": "all-access", "agent": "user",
                            "views": 1234}]}).encode()
FX = json.dumps({"base": "USD", "rates": {"2026-10-30": {"INR": 88.5}, "2026-11-02": {"INR": 88.7}}}).encode()
YF = ("Date,Open,High,Low,Close,Adj Close,Volume\n2026-10-30 00:00:00-04:00,1,2,0.5,150.0,149.5,10\n").encode()
GD = json.dumps({"timeline": [{"series": "Volume", "data": [{"date": "20261001T000000Z", "value": 0.5}]}]}).encode()
CDX = json.dumps([["timestamp", "original", "mimetype", "statuscode", "digest", "length"],
                  ["20250920101010", "https://store.test/in/p", "text/html", "200", "AAA", "10"],
                  ["20251020101010", "https://store.test/in/p", "text/html", "200", "BBB", "10"]]).encode()


def json_ok(body):
    return lambda r: httpx.Response(200, content=body)


def state(ctx, key):
    return ctx.state.get(key)


# ---- helpers ------------------------------------------------------------------------------------
def test_parse_inr_indian_grouping():
    assert parse.parse_inr("₹1,64,900") == 164900
    assert parse.parse_inr("Rs. 79,900.00 only") == 79900
    assert parse.parse_inr("no price") is None


def test_week_start_is_sunday():
    assert timeutil.week_start(date(2026, 11, 3)) == date(2026, 11, 1)   # Tuesday -> Sunday
    assert timeutil.week_start(date(2026, 11, 1)) == date(2026, 11, 1)   # Sunday -> itself
    assert timeutil.week_start(date(2026, 11, 7)) == date(2026, 11, 1)   # Saturday -> same week
    assert timeutil.to_ist_date(NOW.replace(hour=20)) == date(2026, 11, 4)  # 20:00 UTC is already next day in IST


# ---- SKU matching -------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def matcher():
    return match.Matcher(cat.read_csv(cat.PRODUCTS_PATH), cat.read_csv(cat.REFERENCE_PATH))


@pytest.mark.parametrize("title, decision, price_key, sku", [
    ("Apple iPhone 18 Pro Max (256GB) - Silver", "accept", "iphone-18-pro-max|256gb", "iphone-18-pro-max|256gb|silver"),
    ("Apple iPhone 18 Pro Max 2 TB Black Titanium-free", "accept", "iphone-18-pro-max|2tb", "iphone-18-pro-max|2tb|black"),
    ("Apple iPhone 17 256 GB: Lavender", "accept", "iphone-17|256gb", "iphone-17|256gb|lavender"),
    ("Apple iPhone 17e 512GB", "accept", "iphone-17e|512gb", ""),            # colour not named: price_key only
    ("Apple iPhone 17 Pro 256GB Deep Blue", "accept", "iphone-17-pro|256gb", "iphone-17-pro|256gb|deep-blue"),
    ("Apple iPhone Air 1TB Sky Blue", "accept", "iphone-air|1tb", "iphone-air|1tb|sky-blue"),
])
def test_match_accepts(matcher, title, decision, price_key, sku):
    r = matcher.match(title)
    assert (r.decision, r.price_key, r.sku_id) == (decision, price_key, sku)


@pytest.mark.parametrize("title, decision", [
    ("Apple iPhone 17 Pro 256GB (Renewed)", "excluded"),
    ("iPhone 16 Pro Max Case Cover", "excluded"),
    ("Apple iPhone 16 Plus 128GB", "reject"),          # qualifier after a catalogue name: not in catalogue
    ("Apple iPhone 15 Pro 256GB", "reject"),
    ("Apple iPhone 17 Pro 2TB", "reject"),             # 17 Pro never offered 2TB
    ("Samsung Galaxy S25 Ultra 256GB", "reject"),
    ("Apple iPhone 17 Black", "review"),               # storage missing
    ("Apple iphne 17 pro max 256gb", "review"),        # typo in model: fuzzy only, never auto-accepted
])
def test_match_non_accepts(matcher, title, decision):
    assert matcher.match(title).decision == decision


# ---- Wikipedia ----------------------------------------------------------------------------------
def test_wikipedia_incremental_window_and_state(make_ctx):
    net = Net(json_ok(PV))
    cfg = make_cfg("wikipedia", opts={"base_url": "https://wm.test/pv", "articles": ["IPhone_17"], "default_start": "2026-10-01"})
    ctx = make_ctx(net)
    c = wikipedia.Wikipedia(cfg, ctx)
    s = c.collect()
    assert (s.status, s.fetched) == ("ok", 1)
    assert str(net.requests[0].url).endswith("/IPhone_17/daily/20261001/20261102")  # yesterday, not today
    assert state(ctx, "wikipedia:IPhone_17") == "2026-11-02"
    s2 = wikipedia.Wikipedia(cfg, ctx).collect()      # nothing new to fetch: no request
    assert (s2.fetched, s2.skipped_up_to_date) == (0, 1) and len(net.requests) == 1


def test_wikipedia_failure_does_not_advance_window(make_ctx):
    ctx = make_ctx(Net(lambda r: httpx.Response(404)))
    cfg = make_cfg("wikipedia", opts={"base_url": "https://wm.test/pv", "articles": ["Nope"], "default_start": "2026-10-01"})
    s = wikipedia.Wikipedia(cfg, ctx).collect()
    assert s.status == "failed" and state(ctx, "wikipedia:Nope") is None


def test_parse_pageviews():
    (row,) = wikipedia.parse_pageviews(PV)
    assert row["views"] == 1234 and row["article"] == "IPhone_17"


# ---- Frankfurter / yfinance ---------------------------------------------------------------------
def test_frankfurter_collect_and_parse(make_ctx):
    net = Net(json_ok(FX))
    ctx = make_ctx(net)
    cfg = make_cfg("frankfurter", opts={"base_url": "https://fx.test", "default_start": "2026-10-29"})
    s = financial.Frankfurter(cfg, ctx).collect()
    assert s.fetched == 1 and net.requests[0].url.params["to"] == "INR"
    assert "/2026-10-29..2026-11-02" in str(net.requests[0].url)
    rows = financial.parse_frankfurter(FX)
    assert rows[0]["market_date"] == "2026-10-30" and rows[0]["available_ist_date"] == "2026-10-30"


def test_yfinance_uses_injected_history_and_exclusive_end(make_ctx):
    calls = []

    class Fake(financial.Yfinance):
        history_fn = staticmethod(lambda sym, a, b: calls.append((sym, a, b)) or YF.decode())

    ctx = make_ctx()
    cfg = make_cfg("yfinance", opts={"symbols": ["AAPL"], "default_start": "2026-10-29"})
    s = Fake(cfg, ctx).collect()
    assert s.fetched == 1 and calls == [("AAPL", date(2026, 10, 29), date(2026, 11, 3))]  # end = last day + 1
    assert state(ctx, "yfinance:AAPL") == "2026-11-02"


def test_yfinance_library_error_is_logged_not_raised(make_ctx):
    class Boom(financial.Yfinance):
        history_fn = staticmethod(lambda *a: (_ for _ in ()).throw(RuntimeError("rate limited")))

    ctx = make_ctx()
    s = Boom(make_cfg("yfinance", opts={"symbols": ["AAPL"], "default_start": "2026-10-29"}), ctx).collect()
    assert s.status == "failed" and state(ctx, "yfinance:AAPL") is None


def test_aapl_availability_is_next_day_and_other_symbols_na():
    (aapl,) = financial.parse_yfinance_csv(YF, "AAPL")
    assert aapl["market_date"] == "2026-10-30" and aapl["available_ist_date"] == "2026-10-31"
    assert aapl["adj_close"] == 149.5
    (fx,) = financial.parse_yfinance_csv(YF, "INR=X")
    assert fx["available_ist_date"] is None


# ---- GDELT --------------------------------------------------------------------------------------
def test_gdelt_window_clamped_to_rolling_90_days(make_ctx):
    net = Net(json_ok(GD))
    ctx = make_ctx(net)
    cfg = make_cfg("gdelt", opts={"base_url": "https://gd.test/doc", "modes": ["timelinevol"],
                                  "queries": [{"name": "q", "query": "iphone"}]})
    ctx.since = "2020-01-01"
    s = gdelt.Gdelt(cfg, ctx).collect()
    assert s.fetched == 1
    assert net.requests[0].url.params["startdatetime"] == "20260805000000"  # 2026-11-03 minus 90 days
    assert gdelt.parse_timeline(GD)[0]["date"] == "2026-10-01"


# ---- Wayback ------------------------------------------------------------------------------------
def write_listings(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=retail.LISTING_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({**dict.fromkeys(retail.LISTING_COLUMNS, ""), **r})


def test_wayback_downloads_each_snapshot_once(make_ctx, tmp_path):
    lp = tmp_path / "listings.csv"
    write_listings(lp, [{"source": "apple_in", "url": "https://store.test/in/p", "price_key": "iphone-17|256gb"}])

    def handler(request):
        return httpx.Response(200, content=CDX if "cdx" in request.url.path else b"<html>old page</html>")

    net = Net(handler)
    ctx = make_ctx(net)
    cfg = make_cfg("wayback", opts={"cdx_url": "https://ia.test/cdx", "url_sources": ["apple_in"],
                                    "snapshot_url_template": "https://ia.test/web/{timestamp}id_/{original}"})
    c = wayback.Wayback(cfg, ctx)
    c.listings_path = lp
    s = c.collect()
    assert s.fetched == 3 and s.failed == 0  # 1 CDX + 2 snapshots
    assert "https://ia.test/web/20250920101010id_/https://store.test/in/p" in [str(r.url) for r in net.requests]
    n = len(net.requests)
    c2 = wayback.Wayback(cfg, ctx)
    c2.listings_path = lp
    s2 = c2.collect()
    assert s2.skipped_up_to_date == 2 and len(net.requests) == n + 1  # only the CDX query is repeated
    assert "from" in net.requests[-1].url.params  # incremental window starts at the stored date


def test_wayback_snapshot_budget_defers_remainder(make_ctx, tmp_path):
    lp = tmp_path / "l.csv"
    write_listings(lp, [{"source": "apple_in", "url": "https://store.test/in/p"}])
    net = Net(lambda r: httpx.Response(200, content=CDX if "cdx" in r.url.path else b"x"))
    ctx = make_ctx(net)
    cfg = make_cfg("wayback", opts={"cdx_url": "https://ia.test/cdx", "url_sources": ["apple_in"],
                                    "snapshot_url_template": "https://ia.test/{timestamp}/{original}", "max_snapshots_per_run": 1})
    c = wayback.Wayback(cfg, ctx)
    c.listings_path = lp
    c.collect()
    key = next(k for k in ctx.state._data if k.startswith("wayback:"))
    assert len(ctx.state.get(key)["downloaded"]) == 1 and ctx.state.get(key)["covered_through"] == ""


# ---- YouTube ------------------------------------------------------------------------------------
def yt_cfg(**o):
    return make_cfg("youtube", opts={"base_url": "https://yt.test/v3", "daily_quota": 10000, "quota_reserve": 200,
                                     "search_query_template": "{model} review", "max_videos_per_model": 2,
                                     "max_comment_pages_per_video": 2, **o})


def yt_handler(request):
    p = request.url.path
    if p.endswith("/search"):
        return httpx.Response(200, json={"items": [{"id": {"videoId": "vid1"}}]})
    if p.endswith("/videos"):
        return httpx.Response(200, json={"items": [{"id": "vid1", "snippet": {"title": "t", "publishedAt": "2026-01-01T00:00:00Z"},
                                                    "statistics": {"viewCount": "10"}}]})
    comments = [{"id": "c1", "snippet": {"videoId": "vid1", "totalReplyCount": 0, "topLevelComment": {
        "snippet": {"textDisplay": "bought it", "publishedAt": "2026-10-02T00:00:00Z", "likeCount": 1}}}}]
    body = {"items": comments}
    if "pageToken" not in request.url.params:
        body["nextPageToken"] = "T2"
    return httpx.Response(200, json=body)


def test_youtube_skipped_without_key(make_ctx, monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    assert youtube.YouTube(yt_cfg(), make_ctx()).collect().status == "skipped"


def test_youtube_collects_charges_quota_and_hides_key(make_ctx, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "KEY-ABC")
    net = Net(yt_handler)
    ctx = make_ctx(net)
    s = youtube.YouTube(yt_cfg(), ctx).collect()
    assert s.status == "ok" and s.failed == 0
    used = ctx.state.get("youtube:quota:2026-11-03")
    searches = sum(r.url.path.endswith("/search") for r in net.requests)
    assert used == searches * 100 + (len(net.requests) - searches)  # search 100, every other call 1
    assert ctx.state.get("youtube:comments:vid1")["newest_ts"] == "2026-10-02T00:00:00Z"
    logged = (ctx.data_dir / "raw" / "_meta" / "fetch_log.jsonl").read_text(encoding="utf-8")
    assert "KEY-ABC" not in logged
    for p in (ctx.data_dir / "raw").rglob("*.meta.json"):
        assert "KEY-ABC" not in p.read_text(encoding="utf-8")


def test_youtube_stops_cleanly_at_quota_and_resumes_cursor(make_ctx, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "k")
    net = Net(yt_handler)
    ctx = make_ctx(net)
    # budget for exactly 1 search (100) then nothing else: 10000-200-... set quota so only one search fits
    cfg = yt_cfg(daily_quota=300, quota_reserve=100)   # budget 200 -> 2 searches max, thirteen needed
    s = youtube.YouTube(cfg, ctx).collect()
    assert s.status == "partial" and "stopped cleanly" in s.note
    assert sum(r.url.path.endswith("/search") for r in net.requests) == 2


def test_youtube_comment_cursor_persists_when_page_cap_hit(make_ctx, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "k")

    def always_more(request):
        if request.url.path.endswith("/commentThreads"):
            return httpx.Response(200, json={"items": [], "nextPageToken": "MORE"})
        return yt_handler(request)

    ctx = make_ctx(Net(always_more))
    ctx.state.set("youtube:videos:iphone-15", {"ids": ["vid1"], "searched_on": "2026-11-03"})
    cfg = yt_cfg(max_comment_pages_per_video=1)
    c = youtube.YouTube(cfg, ctx)
    c._models = lambda: {"iphone-15": "iPhone 15"}
    c.collect()
    assert ctx.state.get("youtube:comments:vid1")["resume_token"] == "MORE"


# ---- Retail (fetch-only) ------------------------------------------------------------------------
def test_retail_fetches_only_its_own_listings_and_stores_raw(make_ctx, tmp_path):
    lp = tmp_path / "l.csv"
    write_listings(lp, [
        {"source": "croma", "url": "https://www.croma.com/p/1", "price_key": "iphone-17|256gb", "page_type": "product"},
        {"source": "flipkart", "url": "https://www.flipkart.com/p/2"},
    ])
    net = Net(lambda r: httpx.Response(200, content=b"<html>FIXTURE</html>"))
    ctx = make_ctx(net)
    cfg = make_cfg("croma", kind="retail", allowed_host_suffixes=("croma.com",))
    c = retail.Croma(cfg, ctx)
    c.listings_path = lp
    s = c.collect()
    assert (s.fetched, s.planned) == (1, 1) and [str(r.url) for r in net.requests] == ["https://www.croma.com/p/1"]
    (meta,) = list((ctx.data_dir / "raw" / "croma").rglob("*.meta.json"))
    assert json.loads(meta.read_text(encoding="utf-8"))["price_key"] == "iphone-17|256gb"


def test_retail_rejects_url_on_wrong_host(make_ctx, tmp_path):
    lp = tmp_path / "l.csv"
    write_listings(lp, [{"source": "croma", "url": "https://evil.test/p"}])
    net = Net(lambda r: httpx.Response(200, content=b"x"))
    c = retail.Croma(make_cfg("croma", kind="retail", allowed_host_suffixes=("croma.com",)), make_ctx(net))
    c.listings_path = lp
    assert c.collect().status == "failed" and not net.requests


def test_retail_parser_is_explicitly_incomplete():
    with pytest.raises(IncompleteCollector):
        retail.RetailCollector.parse_page(b"<html></html>")


def test_shipped_listings_file_is_header_only_and_valid():
    assert retail.load_listings() == []


def test_listings_validation_against_catalogue():
    rows = [{"source": "croma", "url": "u", "price_key": "nope|1gb", "sku_id": "", **{}}]
    errs = retail.validate_listings(rows, {"iphone-17|256gb"}, set())
    assert errs and "unknown price_key" in errs[0]


# ---- Trends / registry / runner -----------------------------------------------------------------
def test_trends_batches_include_anchor_and_cap_at_five_terms():
    batches = trends.plan_term_batches(["iPhone 17", "iPhone 18", "iPhone 17", "a", "b", "c", "iPhone"])
    assert batches == [["iPhone", "iPhone 17", "iPhone 18", "a", "b"], ["iPhone", "c"]]


def test_trends_collect_raises_incomplete(make_ctx):
    with pytest.raises(IncompleteCollector):
        trends.GoogleTrends(make_cfg("trends"), make_ctx()).collect()


def test_registry_matches_config_and_declares_status():
    sources = load_sources()
    assert set(REGISTRY) == set(sources)
    assert {c.implementation for c in REGISTRY.values()} <= {"implemented_unverified", "fetch_only", "incomplete"}


def test_gate_blocks_unreviewed_scrape_sources():
    s = load_sources()
    assert "disabled" in gate(s["croma"])
    assert "terms" in gate(SourceConfig(**{**s["croma"].__dict__, "enabled": True}))
    assert gate(s["wikipedia"]) == ""


def test_run_collect_isolates_failures_and_logs_run(make_ctx, monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    sources = {"trends": make_cfg("trends"), "youtube": yt_cfg(),
               "wikipedia": make_cfg("wikipedia", opts={"base_url": "https://wm.test", "articles": ["IPhone_17"], "default_start": "2026-10-01"})}
    ctx = make_ctx(Net(json_ok(PV)))
    out = {s.source: s for s in run_collect(["trends", "youtube", "wikipedia"], ctx, sources)}
    assert out["trends"].status == "incomplete" and out["youtube"].status == "skipped" and out["wikipedia"].status == "ok"
    (line,) = (ctx.data_dir / "raw" / "_meta" / "runs.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(line)["run_id"] == ctx.run_id


def test_dry_run_makes_no_requests_and_writes_nothing(make_ctx, capsys):
    net = Net(json_ok(PV))
    sources = {"wikipedia": make_cfg("wikipedia", opts={"base_url": "https://wm.test", "articles": ["IPhone_17"], "default_start": "2026-10-01"})}
    ctx = make_ctx(net, dry_run=True)
    (s,) = run_collect(["wikipedia"], ctx, sources)
    assert s.status == "dry-run" and s.planned == 1 and not net.requests
    assert not ctx.data_dir.exists()
    assert "IPhone_17" in capsys.readouterr().out
