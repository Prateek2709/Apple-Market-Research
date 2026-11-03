"""Offline test helpers. All HTTP is served by httpx.MockTransport; payloads are small FIXTURES shaped like
each service's documented schema. They are invented for tests, not real responses."""

from datetime import datetime, timezone

import httpx
import pytest

from market_signals.collectors.base import RunContext, SourceConfig

NOW = datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc)


def make_cfg(name="src", kind="api", **kw) -> SourceConfig:
    opts = kw.pop("opts", {})
    base = dict(name=name, kind=kind, tier="A", enabled=True, terms_checked=True, respect_robots=False,
                min_interval_s=0.0, timeout_s=5, max_attempts=3, user_agent="test-agent",
                allowed_host_suffixes=(), opts=opts)
    base.update(kw)
    return SourceConfig(**base)


class Net:
    """Records requests and serves canned responses: handler(request) -> httpx.Response."""

    def __init__(self, handler):
        self.handler, self.requests = handler, []

    def factory(self, cfg):
        def h(request):
            self.requests.append(request)
            return self.handler(request)
        return httpx.Client(transport=httpx.MockTransport(h), headers={"User-Agent": cfg.user_agent})


@pytest.fixture
def sleeps():
    return []


@pytest.fixture
def make_ctx(tmp_path, sleeps):
    def _make(net=None, **kw):
        return RunContext(data_dir=tmp_path / "data", now=lambda: NOW, sleep=sleeps.append,
                          clock=lambda: 0.0, client_factory=net.factory if net else None, **kw)
    return _make
