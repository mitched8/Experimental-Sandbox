"""Fetch active markets from the Polymarket Gamma API."""

import json
import logging
import time
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://gamma-api.polymarket.com"
MARKETS_ENDPOINT = "/markets"
PAGE_SIZE = 100
MAX_PAGES = 10
PAGE_DELAY_S = 0.5
REQUEST_TIMEOUT_S = 15


@dataclass
class RawMarket:
    """A market as returned by the Gamma API, lightly parsed."""

    market_id: str
    slug: str
    question: str
    description: str
    yes_price: float | None
    no_price: float | None
    volume_24h: float
    liquidity: float
    outcome_count: int

    @property
    def url(self) -> str:
        return f"https://polymarket.com/event/{self.slug}"


def fetch_active_markets() -> list[RawMarket]:
    """Fetch all active (open) markets, paginated, ordered by 24h volume desc.

    Returns at most MAX_PAGES * PAGE_SIZE markets.  Binary markets only
    (outcome_count == 2) — multi-outcome markets are skipped.
    """
    markets: list[RawMarket] = []

    with httpx.Client(timeout=REQUEST_TIMEOUT_S) as client:
        for page in range(MAX_PAGES):
            offset = page * PAGE_SIZE
            logger.info("Fetching markets page %d (offset %d)", page + 1, offset)

            try:
                resp = client.get(
                    f"{BASE_URL}{MARKETS_ENDPOINT}",
                    params={
                        "closed": "false",
                        "limit": PAGE_SIZE,
                        "offset": offset,
                        "order": "volume24hr",
                        "ascending": "false",
                    },
                )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("API request failed on page %d: %s", page + 1, exc)
                break

            data = resp.json()
            if not data:
                logger.info("No more results at page %d, stopping", page + 1)
                break

            for item in data:
                market = _parse_market(item)
                if market is not None:
                    markets.append(market)

            logger.info(
                "Page %d: got %d items, %d binary markets total so far",
                page + 1,
                len(data),
                len(markets),
            )

            # Rate-limit: don't hammer the API
            if page < MAX_PAGES - 1 and data:
                time.sleep(PAGE_DELAY_S)

    logger.info("Fetched %d binary markets total", len(markets))
    return markets


def _parse_market(item: dict) -> RawMarket | None:
    """Parse a single API response item into a RawMarket.

    Returns None for multi-outcome markets (outcome_count != 2).
    """
    yes_price, no_price, outcome_count = _parse_outcome_prices(
        item.get("outcomePrices")
    )

    if outcome_count != 2:
        return None

    return RawMarket(
        market_id=item.get("conditionId", ""),
        slug=item.get("slug", ""),
        question=item.get("question", ""),
        description=item.get("description", ""),
        yes_price=yes_price,
        no_price=no_price,
        volume_24h=float(item.get("volume24hr", 0) or 0),
        liquidity=float(item.get("liquidityNum", 0) or 0),
        outcome_count=outcome_count,
    )


def _parse_outcome_prices(raw: str | None) -> tuple[float | None, float | None, int]:
    """Parse the outcomePrices JSON string.

    Returns (yes_price, no_price, outcome_count).
    """
    if not raw:
        return None, None, 0

    try:
        prices = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None, None, 0

    count = len(prices)
    yes_price = float(prices[0]) if count > 0 else None
    no_price = float(prices[1]) if count > 1 else None
    return yes_price, no_price, count
