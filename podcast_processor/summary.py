"""Summary generation — produce a structured summary using Claude."""

import logging
from dataclasses import dataclass

import anthropic

from .transcription import TranscriptResult

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"


@dataclass
class EpisodeSummary:
    summary: str            # 3-5 paragraph narrative summary
    themes: list[str]       # key themes / topics
    trade_recommendations: list[str]  # specific trade recs, positioning, forecasts
    notable_quotes: list[str]


def generate_summary(
    transcript: TranscriptResult,
    episode_title: str,
    anthropic_api_key: str,
) -> EpisodeSummary:
    """Generate a structured summary of the podcast episode."""
    client = anthropic.Anthropic(api_key=anthropic_api_key)

    # Build the full attributed transcript text
    if transcript.utterances:
        transcript_text = "\n".join(
            f"{u.speaker}: {u.text}" for u in transcript.utterances
        )
    else:
        transcript_text = transcript.raw_text

    prompt = f"""You are analysing a podcast episode titled "{episode_title}".

Here is the full transcript:

<transcript>
{transcript_text}
</transcript>

Please produce a structured analysis with the following sections. Return your response in EXACTLY this format with these section headers:

## Summary
Write a concise summary of the episode in 3-5 paragraphs. Cover the main discussion points and conclusions.

## Key Themes
List the key themes and topics discussed, one per line, prefixed with "- ".

## Trade Recommendations & Market Views
List any specific trade recommendations, positioning views, currency forecasts, or market calls mentioned. One per line, prefixed with "- ". If none were discussed, write "- None explicitly mentioned".

## Notable Quotes
List 3-5 notable or insightful direct quotes from the episode, one per line, prefixed with "- " and wrapped in quotation marks. Include the speaker's name.

Return ONLY the structured analysis, no other commentary."""

    logger.info("Generating episode summary with Claude")
    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    return _parse_summary(response.content[0].text)


def _parse_summary(text: str) -> EpisodeSummary:
    """Parse Claude's structured summary response into an EpisodeSummary."""
    sections = {"summary": "", "themes": [], "trade_recommendations": [], "notable_quotes": []}

    current_section = None
    current_lines: list[str] = []

    for line in text.split("\n"):
        stripped = line.strip()
        lower = stripped.lower()

        if lower.startswith("## summary"):
            _flush_section(sections, current_section, current_lines)
            current_section = "summary"
            current_lines = []
        elif lower.startswith("## key themes"):
            _flush_section(sections, current_section, current_lines)
            current_section = "themes"
            current_lines = []
        elif lower.startswith("## trade") or lower.startswith("## market"):
            _flush_section(sections, current_section, current_lines)
            current_section = "trade_recommendations"
            current_lines = []
        elif lower.startswith("## notable"):
            _flush_section(sections, current_section, current_lines)
            current_section = "notable_quotes"
            current_lines = []
        else:
            current_lines.append(line)

    _flush_section(sections, current_section, current_lines)

    return EpisodeSummary(
        summary=sections["summary"],
        themes=sections["themes"],
        trade_recommendations=sections["trade_recommendations"],
        notable_quotes=sections["notable_quotes"],
    )


def _flush_section(
    sections: dict, section_name: str | None, lines: list[str]
) -> None:
    """Flush accumulated lines into the appropriate section."""
    if section_name is None:
        return

    if section_name == "summary":
        sections["summary"] = "\n".join(lines).strip()
    else:
        items = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("- "):
                items.append(stripped[2:].strip())
            elif stripped.startswith("* "):
                items.append(stripped[2:].strip())
        sections[section_name] = items
