"""Shared collection infrastructure: config, rate limiting, retries, robots.txt, raw store, logs, state.

Nothing in this module (or the collectors) runs at import time or performs network access unless a
collector's collect() is called by the runner.

Data written (all under data/, git-ignored, append-only raw):
    data/raw/<source>/<ist-date>/<utc-stamp>_<target-hash>.<ext>  + .meta.json sidecar (provenance)
    data/raw/_meta/fetch_log.jsonl one line per fetch attempt outcome (run_id, source, target, ts, status, bytes, ...)
    data/raw/_meta/runs.jsonl      one line per run
    data/raw/_meta/collect_state.json incremental-collection state (covered ranges, cursors, quota ledger)
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.robotparser
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import httpx
import yaml
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from scraping import __version__, settings, timeutil

SOURCES_PATH = settings.CONFIG_DIR / "sources.yaml"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
RETRY_AFTER_CAP_S = 300.0
DEFAULT_USER_AGENT = "market-signals-research/0.1 (personal research; set MARKET_SIGNALS_USER_AGENT)"


class FetchError(Exception):
    """A fetch could not be completed (transport failure after retries, or blocked by robots.txt)."""


class RobotsDisallowed(FetchError):
    pass


class IncompleteCollector(NotImplementedError):
    """Raised by collectors/parsers that cannot be written reliably without a real response."""


class RetryableHTTP(Exception):
    def __init__(self, response: httpx.Response, retry_after: float | None):
        super().__init__(f"HTTP {response.status_code}")
        self.response = response
        self.retry_after = retry_after


# ----------------------------------------------------------------------------- configuration
@dataclass(frozen=True)
class SourceConfig:
    name: str
    kind: str
    tier: str
    enabled: bool
    terms_checked: bool
    respect_robots: bool
    min_interval_s: float
    timeout_s: float
    max_attempts: int
    user_agent: str
    allowed_host_suffixes: tuple[str, ...]
    opts: dict[str, Any] = field(default_factory=dict)


def load_sources(path: Path | None = None) -> dict[str, SourceConfig]:
    with open(path or SOURCES_PATH, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    defaults = raw.get("defaults", {})
    ua = os.environ.get("MARKET_SIGNALS_USER_AGENT") or defaults.get("user_agent") or DEFAULT_USER_AGENT
    out: dict[str, SourceConfig] = {}
    for name, entry in (raw.get("sources") or {}).items():
        merged = {**defaults, **entry}
        known = {"kind", "tier", "enabled", "terms_checked", "respect_robots", "min_interval_s", "timeout_s",
                 "max_attempts", "user_agent", "allowed_host_suffixes"}
        out[name] = SourceConfig(
            name=name, kind=merged["kind"], tier=merged.get("tier", "A"),
            enabled=bool(merged.get("enabled", True)), terms_checked=bool(merged.get("terms_checked", True)),
            respect_robots=bool(merged.get("respect_robots", False)),
            min_interval_s=float(merged.get("min_interval_s", 2.0)), timeout_s=float(merged.get("timeout_s", 30)),
            max_attempts=int(merged.get("max_attempts", 5)), user_agent=ua,
            allowed_host_suffixes=tuple(merged.get("allowed_host_suffixes") or ()),
            opts={k: v for k, v in merged.items() if k not in known and k != "user_agent"},
        )
    return out


# ----------------------------------------------------------------------------- state, logs, raw store
class JsonState:
    """Small JSON key/value store (atomic writes) for incremental collection."""

    def __init__(self, path: Path):
        self.path = path
        self._data: dict[str, Any] = {}
        if path.exists():
            self._data = json.loads(path.read_text(encoding="utf-8"))

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=1, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]


@dataclass
class RunContext:
    """Everything a collector needs; clock, sleep and HTTP client are injectable for tests."""

    data_dir: Path
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    now: Callable[[], datetime] = timeutil.utc_now
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    client_factory: Callable[[SourceConfig], httpx.Client] | None = None
    dry_run: bool = False
    since: str | None = None  # ISO date; overrides stored state as the start of a window

    def __post_init__(self) -> None:
        self.state = JsonState(self.meta_dir / "collect_state.json")

    @property
    def meta_dir(self) -> Path:
        return self.data_dir / settings.META_SUBDIR

    # --- append-only raw layer
    def save_raw(self, source: str, target_key: str, content: bytes, ext: str, meta: dict[str, Any]) -> str:
        ts = self.now()
        folder = self.data_dir / "raw" / source / timeutil.to_ist_date(ts).isoformat()
        folder.mkdir(parents=True, exist_ok=True)
        base = f"{timeutil.file_stamp(ts)}_{short_hash(target_key)}"
        n = 0
        while True:
            suffix = "" if n == 0 else f"_{n}"
            path = folder / f"{base}{suffix}.{ext}"
            if not path.exists():  # raw files are never overwritten
                break
            n += 1
        path.write_bytes(content)
        provenance = {
            "run_id": self.run_id, "source": source, "target_key": target_key,
            "fetch_ts_utc": timeutil.iso_utc(ts), "ist_date": timeutil.to_ist_date(ts).isoformat(),
            "bytes": len(content), "sha256": sha256_hex(content), "code_version": __version__, **meta,
        }
        path.with_name(path.name + ".meta.json").write_text(
            json.dumps(provenance, indent=1, sort_keys=True, default=str), encoding="utf-8")
        return path.relative_to(self.data_dir).as_posix()

    def append_jsonl(self, name: str, record: dict[str, Any]) -> None:
        path = self.meta_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(record, sort_keys=True, default=str) + "\n")

    def log_fetch(self, source: str, target: str, *, http_status: int | None, nbytes: int,
                  parse_ok: bool | None, error: str = "", raw_path: str = "", sha256: str = "") -> None:
        ts = self.now()
        self.append_jsonl("fetch_log.jsonl", {
            "run_id": self.run_id, "source": source, "target": target, "ts_utc": timeutil.iso_utc(ts),
            "ist_date": timeutil.to_ist_date(ts).isoformat(), "http_status": http_status, "bytes": nbytes,
            "parse_ok": parse_ok, "error": error, "raw_path": raw_path, "sha256": sha256,
        })


# ----------------------------------------------------------------------------- fetching
@dataclass
class Target:
    source: str
    key: str                       # stable identity used for file names and provenance
    url: str
    params: dict[str, Any] | None = None
    secret_params: tuple[str, ...] = ()   # query params never written to logs/provenance (e.g. API keys)
    ext: str = "html"
    meta: dict[str, Any] = field(default_factory=dict)

    def safe_params(self) -> dict[str, Any]:
        return {k: ("<redacted>" if k in self.secret_params else v) for k, v in (self.params or {}).items()}


@dataclass
class Outcome:
    ok: bool
    status: int | None
    content: bytes = b""
    raw_path: str = ""
    error: str = ""


class RateLimiter:
    def __init__(self, min_interval_s: float, clock: Callable[[], float], sleep: Callable[[float], None]):
        self.min_interval_s, self._clock, self._sleep = min_interval_s, clock, sleep
        self._last: float | None = None

    def wait(self) -> None:
        if self._last is not None:
            gap = self.min_interval_s - (self._clock() - self._last)
            if gap > 0:
                self._sleep(gap)
        self._last = self._clock()


def parse_retry_after(value: str | None, now: datetime | None = None) -> float | None:
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return min(float(value), RETRY_AFTER_CAP_S)
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    now = now or datetime.now(timezone.utc)
    return min(max((when - now).total_seconds(), 0.0), RETRY_AFTER_CAP_S)


class Fetcher:
    """HTTP GET with per-source rate limit, tenacity retries (honours Retry-After), optional robots.txt gate,
    provenance-carrying raw storage and a fetch log row for every outcome."""

    def __init__(self, cfg: SourceConfig, ctx: RunContext):
        self.cfg, self.ctx = cfg, ctx
        self.limiter = RateLimiter(cfg.min_interval_s, ctx.clock, ctx.sleep)
        self._client = ctx.client_factory(cfg) if ctx.client_factory else httpx.Client(
            timeout=cfg.timeout_s, headers={"User-Agent": cfg.user_agent}, follow_redirects=True)
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    def close(self) -> None:
        self._client.close()

    # --- low level
    def _get_with_retry(self, url: str, params: dict[str, Any] | None) -> httpx.Response:
        def attempt() -> httpx.Response:
            self.limiter.wait()
            resp = self._client.get(url, params=params)
            if resp.status_code in RETRYABLE_STATUS:
                raise RetryableHTTP(resp, parse_retry_after(resp.headers.get("Retry-After")))
            return resp

        backoff = wait_exponential(multiplier=2, min=2, max=60)

        def wait(state):
            exc = state.outcome.exception()
            if isinstance(exc, RetryableHTTP) and exc.retry_after is not None:
                return exc.retry_after
            return backoff(state)

        retrying = Retrying(
            stop=stop_after_attempt(self.cfg.max_attempts), wait=wait, sleep=self.ctx.sleep, reraise=True,
            retry=retry_if_exception_type((httpx.TransportError, RetryableHTTP)),
        )
        try:
            return retrying(attempt)
        except RetryableHTTP as exc:  # attempts exhausted: hand back the last error response
            return exc.response

    def _robots_allows(self, url: str) -> bool:
        parts = urlparse(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            rp: urllib.robotparser.RobotFileParser | None = urllib.robotparser.RobotFileParser()
            try:
                resp = self._get_with_retry(f"{origin}/robots.txt", None)
                self.ctx.log_fetch(self.cfg.name, f"{origin}/robots.txt", http_status=resp.status_code,
                                   nbytes=len(resp.content), parse_ok=None)
                if resp.status_code == 200:
                    rp.parse(resp.text.splitlines())
                elif 400 <= resp.status_code < 500:
                    rp.parse([])            # no robots.txt: everything allowed
                else:
                    rp = None               # could not read it: be conservative
            except httpx.HTTPError as exc:
                self.ctx.log_fetch(self.cfg.name, f"{origin}/robots.txt", http_status=None, nbytes=0,
                                   parse_ok=None, error=repr(exc))
                rp = None
            self._robots[origin] = rp
        rp = self._robots[origin]
        return bool(rp and rp.can_fetch(self.cfg.user_agent, url))

    @staticmethod
    def _redact(text: str, target: "Target") -> str:
        for name in target.secret_params:
            value = (target.params or {}).get(name)
            if value:
                text = text.replace(str(value), "<redacted>")
        return text

    def check_host(self, url: str) -> None:
        if not self.cfg.allowed_host_suffixes:
            return
        host = (urlparse(url).hostname or "").lower()
        if not any(host == s or host.endswith("." + s) for s in self.cfg.allowed_host_suffixes):
            raise FetchError(f"host {host!r} is not allowed for source {self.cfg.name} "
                             f"(allowed: {', '.join(self.cfg.allowed_host_suffixes)})")

    # --- public
    def fetch(self, target: Target, *, store_raw: bool = True,
              validate: Callable[[bytes], bool] | None = None) -> Outcome:
        """Fetch one target. Returns an Outcome; never raises for HTTP/transport problems (they are logged)."""
        label = target.key
        try:
            self.check_host(target.url)
            if self.cfg.respect_robots and not self._robots_allows(target.url):
                raise RobotsDisallowed(f"robots.txt disallows (or could not be read for) {target.url}")
            resp = self._get_with_retry(target.url, target.params)
        except (FetchError, httpx.HTTPError) as exc:
            err = self._redact(repr(exc), target)
            self.ctx.log_fetch(self.cfg.name, label, http_status=None, nbytes=0, parse_ok=None, error=err)
            return Outcome(False, None, error=err)

        content = resp.content
        if not resp.is_success:
            self.ctx.log_fetch(self.cfg.name, label, http_status=resp.status_code, nbytes=len(content),
                               parse_ok=None, error=f"HTTP {resp.status_code}")
            return Outcome(False, resp.status_code, error=f"HTTP {resp.status_code}")

        parse_ok = None
        if validate is not None:
            try:
                parse_ok = bool(validate(content))
            except Exception:  # noqa: BLE001 - a parser failure must not lose the raw page
                parse_ok = False
        raw_path = ""
        if store_raw:
            raw_path = self.ctx.save_raw(self.cfg.name, target.key, content, target.ext, {
                "url": target.url, "params": target.safe_params(), "http_status": resp.status_code,
                "final_url": str(resp.url).split("?")[0] if target.secret_params else str(resp.url),
                "content_type": resp.headers.get("content-type", ""), "parse_ok": parse_ok, **target.meta})
        self.ctx.log_fetch(self.cfg.name, label, http_status=resp.status_code, nbytes=len(content),
                           parse_ok=parse_ok, raw_path=raw_path, sha256=sha256_hex(content))
        return Outcome(True, resp.status_code, content, raw_path)

    def record_external(self, target: Target, content: bytes, *, error: str = "",
                        validate: Callable[[bytes], bool] | None = None) -> Outcome:
        """Store/log a result obtained without HTTP through this module (e.g. a client library)."""
        if error:
            self.ctx.log_fetch(self.cfg.name, target.key, http_status=None, nbytes=0, parse_ok=None, error=error)
            return Outcome(False, None, error=error)
        parse_ok = None
        if validate is not None:
            try:
                parse_ok = bool(validate(content))
            except Exception:  # noqa: BLE001
                parse_ok = False
        raw_path = self.ctx.save_raw(self.cfg.name, target.key, content, target.ext,
                                     {"url": target.url, "params": target.safe_params(), "parse_ok": parse_ok,
                                      "via": "client library", **target.meta})
        self.ctx.log_fetch(self.cfg.name, target.key, http_status=None, nbytes=len(content), parse_ok=parse_ok,
                           raw_path=raw_path, sha256=sha256_hex(content))
        return Outcome(True, None, content, raw_path)


# ----------------------------------------------------------------------------- collector base
@dataclass
class Summary:
    source: str
    status: str = "ok"          # ok | partial | failed | skipped | incomplete
    planned: int = 0
    fetched: int = 0
    skipped_up_to_date: int = 0
    failed: int = 0
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class Collector:
    """One collector per source. Subclasses implement plan() (no network) and collect()."""

    name = ""
    # implemented_unverified: written from public documentation, never run against the live service
    # fetch_only: fetches and stores raw pages; the page parser is NOT implemented (needs a real page)
    # incomplete: cannot run (see note)
    implementation = "implemented_unverified"
    live_verification = "required"

    def __init__(self, cfg: SourceConfig, ctx: RunContext):
        self.cfg, self.ctx = cfg, ctx

    def plan(self) -> list[Target]:
        raise NotImplementedError

    def collect(self) -> Summary:
        raise NotImplementedError

    def _summary(self, **kw: Any) -> Summary:
        return Summary(source=self.name, **kw)


def yesterday_utc(ctx: RunContext):
    return (ctx.now() - timedelta(days=1)).astimezone(timezone.utc).date()
