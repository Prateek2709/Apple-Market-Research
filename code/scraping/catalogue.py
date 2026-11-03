"""Build and validate the independent product catalogue (config/products.csv).

Inputs : config/active_scope.yaml (what is in scope) and config/model_specs.yaml (India facts).
Outputs: config/products.csv             one row per active model x storage x colour (sku_id grain)
         config/reference_models.csv   one row per reference-only model x storage (price_key grain;
                                          colour is not needed for predecessor comparisons)

Keys (plan, "Final dataset and product catalogue"):
    sku_id    = model_key|storage|colour   e.g. iphone-18-pro-max|256gb|silver
    price_key = model_key|storage          e.g. iphone-18-pro-max|256gb
    model_key = model                      e.g. iphone-18-pro-max

Nothing here fetches data; it only joins the two checked-in files. Run from the project root:
    python run.py catalogue build
    python run.py catalogue validate
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import yaml

from scraping import settings

SPECS_PATH: Path = settings.CONFIG_DIR / "model_specs.yaml"
PRODUCTS_PATH: Path = settings.CONFIG_DIR / "products.csv"
REFERENCE_PATH: Path = settings.CONFIG_DIR / "reference_models.csv"

PRODUCT_COLUMNS = [
    "sku_id", "price_key", "model_key", "model", "generation", "tier",
    "storage_gb", "colour", "scope_status", "segment",
    "india_launch_date", "india_launch_mrp", "apple_store_status", "apple_delisted_date",
    "predecessor_price_key", "predecessor_model_key", "mapping_type", "mapping_note",
    "verified_on", "verified_source", "unverified_fields",
]
# Reference rows have no colour, so no sku_id / colour columns.
REFERENCE_COLUMNS = [c for c in PRODUCT_COLUMNS if c not in ("sku_id", "colour")]

APPLE_STORE_STATUSES = {"listed", "delisted", "unknown"}
MAPPING_TYPES = {"exact", "none"}
_STORAGE_TOKEN = re.compile(r"^\d+(gb|tb)$")


def storage_token(storage_gb: int) -> str:
    """256 -> '256gb', 1024 -> '1tb', 2048 -> '2tb'."""
    return f"{storage_gb // 1024}tb" if storage_gb >= 1024 and storage_gb % 1024 == 0 else f"{storage_gb}gb"


def colour_slug(colour: str) -> str:
    """'Mist Blue' -> 'mist-blue'."""
    return re.sub(r"[^a-z0-9]+", "-", colour.lower()).strip("-")


def price_key(model_key: str, storage_gb: int) -> str:
    return f"{model_key}|{storage_token(storage_gb)}"


def sku_id(model_key: str, storage_gb: int, colour: str) -> str:
    return f"{price_key(model_key, storage_gb)}|{colour_slug(colour)}"


def load_specs(path: Path | None = None) -> dict:
    with open(path or SPECS_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _predecessor_fields(spec: dict, storage_gb: int, specs: dict) -> dict:
    """Predecessor mapping by model and exact storage; never by colour, never a neighbouring capacity."""
    pred_key = spec.get("predecessor")
    if not pred_key:
        return {"predecessor_price_key": "", "predecessor_model_key": "", "mapping_type": "none",
                "mapping_note": "no like-for-like predecessor"}
    pred = specs["models"][pred_key]
    if storage_gb in pred["storage_mrp"]:
        return {"predecessor_price_key": price_key(pred_key, storage_gb), "predecessor_model_key": pred_key,
                "mapping_type": "exact", "mapping_note": ""}
    return {"predecessor_price_key": "", "predecessor_model_key": pred_key, "mapping_type": "none",
            "mapping_note": f"{pred['model']} never offered {storage_token(storage_gb)}"}


def _row(model_key: str, spec: dict, storage_gb: int, scope_status: str, specs: dict) -> dict:
    defaults = specs["defaults"]
    mrp = spec["storage_mrp"][storage_gb]
    unverified = list(defaults["common_unverified"]) + list(spec.get("unverified") or [])
    if mrp is None:
        unverified.append("india_launch_mrp")
    row = {
        "price_key": price_key(model_key, storage_gb),
        "model_key": model_key,
        "model": spec["model"],
        "generation": spec["generation"],
        "tier": spec["tier"],
        "storage_gb": storage_gb,
        "scope_status": scope_status,
        "segment": spec["segment"],
        "india_launch_date": spec["india_launch_date"],
        "india_launch_mrp": "" if mrp is None else int(mrp),
        "apple_store_status": spec["apple_store"],
        "apple_delisted_date": "",  # no delisting date has been verified for any model
        "verified_on": defaults["verified_on"],
        "verified_source": defaults["verified_source"],
        "unverified_fields": ";".join(unverified),
    }
    row.update(_predecessor_fields(spec, storage_gb, specs))
    return row


def build_catalogue(specs: dict | None = None, scope: dict[str, list[str]] | None = None
                    ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (products, reference_models) for the models named in the active-scope config."""
    specs = specs or load_specs()
    scope = scope or settings.load_active_scope()
    missing = [m for m in scope["active"] + scope["reference_only"] if m not in specs["models"]]
    if missing:
        raise ValueError(f"Models in active_scope.yaml with no entry in model_specs.yaml: {missing}")

    products: list[dict] = []
    for model_key in scope["active"]:
        spec = specs["models"][model_key]
        if not spec["colours"]:
            raise ValueError(f"Active model {model_key} has no colours in model_specs.yaml")
        for storage_gb in sorted(spec["storage_mrp"]):
            base = _row(model_key, spec, storage_gb, "active", specs)
            for colour in spec["colours"]:
                row = dict(base, colour=colour)
                row["sku_id"] = sku_id(model_key, storage_gb, colour)
                products.append(row)

    reference: list[dict] = []
    for model_key in scope["reference_only"]:
        spec = specs["models"][model_key]
        for storage_gb in sorted(spec["storage_mrp"]):
            reference.append(_row(model_key, spec, storage_gb, "reference_only", specs))

    return (pd.DataFrame(products, columns=PRODUCT_COLUMNS),
            pd.DataFrame(reference, columns=REFERENCE_COLUMNS))


