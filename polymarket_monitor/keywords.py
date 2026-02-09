"""Keyword filter — cheap first-pass to narrow markets to FX-relevant subset."""

import logging
import re
from dataclasses import dataclass

from .fetcher import RawMarket

logger = logging.getLogger(__name__)

# Categorised keyword list — tuned for FX relevance.
# Edit this dict to adjust what gets flagged.
FX_KEYWORDS: dict[str, list[str]] = {
    "central_banks": [
        "fed", "ecb", "boe", "boj", "rba", "fomc",
        "powell", "lagarde", "ueda", "bailey",
        "interest rate", "rate cut", "rate hike", "rate hold",
    ],
    "macro": [
        "recession", "gdp", "inflation", "cpi", "pce",
        "unemployment", "payrolls", "nonfarm", "jobs report",
    ],
    "trade": [
        "tariff", "trade war", "sanctions", "trade deal", "import duty",
    ],
    "geopolitics": [
        "china", "taiwan", "ukraine", "russia", "iran", "opec",
        "nato", "north korea", "middle east",
    ],
    "currencies": [
        "dollar", "euro", "yen", "pound", "yuan", "renminbi",
        "currency", "forex", "fx", "exchange rate",
        "usd", "eur", "gbp", "jpy", "cny", "aud", "cad", "chf",
    ],
    "fiscal": [
        "debt ceiling", "shutdown", "deficit", "treasury",
        "yield curve", "government spending", "fiscal",
    ],
}

# Pre-compile a combined pattern for fast matching.
# Use \b...\b with optional trailing 's' to catch common plurals
# (e.g. "tariff" matches "tariffs", "sanction" matches "sanctions").
_ALL_KEYWORDS = [kw for group in FX_KEYWORDS.values() for kw in group]
_KEYWORD_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(kw) for kw in _ALL_KEYWORDS) + r")s?\b",
    re.IGNORECASE,
)

# Build category lookup: keyword -> category name
_KEYWORD_TO_CATEGORY: dict[str, str] = {}
for _cat, _kws in FX_KEYWORDS.items():
    for _kw in _kws:
        _KEYWORD_TO_CATEGORY[_kw.lower()] = _cat


@dataclass
class FilteredMarket:
    """A market that passed the keyword filter, with match metadata."""

    market: RawMarket
    matched_categories: list[str]
    matched_keywords: list[str]


def filter_markets(markets: list[RawMarket]) -> list[FilteredMarket]:
    """Filter markets by keyword relevance. Returns only those that match."""
    results: list[FilteredMarket] = []

    for market in markets:
        searchable = f"{market.question} {market.description}".lower()
        matches = _KEYWORD_PATTERN.findall(searchable)

        if not matches:
            continue

        # Deduplicate and find categories
        unique_keywords = sorted(set(m.lower() for m in matches))
        categories = sorted(set(
            _KEYWORD_TO_CATEGORY[kw]
            for kw in unique_keywords
            if kw in _KEYWORD_TO_CATEGORY
        ))

        results.append(
            FilteredMarket(
                market=market,
                matched_categories=categories,
                matched_keywords=unique_keywords,
            )
        )

    logger.info(
        "Keyword filter: %d / %d markets passed",
        len(results),
        len(markets),
    )
    return results
