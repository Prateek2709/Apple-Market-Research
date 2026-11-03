import json

import httpx

from scraping.base import Fetcher, JsonState, RateLimiter, Target, load_sources, parse_retry_after
from tests.conftest import Net, make_cfg


def log_lines(ctx):
    p = ctx.data_dir / "raw" / "_meta" / "fetch_log.jsonl"
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


def test_sources_yaml_loads_and_gates_retail():
    sources = load_sources()
    assert sources["amazon_in"].kind == "retail" and not sources["amazon_in"].enabled
    assert not sources["amazon_in"].terms_checked and sources["amazon_in"].respect_robots
    assert sources["trends"].enabled is False


def test_retry_after_parsing():
    assert parse_retry_after("7") == 7.0
    assert parse_retry_after("99999") == 300.0
    assert parse_retry_after(None) is None and parse_retry_after("garbage") is None


def test_retries_429_honouring_retry_after_then_succeeds(make_ctx, sleeps):
    calls = iter([httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(503), httpx.Response(200, content=b"ok")])
    net = Net(lambda r: next(calls))
    ctx = make_ctx(net)
    out = Fetcher(make_cfg(), ctx).fetch(Target("src", "k", "https://example.test/x", ext="txt"))
    assert out.ok and out.content == b"ok"
    assert 7.0 in sleeps and len(net.requests) == 3


def test_gives_up_after_max_attempts_and_logs_failure(make_ctx):
    net = Net(lambda r: httpx.Response(500))
    ctx = make_ctx(net)
    out = Fetcher(make_cfg(), ctx).fetch(Target("src", "k", "https://example.test/x"))
    assert not out.ok and out.status == 500 and len(net.requests) == 3
    (line,) = log_lines(ctx)
    assert line["http_status"] == 500 and line["raw_path"] == "" and line["error"] == "HTTP 500"
    assert [d.name for d in (ctx.data_dir / "raw").iterdir()] == ["_meta"]  # no raw page stored for failures


def test_transport_error_is_retried_then_logged(make_ctx):
    def boom(request):
        raise httpx.ConnectError("down")
    ctx = make_ctx(Net(boom))
    out = Fetcher(make_cfg(), ctx).fetch(Target("src", "k", "https://example.test/x"))
    assert not out.ok and "ConnectError" in out.error
    assert log_lines(ctx)[0]["http_status"] is None


def test_404_is_not_retried(make_ctx):
    net = Net(lambda r: httpx.Response(404))
    out = Fetcher(make_cfg(), make_ctx(net)).fetch(Target("src", "k", "https://example.test/x"))
    assert not out.ok and out.status == 404 and len(net.requests) == 1


def test_raw_storage_has_provenance_and_is_never_overwritten(make_ctx):
    ctx = make_ctx(Net(lambda r: httpx.Response(200, content=b"<html>a</html>")))
    f = Fetcher(make_cfg(), ctx)
    t = Target("src", "listing|1", "https://example.test/p", meta={"price_key": "iphone-17|256gb"})
    a, b = f.fetch(t), f.fetch(t)
    assert a.raw_path != b.raw_path  # same second, same target: second file gets a suffix
    assert (ctx.data_dir / a.raw_path).read_bytes() == b"<html>a</html>"
    meta = json.loads((ctx.data_dir / (a.raw_path + ".meta.json")).read_text(encoding="utf-8"))
    for k in ("run_id", "fetch_ts_utc", "ist_date", "sha256", "bytes", "url", "http_status", "price_key", "code_version"):
        assert k in meta
    assert meta["fetch_ts_utc"] == "2026-11-03T10:00:00Z" and meta["ist_date"] == "2026-11-03"
    assert ":" not in a.raw_path.split("/")[-1]  # Windows-safe file name


def test_secret_params_never_reach_logs_or_provenance(make_ctx):
    def handler(request):
        raise httpx.ConnectError(f"cannot reach {request.url}")
    ctx = make_ctx(Net(handler))
    t = Target("src", "k", "https://example.test/api", {"key": "SECRET123", "q": "x"}, secret_params=("key",))
    Fetcher(make_cfg(), ctx).fetch(t)
    assert "SECRET123" not in (ctx.data_dir / "raw" / "_meta" / "fetch_log.jsonl").read_text(encoding="utf-8")
    ctx2 = make_ctx(Net(lambda r: httpx.Response(200, content=b"{}")))
    out = Fetcher(make_cfg(), ctx2).fetch(t)
    meta = (ctx2.data_dir / (out.raw_path + ".meta.json")).read_text(encoding="utf-8")
    assert "SECRET123" not in meta and "<redacted>" in meta


def test_robots_disallow_blocks_fetch(make_ctx):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private\n")
        return httpx.Response(200, content=b"page")
    net = Net(handler)
    f = Fetcher(make_cfg(respect_robots=True), make_ctx(net))
    assert not f.fetch(Target("src", "a", "https://example.test/private/x")).ok
    assert f.fetch(Target("src", "b", "https://example.test/public")).ok
    assert sum(r.url.path == "/robots.txt" for r in net.requests) == 1  # cached per origin


def test_robots_unreadable_is_conservative(make_ctx):
    net = Net(lambda r: httpx.Response(500))
    f = Fetcher(make_cfg(respect_robots=True, max_attempts=1), make_ctx(net))
    assert not f.fetch(Target("src", "a", "https://example.test/x")).ok


def test_robots_404_means_allowed(make_ctx):
    net = Net(lambda r: httpx.Response(404) if r.url.path == "/robots.txt" else httpx.Response(200, content=b"p"))
    assert Fetcher(make_cfg(respect_robots=True), make_ctx(net)).fetch(Target("src", "a", "https://example.test/x")).ok


def test_host_allow_list(make_ctx):
    net = Net(lambda r: httpx.Response(200, content=b"p"))
    f = Fetcher(make_cfg(allowed_host_suffixes=("example.test",)), make_ctx(net))
    assert f.fetch(Target("src", "a", "https://www.example.test/x")).ok
    assert not f.fetch(Target("src", "b", "https://evil.test/x")).ok
    assert len(net.requests) == 1


def test_validate_failure_keeps_raw_and_flags_parse_ok_false(make_ctx):
    ctx = make_ctx(Net(lambda r: httpx.Response(200, content=b"not json")))
    out = Fetcher(make_cfg(), ctx).fetch(Target("src", "a", "https://example.test/x"), validate=json.loads)
    assert out.ok and out.raw_path and log_lines(ctx)[0]["parse_ok"] is False


def test_rate_limiter_waits_for_interval():
    t, slept = [0.0], []
    rl = RateLimiter(5.0, lambda: t[0], slept.append)
    rl.wait()
    t[0] = 2.0
    rl.wait()
    assert slept == [3.0]


def test_state_roundtrip(tmp_path):
    s = JsonState(tmp_path / "m" / "state.json")
    s.set("a", {"x": 1})
    assert JsonState(tmp_path / "m" / "state.json").get("a") == {"x": 1}