def validate_catalogue(products: pd.DataFrame, reference: pd.DataFrame,
                       scope: dict[str, list[str]] | None = None) -> list[str]:
    """Return a list of problems (empty list = valid)."""
    scope = scope or settings.load_active_scope()
    errors: list[str] = []

    # --- uniqueness and key consistency
    if products["sku_id"].duplicated().any():
        errors.append(f"duplicate sku_id: {products.loc[products['sku_id'].duplicated(), 'sku_id'].tolist()}")
    if reference["price_key"].duplicated().any():
        errors.append("duplicate price_key in reference_models")
    for df, name in ((products, "products"), (reference, "reference_models")):
        for r in df.itertuples():
            if r.price_key != f"{r.model_key}|{storage_token(int(r.storage_gb))}":
                errors.append(f"{name}: price_key {r.price_key} inconsistent with model/storage")
            if not _STORAGE_TOKEN.match(r.price_key.split("|")[1]):
                errors.append(f"{name}: bad storage token in {r.price_key}")
    for r in products.itertuples():
        if r.sku_id != f"{r.price_key}|{colour_slug(r.colour)}":
            errors.append(f"sku_id {r.sku_id} inconsistent with price_key/colour")

    # --- scope: exactly the configured models, nothing else
    if set(products["model_key"]) != set(scope["active"]):
        errors.append(f"active models {sorted(set(products['model_key']))} != scope {sorted(scope['active'])}")
    if set(reference["model_key"]) != set(scope["reference_only"]):
        errors.append("reference models do not match reference_only scope")
    if set(products["scope_status"]) != {"active"}:
        errors.append("products.csv must contain only scope_status=active")
    if set(reference["scope_status"]) != {"reference_only"}:
        errors.append("reference_models.csv must contain only scope_status=reference_only")

    # --- price_key-level attributes must not vary by colour (price varies by model x storage only)
    for col in ("india_launch_mrp", "india_launch_date", "predecessor_price_key", "mapping_type", "segment"):
        if (products.groupby("price_key")[col].nunique(dropna=False) > 1).any():
            errors.append(f"{col} varies by colour within a price_key")

    # --- field validity
    for df, name in ((products, "products"), (reference, "reference_models")):
        for r in df.itertuples():
            try:
                date.fromisoformat(r.india_launch_date)
            except ValueError:
                errors.append(f"{name}: bad india_launch_date for {r.price_key}")
            if r.india_launch_mrp != "" and not int(r.india_launch_mrp) > 0:
                errors.append(f"{name}: non-positive MRP for {r.price_key}")
            if r.apple_store_status not in APPLE_STORE_STATUSES:
                errors.append(f"{name}: bad apple_store_status for {r.price_key}")
            if r.mapping_type not in MAPPING_TYPES:
                errors.append(f"{name}: bad mapping_type for {r.price_key}")
            if r.apple_delisted_date != "":
                try:
                    date.fromisoformat(r.apple_delisted_date)
                except ValueError:
                    errors.append(f"{name}: bad apple_delisted_date for {r.price_key}")
    if products["colour"].isna().any() or (products["colour"] == "").any():
        errors.append("active SKU with empty colour")

    # --- predecessor mappings: same storage, earlier launch, known target, none => empty target
    known = pd.concat([products.drop_duplicates("price_key"), reference]).set_index("price_key")
    for r in pd.concat([products.drop_duplicates("price_key"), reference]).itertuples():
        if r.mapping_type == "exact":
            if r.predecessor_price_key not in known.index:
                errors.append(f"{r.price_key}: predecessor {r.predecessor_price_key} not in catalogue")
                continue
            pred = known.loc[r.predecessor_price_key]
            if int(pred.storage_gb) != int(r.storage_gb):
                errors.append(f"{r.price_key}: predecessor storage differs (no substitution allowed)")
            if pred.india_launch_date >= r.india_launch_date:
                errors.append(f"{r.price_key}: predecessor not launched earlier")
            if r.predecessor_model_key != pred.model_key:
                errors.append(f"{r.price_key}: predecessor_model_key mismatch")
        elif r.predecessor_price_key != "":
            errors.append(f"{r.price_key}: mapping_type none but predecessor_price_key set")
    return errors


