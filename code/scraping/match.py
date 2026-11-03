"""Match a retailer listing title to the catalogue (plan, "Product identity").

1. Rules extract model, storage and (if named) colour from the title.
2. rapidfuzz token_set_ratio against the alias table is used only as a fallback for titles the
   rules cannot place (typos). token_set_ratio scores a subset of tokens as 100, so on its own it would
   match "iPhone 17 Pro Max 256GB" to "iPhone 17"; that is why rules run first and fuzzy matches are
   never auto-accepted here (deliberately stricter than the plan's >= 90 auto-accept).

Decisions: accept | review | reject | excluded.
A listing matches a sku_id only when its title names the colour; otherwise its price_key.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd
from rapidfuzz import fuzz, process

ACCEPT, REVIEW_LOW = 90, 75

# Plan: refurbished/renewed, open-box, grey-import/international, bundles, accessories.
EXCLUDED_KEYWORDS = (
    "refurbished", "renewed", "open box", "open-box", "pre-owned", "preowned", "used", "second hand",
    "grey import", "international", "imported", "bundle", "combo", "case", "cover", "screen guard",
    "tempered", "charger", "cable", "protector", "skin", "dummy",
)
# Tokens that, directly after a catalogue model name, mean a different (out-of-catalogue) model.
_QUALIFIERS = {"pro", "max", "plus", "mini", "air", "e", "se"}
_STORAGE = re.compile(r"(\d+)\s*(gb|tb)\b")


@dataclass(frozen=True)
class MatchResult:
    decision: str
    price_key: str = ""
    sku_id: str = ""
    model_key: str = ""
    score: float = 0.0
    reason: str = ""


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _find(tokens: list[str], phrase: list[str]) -> int:
    n = len(phrase)
    for i in range(len(tokens) - n + 1):
        if tokens[i:i + n] == phrase:
            return i
    return -1


class Matcher:
    def __init__(self, active: pd.DataFrame, reference: pd.DataFrame | None = None):
        rows = [active] + ([reference] if reference is not None and len(reference) else [])
        cat = pd.concat(rows, ignore_index=True)
        self._models = {r.model_key: r.model for r in cat.drop_duplicates("model_key").itertuples()}
        self._by_len = sorted(self._models.items(), key=lambda kv: -len(_tokens(kv[1])))
        self._storages = {(r.model_key, int(r.storage_gb)) for r in cat.itertuples()}
        self._colours: dict[str, dict[str, str]] = {}
        if "sku_id" in active.columns:
            for r in active.itertuples():
                self._colours.setdefault(r.model_key, {})[r.colour] = r.sku_id
        self._sku = {(r.model_key, int(r.storage_gb), r.colour): r.sku_id for r in active.itertuples()}
        self._alias_names = {f"apple {name.lower()}": key for key, name in self._models.items()}

    def match(self, title: str) -> MatchResult:
        low = title.lower()
        for kw in EXCLUDED_KEYWORDS:
            if re.search(rf"\b{re.escape(kw)}\b", low):
                return MatchResult("excluded", reason=f"excluded keyword: {kw}")
        tokens = _tokens(title)

        model_key = ""
        for key, name in self._by_len:
            phrase = _tokens(name)
            i = _find(tokens, phrase)
            if i < 0:
                continue
            nxt = tokens[i + len(phrase)] if i + len(phrase) < len(tokens) else ""
            if nxt in _QUALIFIERS:
                return MatchResult("reject", reason=f"qualifier '{nxt}' after {name}: model not in catalogue")
            model_key = key
            break

        if not model_key:
            best = process.extractOne(" ".join(tokens), list(self._alias_names), scorer=fuzz.token_set_ratio)
            if best and best[1] >= REVIEW_LOW:
                return MatchResult("review", model_key=self._alias_names[best[0]], score=best[1],
                                   reason="fuzzy model match only; needs manual confirmation")
            return MatchResult("reject", score=best[1] if best else 0.0, reason="no catalogue model in title")

        m = _STORAGE.search(low)
        if not m:
            return MatchResult("review", model_key=model_key, score=REVIEW_LOW, reason="storage not in title")
        storage_gb = int(m.group(1)) * (1024 if m.group(2) == "tb" else 1)
        if (model_key, storage_gb) not in self._storages:
            return MatchResult("reject", model_key=model_key, reason=f"{storage_gb}GB not offered for {model_key}")

        price_key = f"{model_key}|{storage_gb}gb" if storage_gb < 1024 else f"{model_key}|{storage_gb // 1024}tb"
        colour_hit = next((c for c in self._colours.get(model_key, {})
                           if _find(tokens, _tokens(c)) >= 0), "")
        sku = self._sku.get((model_key, storage_gb, colour_hit), "") if colour_hit else ""
        return MatchResult("accept", price_key=price_key, sku_id=sku, model_key=model_key, score=100.0,
                           reason="" if sku else "colour not named: price_key only")
