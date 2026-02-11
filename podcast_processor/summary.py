"""Pass 1: Summary generation — produce a structured summary with stance tracking using Claude Sonnet."""

import logging

import anthropic

from .config import PodcastCorrections, SummarisationConfig
from .stance import format_stance_for_prompt
from .transcription import TranscriptResult

logger = logging.getLogger(__name__)


def generate_summary(
    transcript: TranscriptResult,
    episode_title: str,
    episode_date: str,
    series_name: str,
    anthropic_api_key: str,
    stance: dict | None = None,
    corrections: PodcastCorrections | None = None,
    config: SummarisationConfig | None = None,
) -> str:
    """Generate a structured summary with What's Changed tracking (Pass 1).

    Returns the raw markdown output from Claude for further validation.
    """
    if config is None:
        config = SummarisationConfig()

    client = anthropic.Anthropic(api_key=anthropic_api_key)

    # Build attributed transcript text
    if transcript.utterances:
        transcript_text = "\n".join(
            f"{u.speaker}: {u.text}" for u in transcript.utterances
        )
    else:
        transcript_text = transcript.raw_text

    # Build speaker roster section
    roster_section = ""
    if corrections and corrections.speaker_roster:
        roster_lines = ["Known speakers for this series:"]
        for s in corrections.speaker_roster:
            roster_lines.append(f"- {s.name} ({s.role}) — covers: {s.coverage}")
        roster_section = "\n".join(roster_lines)

    # Build stance context
    stance_section = ""
    if stance:
        stance_yaml = format_stance_for_prompt(stance)
        stance_section = f"""
The following is the current known stance file for this podcast series.
Compare the views expressed in this episode against these existing views to populate the "What's Changed" section.

<current_stance>
{stance_yaml}
</current_stance>
"""
    else:
        stance_section = """
No existing stance file exists for this series. This is the first episode being processed.
Treat all views as NEW (🆕) in the "What's Changed" section.
"""

    system_prompt = f"""You are a senior FX strategist summarising a podcast episode for a trading desk.
Your audience already knows markets — do not explain basic concepts. Be precise with levels, pairs, and timeframes.

{roster_section}

{stance_section}

Critical rules:
- NEVER include the full transcript in the output
- NEVER reproduce garbled or clearly erroneous transcription text — paraphrase instead
- Use standard market convention for currency pairs and levels (e.g. USD/JPY not dollar-yen)
- Distinguish base case views from risk scenarios
- Distinguish event-driven updates from structural macro shifts
- For the What's Changed table, be specific with numbers and levels, not just "more bullish"
"""

    user_prompt = f"""Analyse this podcast episode and produce a structured summary.

Episode: "{episode_title}"
Date: {episode_date}
Series: {series_name}

<transcript>
{transcript_text}
</transcript>

Produce output in EXACTLY this format:

---
title: "{episode_title}"
date: "{episode_date}"
source: "{series_name}"
series: "{series_name}"
tags:
  - podcast
  - fx-strategy
---

## What's Changed

| Currency/Theme | Change | Detail |
|---|---|---|
Use these categories:
- 🔼/🔽 Conviction change (target moved, conviction upgraded/downgraded)
- 🔄 Narrative shift (same direction, different reasoning)
- 🆕 New theme (not previously discussed)
- ⚠️ View reversal (direction flipped)
- ➡️ Unchanged (explicitly reaffirmed)
- 🗑️ Dropped (previously discussed, now absent)

Lead with changes before continuations. Be specific with numbers/levels.

## Trade Recommendations

| Pair | Direction | Target | Timeframe | Notes |
|---|---|---|---|---|

Include all explicit trade recommendations and positioning calls mentioned.

## Summary

3-5 paragraphs of prose for someone who already knows markets. Cover the main themes, reasoning, and conclusions.

## Notable Quotes

2-4 maximum. Only include quotes where the transcription quality is clearly high. Format as:
> "Quote text" — Speaker Name

## Desk Relevance (FX Options)

3-6 bullets on implications for an FX options desk:
- Vol surface implications (skew, term structure)
- Expected flow and positioning
- Structures worth considering
- Event risk and binary outcomes
- Any explicit vol or options commentary from the podcast

## Stance Updates

```yaml
macro_framework:
  # key: view updates
currency_views:
  # CCY:
  #   direction: bullish/bearish/neutral
  #   target: "level or range"
  #   conviction: high/medium/low
  #   narrative: "brief reasoning"
```

Populate the stance updates YAML with all views expressed in this episode. Use the currency ISO codes as keys."""

    logger.info("Pass 1: Generating summary with %s", config.pass1_model)
    response = client.messages.create(
        model=config.pass1_model,
        max_tokens=config.max_tokens_pass1,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    result = response.content[0].text
    logger.info("Pass 1 complete: %d characters", len(result))
    return result
