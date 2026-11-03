"""Small shared parsers. Retailer-page parsers are NOT here: they need real pages (see collectors/retail.py)."""

from __future__ import annotations

import re

_INR = re.compile(r"(?:₹|Rs\.?|INR)\s*([0-9][0-9,]*)(?:\.(\d+))?", re.IGNORECASE)


def parse_inr(text: str) -> int | None:
    """First rupee amount in text as integer rupees; Indian digit grouping is just commas.

    '₹1,64,900' -> 164900. Paise are dropped (rounded down). Returns None when no amount is present.
    """
    m = _INR.search(text or "")
    if not m:
        return None
    return int(m.group(1).replace(",", ""))
