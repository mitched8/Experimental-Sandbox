"""Claude-based FX relevance classification for filtered markets."""

import json
import logging
from dataclasses import dataclass

import anthropic

from .keywords import FilteredMarket

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"
BATCH_SIZE = 30
DEFAULT_SCORE = 5


@dataclass
class ScoredMarket:
    """A market with an FX relevance score from Claude."""

    market: FilteredMarket
    fx_score: int              # 0-10
    fx_reason: str
    affected_pairs: list[str]  # e.g. ["EUR/USD", "USD/JPY"]


def classify_markets(
    markets: list[FilteredMarket],
    anthropic_api_key: str,
) -> list[ScoredMarket]:
    """Score a list of filtered markets for FX relevance using Claude.

    Markets are sent in batches of ~BATCH_SIZE.  If a batch fails, markets
    in that batch receive DEFAULT_SCORE.
    """
    if not markets:
        return []

    client = anthropic.Anthropic(api_key=anthropic_api_key)
    scored: list[ScoredMarket] = []

    for i in range(0, len(markets), BATCH_SIZE):
        batch = markets[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        logger.info("Classifying batch %d (%d markets)", batch_num, len(batch))

        try:
            batch_scores = _classify_batch(client, batch)
            scored.extend(batch_scores)
        except Exception:
            logger.exception("Batch %d classification failed, assigning default scores", batch_num)
            for fm in batch:
                scored.append(
                    ScoredMarket(
                        market=fm,
                        fx_score=DEFAULT_SCORE,
                        fx_reason="Classification failed — default score",
                        affected_pairs=[],
                    )
                )

    logger.info("Classified %d markets total", len(scored))
    return scored


def _classify_batch(
    client: anthropic.Anthropic,
    batch: list[FilteredMarket],
) -> list[ScoredMarket]:
    """Send a batch of markets to Claude for FX relevance scoring."""
    # Build the market list for the prompt
    market_entries = []
    for idx, fm in enumerate(batch):
        market_entries.append({
            "index": idx,
            "question": fm.market.question,
            "description": fm.market.description[:300],  # truncate long descriptions
            "yes_price": fm.market.yes_price,
            "volume_24h": fm.market.volume_24h,
            "matched_categories": fm.matched_categories,
        })

    prompt = f"""You are an FX markets analyst. Score each prediction market below for its relevance to foreign exchange markets on a scale of 0-10.

Scoring guide:
- 9-10: Directly about currencies, exchange rates, or central bank rate decisions
- 7-8: Strongly affects FX (major trade policy, sovereign debt events, key macro data)
- 4-6: Indirect FX impact (geopolitical events, elections that may shift policy)
- 1-3: Weak or speculative FX connection
- 0: No FX relevance

<markets>
{json.dumps(market_entries, indent=2)}
</markets>

Return a JSON array with one object per market, in the same order. Each object must have:
- "index": the market index number
- "fx_score": integer 0-10
- "fx_reason": one-sentence explanation (max 100 chars)
- "affected_pairs": array of currency pairs affected, e.g. ["EUR/USD", "USD/JPY"]. Empty array if none.

Return ONLY the JSON array, no other text."""

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    return _parse_batch_response(response.content[0].text, batch)


def _parse_batch_response(
    text: str,
    batch: list[FilteredMarket],
) -> list[ScoredMarket]:
    """Parse Claude's JSON response into ScoredMarket objects."""
    # Strip markdown code fences if present
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    scores_list = json.loads(text)

    # Index the parsed scores by their index field
    scores_by_idx: dict[int, dict] = {}
    for item in scores_list:
        scores_by_idx[item["index"]] = item

    results: list[ScoredMarket] = []
    for idx, fm in enumerate(batch):
        score_data = scores_by_idx.get(idx, {})
        results.append(
            ScoredMarket(
                market=fm,
                fx_score=int(score_data.get("fx_score", DEFAULT_SCORE)),
                fx_reason=score_data.get("fx_reason", "No reason provided"),
                affected_pairs=score_data.get("affected_pairs", []),
            )
        )

    return results