def write_catalogue(products: pd.DataFrame, reference: pd.DataFrame,
                    products_path: Path = PRODUCTS_PATH, reference_path: Path = REFERENCE_PATH) -> None:
    for df, path in ((products, products_path), (reference, reference_path)):
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")


def read_csv(path: Path) -> pd.DataFrame:
    """Read a catalogue CSV with empty cells kept as '' (not NaN)."""
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8").astype(
        {"storage_gb": int}
    )


def summary(products: pd.DataFrame, reference: pd.DataFrame) -> str:
    lines = [f"active SKUs: {len(products)}   price_keys: {products['price_key'].nunique()}   "
             f"models: {products['model_key'].nunique()}   reference price_keys: {len(reference)}"]
    per = products.groupby("model_key").agg(skus=("sku_id", "size"), price_keys=("price_key", "nunique"))
    lines += [f"  {k:20s} skus={v.skus:3d} price_keys={v.price_keys}" for k, v in per.iterrows()]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python run.py catalogue")
    parser.add_argument("command", choices=["build", "validate"])
    args = parser.parse_args(argv)

    if args.command == "build":
        products, reference = build_catalogue()
        errors = validate_catalogue(products, reference)
        if errors:
            print("\n".join(errors), file=sys.stderr)
            return 1
        write_catalogue(products, reference)
        print(f"wrote {PRODUCTS_PATH.relative_to(settings.PROJECT_ROOT)} and "
              f"{REFERENCE_PATH.relative_to(settings.PROJECT_ROOT)}")
        print(summary(products, reference))
        return 0

    products, reference = read_csv(PRODUCTS_PATH), read_csv(REFERENCE_PATH)
    errors = validate_catalogue(products, reference)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    # the checked-in CSVs must equal a fresh build from the specs
    fresh_p, fresh_r = build_catalogue()
    stale = [n for n, a, b in (("products.csv", products, fresh_p), ("reference_models.csv", reference, fresh_r))
             if not a.equals(b.astype(str).astype({"storage_gb": int}))]
    if stale:
        print(f"stale (rebuild with `build`): {stale}", file=sys.stderr)
        return 1
    print("catalogue valid")
    print(summary(products, reference))
    return 0


if __name__ == "__main__":
    sys.exit(main())
