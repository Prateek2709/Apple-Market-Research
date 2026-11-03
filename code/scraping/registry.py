"""Collector registry. Keys are the source names used in config/sources.yaml and on the command line."""

from __future__ import annotations

from .base import Collector
from .financial import Frankfurter, Yfinance
from .gdelt import Gdelt
from .retail import (AmazonIn, AppleIn, Croma, Flipkart, Gsmarena, Mobiles91, RelianceDigital, Smartprix,
                     VijaySales)
from .trends import GoogleTrends
from .wayback import Wayback
from .wikipedia import Wikipedia
from .youtube import YouTube

_ALL: tuple[type[Collector], ...] = (
    AppleIn, AmazonIn, Flipkart, Croma, RelianceDigital, VijaySales, Smartprix, Mobiles91, Gsmarena,
    Wayback, GoogleTrends, YouTube, Wikipedia, Gdelt, Yfinance, Frankfurter,
)
REGISTRY: dict[str, type[Collector]] = {c.name: c for c in _ALL}
