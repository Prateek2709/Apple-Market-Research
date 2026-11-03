import pandas as pd
import pytest

from scraping import catalogue as cat
from scraping import settings


@pytest.fixture(scope="module")
def built():
    return cat.build_catalogue()


@pytest.fixture(scope="module")
def products(built):
    return built[0]


@pytest.fixture(scope="module")
def reference(built):
    return built[1]


def test_key_helpers():
    assert cat.storage_token(256) == "256gb"
    assert cat.storage_token(1024) == "1tb"
    assert cat.storage_token(2048) == "2tb"
    assert cat.colour_slug("Mist Blue") == "mist-blue"
    assert cat.sku_id("iphone-18-pro-max", 256, "Silver") == "iphone-18-pro-max|256gb|silver"


def test_built_catalogue_is_valid(products, reference):
    assert cat.validate_catalogue(products, reference) == []


def test_checked_in_csvs_match_fresh_build(products, reference):
    on_disk = cat.read_csv(cat.PRODUCTS_PATH)
    assert on_disk.equals(products.astype(str).astype({"storage_gb": int}))
    ref_disk = cat.read_csv(cat.REFERENCE_PATH)
    assert ref_disk.equals(reference.astype(str).astype({"storage_gb": int}))


# ---- uniqueness
def test_sku_ids_unique(products):
    assert products["sku_id"].is_unique


def test_one_mrp_per_price_key(products):
    assert (products.groupby("price_key")["india_launch_mrp"].nunique() == 1).all()


# ---- counts (plan: 81 verified-family SKUs + 30 for the 15/16 base models)
def test_sku_counts(products):
    counts = products.groupby("model_key").size().to_dict()
    assert counts == {
        "iphone-18-pro": 16, "iphone-18-pro-max": 16, "iphone-17-pro": 9, "iphone-17-pro-max": 12,
        "iphone-17": 10, "iphone-17e": 6, "iphone-air": 12, "iphone-16": 15, "iphone-15": 15,
    }
    assert len(products) == 111
    assert products[~products["model_key"].isin(["iphone-15", "iphone-16"])].shape[0] == 81


# ---- scope exclusions
EXCLUDED = ["iphone-16e", "iphone-15-plus", "iphone-15-pro", "iphone-15-pro-max", "iphone-16-plus",
            "iphone-16-pro", "iphone-16-pro-max", "iphone-duo", "iphone-18", "iphone-18e", "iphone-air-2",
            "iphone-14"]


@pytest.mark.parametrize("model_key", EXCLUDED)
def test_excluded_models_not_in_products(products, model_key):
    assert model_key not in set(products["model_key"])


def test_reference_models_have_no_active_rows(products, reference):
    assert set(reference["model_key"]) == {"iphone-14", "iphone-16e", "iphone-16-pro", "iphone-16-pro-max"}
    assert not set(reference["model_key"]) & set(products["model_key"])
    assert "colour" not in reference.columns and "sku_id" not in reference.columns


def test_scope_change_needs_no_code_change():
    """Dropping a model from the scope config removes it from the build."""
    scope = settings.load_active_scope()
    scope["active"] = [m for m in scope["active"] if m != "iphone-15"]
    scope["reference_only"] = scope["reference_only"] + []  # 14 stays a harmless reference
    products, _ = cat.build_catalogue(scope=scope)
    assert "iphone-15" not in set(products["model_key"])


def test_scope_model_without_specs_is_an_error():
    scope = settings.load_active_scope()
    scope["active"] = scope["active"] + ["iphone-19"]
    with pytest.raises(ValueError, match="iphone-19"):
        cat.build_catalogue(scope=scope)


# ---- valid configurations (as listed in the plan)
def configs(products, model):
    sub = products[products["model_key"] == model]
    return sorted(sub["storage_gb"].unique()), sorted(sub["colour"].unique())


@pytest.mark.parametrize(
    "model, storages, colours",
    [
        ("iphone-18-pro", [256, 512, 1024, 2048], ["Black", "Burgundy", "Glacier", "Silver"]),
        ("iphone-18-pro-max", [256, 512, 1024, 2048], ["Black", "Burgundy", "Glacier", "Silver"]),
        ("iphone-17-pro", [256, 512, 1024], ["Cosmic Orange", "Deep Blue", "Silver"]),
        ("iphone-17-pro-max", [256, 512, 1024, 2048], ["Cosmic Orange", "Deep Blue", "Silver"]),
        ("iphone-17", [256, 512], ["Black", "Lavender", "Mist Blue", "Sage", "White"]),
        ("iphone-17e", [256, 512], ["Black", "Soft Pink", "White"]),
        ("iphone-air", [256, 512, 1024], ["Cloud White", "Light Gold", "Sky Blue", "Space Black"]),
        ("iphone-16", [128, 256, 512], ["Black", "Pink", "Teal", "Ultramarine", "White"]),
        ("iphone-15", [128, 256, 512], ["Black", "Blue", "Green", "Pink", "Yellow"]),
    ],
)
def test_configurations(products, model, storages, colours):
    assert configs(products, model) == (storages, colours)
    sub = products[products["model_key"] == model]
    assert len(sub) == len(storages) * len(colours)  # full cross-product, no gaps or extras


