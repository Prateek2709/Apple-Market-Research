"""Project paths and the active-scope configuration.

All paths are resolved relative to the project root (the directory holding
pyproject.toml) using pathlib, so the code runs unchanged on Linux and Windows.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
CONFIG_DIR: Path = PROJECT_ROOT / "config"
CATALOGUE_DIR: Path = PROJECT_ROOT / "catalogue"

DATA_LAYERS = ("raw", "bronze", "silver", "gold", "meta")

# Variant suffixes used in active_scope.yaml -> how they extend the family key.
# "base" and "air" add nothing ("iphone-16", "iphone-air"); "e" is appended
# without a hyphen ("iphone-17e"); the rest are hyphenated ("iphone-18-pro-max").
_SUFFIX_NONE = {"base", "air"}
_SUFFIX_JOINED = {"e"}


def data_dir() -> Path:
    """Root of the data store. Override with MARKET_SIGNALS_DATA_DIR (absolute or project-relative)."""
    override = os.environ.get("MARKET_SIGNALS_DATA_DIR")
    if not override:
        return PROJECT_ROOT / "data"
    path = Path(override).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


def layer_dir(layer: str, create: bool = False) -> Path:
    """Directory for one data layer (raw, bronze, silver, gold, meta)."""
    if layer not in DATA_LAYERS:
        raise ValueError(f"Unknown data layer {layer!r}; expected one of {DATA_LAYERS}")
    path = data_dir() / layer
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def model_key(family: str, variant: str) -> str:
    """Canonical model_key from a family and variant, e.g. ('iphone-18', 'pro-max') -> 'iphone-18-pro-max'."""
    if variant in _SUFFIX_NONE:
        return family
    if variant in _SUFFIX_JOINED:
        return f"{family}{variant}"
    return f"{family}-{variant}"


def load_active_scope(path: Path | None = None) -> dict[str, list[str]]:
    """Read config/active_scope.yaml and return {'active': [...], 'reference_only': [...]} as model_keys."""
    path = path or CONFIG_DIR / "active_scope.yaml"
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    unknown = set(raw) - {"active", "reference_only"}
    if unknown:
        raise ValueError(f"Unexpected sections in {path.name}: {sorted(unknown)}")

    scope: dict[str, list[str]] = {}
    for section in ("active", "reference_only"):
        families = raw.get(section) or {}
        scope[section] = [model_key(fam, var) for fam, variants in families.items() for var in variants]

    overlap = set(scope["active"]) & set(scope["reference_only"])
    if overlap:
        raise ValueError(f"Models listed as both active and reference_only: {sorted(overlap)}")
    return scope
