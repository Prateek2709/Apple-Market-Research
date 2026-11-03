"""Google Trends: INCOMPLETE.

The plan's route is the official Trends API alpha (application-gated) or, meanwhile, trendspyg
(unofficial). Neither the alpha's request/response format nor trendspyg's interface has been seen, so no
fetch is written and collect() raises IncompleteCollector. What IS implemented is the request planning the
plan specifies, which needs no service knowledge: every request carries the anchor term "iPhone" plus up to
four other terms (so series can later be rescaled to a common reference), and the same plan is repeated
for three pulls per window.
"""

from __future__ import annotations

from .base import Collector, IncompleteCollector, Summary, Target

ANCHOR = "iPhone"
MAX_TERMS_PER_REQUEST = 5  # anchor + 4 others (plan)
PULLS_PER_WINDOW = 3       # averaged later to damp sampling noise (plan)


def plan_term_batches(terms: list[str], anchor: str = ANCHOR) -> list[list[str]]:
    """Batches of [anchor, up to 4 terms]; the anchor itself and duplicates are dropped from the term list."""
    seen: list[str] = []
    for t in terms:
        if t != anchor and t not in seen:
            seen.append(t)
    size = MAX_TERMS_PER_REQUEST - 1
    return [[anchor, *seen[i:i + size]] for i in range(0, len(seen), size)]


class GoogleTrends(Collector):
    name = "trends"
    implementation = "incomplete"
    live_verification = "required (client interface unknown; official API alpha not yet granted)"

    def plan(self) -> list[Target]:
        return []

    def collect(self) -> Summary:
        raise IncompleteCollector(
            "Google Trends collection is not implemented: needs the official API alpha access or a verified "
            "trendspyg interface. See plan_term_batches() for the planned request layout.")
