from pathlib import Path

import pytest

from market_signals import config


def test_project_root_contains_pyproject():
    assert (config.PROJECT_ROOT / "pyproject.toml").is_file()


def test_data_dir_default_is_inside_project(monkeypatch):
    monkeypatch.delenv("MARKET_SIGNALS_DATA_DIR", raising=False)
    assert config.data_dir() == config.PROJECT_ROOT / "data"


def test_data_dir_relative_override(monkeypatch):
    monkeypatch.setenv("MARKET_SIGNALS_DATA_DIR", "elsewhere")
    assert config.data_dir() == config.PROJECT_ROOT / "elsewhere"


def test_layer_dir_creates_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("MARKET_SIGNALS_DATA_DIR", str(tmp_path))
    path = config.layer_dir("bronze", create=True)
    assert path == tmp_path / "bronze" and path.is_dir()


def test_layer_dir_rejects_unknown_layer():
    with pytest.raises(ValueError):
        config.layer_dir("platinum")


@pytest.mark.parametrize(
    "family, variant, expected",
    [
        ("iphone-16", "base", "iphone-16"),
        ("iphone-17", "e", "iphone-17e"),
        ("iphone-18", "pro-max", "iphone-18-pro-max"),
        ("iphone-air", "air", "iphone-air"),
    ],
)
def test_model_key(family, variant, expected):
    assert config.model_key(family, variant) == expected


def test_active_scope_matches_plan():
    scope = config.load_active_scope()
    assert sorted(scope["active"]) == sorted(
        [
            "iphone-15",
            "iphone-16",
            "iphone-17",
            "iphone-17e",
            "iphone-17-pro",
            "iphone-17-pro-max",
            "iphone-18-pro",
            "iphone-18-pro-max",
            "iphone-air",
        ]
    )
    assert sorted(scope["reference_only"]) == sorted(
        ["iphone-14", "iphone-16e", "iphone-16-pro", "iphone-16-pro-max"]
    )


def test_active_scope_rejects_overlap(tmp_path: Path):
    bad = tmp_path / "scope.yaml"
    bad.write_text("active:\n  iphone-16: [base]\nreference_only:\n  iphone-16: [base]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="both active and reference_only"):
        config.load_active_scope(bad)