def test_launch_dates_and_mrps(products):
    first = products.drop_duplicates("price_key").set_index("price_key")
    assert first.loc["iphone-18-pro-max|256gb", "india_launch_date"] == "2026-09-18"
    assert first.loc["iphone-18-pro-max|256gb", "india_launch_mrp"] == 179900
    assert first.loc["iphone-18-pro-max|2tb", "india_launch_mrp"] == 329900
    assert first.loc["iphone-17e|256gb", "india_launch_date"] == "2026-03-11"
    assert first.loc["iphone-15|128gb", "india_launch_date"] == "2023-09-22"
    assert first.loc["iphone-air|256gb", "india_launch_mrp"] == 119900


def test_price_does_not_vary_by_colour(products):
    for col in ("india_launch_mrp", "predecessor_price_key", "segment"):
        assert (products.groupby("price_key")[col].nunique() == 1).all()


def test_segments(products):
    seg = products.drop_duplicates("model_key").set_index("model_key")["segment"].to_dict()
    assert seg["iphone-18-pro"] == "Pro" and seg["iphone-18-pro-max"] == "Pro Max"
    assert seg["iphone-air"] == "Air"
    assert {seg[m] for m in ("iphone-15", "iphone-16", "iphone-17", "iphone-17e")} == {"Entry and base"}


# ---- predecessor mappings (plan, section B)
def mapping(products, reference, price_key):
    both = pd.concat([products.drop_duplicates("price_key"), reference]).set_index("price_key")
    row = both.loc[price_key]
    return row.mapping_type, row.predecessor_price_key


@pytest.mark.parametrize(
    "price_key, expected",
    [
        ("iphone-18-pro-max|2tb", ("exact", "iphone-17-pro-max|2tb")),
        ("iphone-18-pro-max|256gb", ("exact", "iphone-17-pro-max|256gb")),
        ("iphone-18-pro|2tb", ("none", "")),  # 17 Pro tops out at 1TB; no substitution
        ("iphone-18-pro|1tb", ("exact", "iphone-17-pro|1tb")),
        ("iphone-17|256gb", ("exact", "iphone-16|256gb")),
        ("iphone-17-pro|256gb", ("exact", "iphone-16-pro|256gb")),
        ("iphone-17-pro-max|2tb", ("none", "")),  # 16 Pro Max tops out at 1TB
        ("iphone-17e|512gb", ("exact", "iphone-16e|512gb")),
        ("iphone-16|128gb", ("exact", "iphone-15|128gb")),
        ("iphone-15|512gb", ("exact", "iphone-14|512gb")),
        ("iphone-air|256gb", ("none", "")),
    ],
)
def test_predecessor_mapping(products, reference, price_key, expected):
    assert mapping(products, reference, price_key) == expected


def test_predecessor_storage_always_matches(products, reference):
    both = pd.concat([products.drop_duplicates("price_key"), reference]).set_index("price_key")
    exact = both[both["mapping_type"] == "exact"]
    assert len(exact) > 0
    for price_key, row in exact.iterrows():
        assert both.loc[row.predecessor_price_key, "storage_gb"] == row.storage_gb


def test_air_has_no_predecessor(products):
    air = products[products["model_key"] == "iphone-air"]
    assert (air["mapping_type"] == "none").all() and (air["predecessor_price_key"] == "").all()


# ---- unverified fields are declared, never silently blank
def test_unverified_fields_declared(products, reference):
    assert (products["unverified_fields"].str.contains("apple_india_configurator")).all()
    assert (products["apple_delisted_date"] == "").all()  # none verified


# ---- validator catches broken catalogues
def test_validator_catches_duplicate_sku(products, reference):
    bad = pd.concat([products, products.iloc[[0]]], ignore_index=True)
    assert any("duplicate sku_id" in e for e in cat.validate_catalogue(bad, reference))


def test_validator_catches_out_of_scope_model(products, reference):
    extra = products.iloc[[0]].copy()
    extra["model_key"] = "iphone-16-plus"
    extra["price_key"] = "iphone-16-plus|256gb"
    extra["sku_id"] = "iphone-16-plus|256gb|black"
    bad = pd.concat([products, extra], ignore_index=True)
    assert any("!= scope" in e for e in cat.validate_catalogue(bad, reference))


def test_validator_catches_substituted_storage(products, reference):
    bad = products.copy()
    mask = bad["price_key"] == "iphone-18-pro|2tb"
    bad.loc[mask, "mapping_type"] = "exact"
    bad.loc[mask, "predecessor_price_key"] = "iphone-17-pro|1tb"
    bad.loc[mask, "predecessor_model_key"] = "iphone-17-pro"
    assert any("predecessor storage differs" in e for e in cat.validate_catalogue(bad, reference))


def test_validator_catches_colour_dependent_price(products, reference):
    bad = products.copy()
    i = bad.index[bad["price_key"] == "iphone-17|256gb"][0]
    bad.loc[i, "india_launch_mrp"] = 1
    assert any("varies by colour" in e for e in cat.validate_catalogue(bad, reference))
