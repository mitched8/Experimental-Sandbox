"""Output — write structured markdown with YAML frontmatter for Obsidian."""

import logging
import re
from datetime import datetime
from pathlib import Path

from .rss_parser import EpisodeMetadata
from .summary import EpisodeSummary
from .transcription import TranscriptResult

logger = logging.getLogger(__name__)


def save_markdown(
    episode: EpisodeMetadata,
    transcript: TranscriptResult,
    summary: EpisodeSummary,
    output_dir: str = "./output",
) -> Path:
    """Save the processed episode as a markdown file with YAML frontmatter."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    filename = _safe_filename(episode.title) + ".md"
    filepath = output_path / filename

    content = _build_markdown(episode, transcript, summary)
    filepath.write_text(content, encoding="utf-8")

    logger.info("Saved output to %s", filepath)
    return filepath


def _build_markdown(
    episode: EpisodeMetadata,
    transcript: TranscriptResult,
    summary: EpisodeSummary,
) -> str:
    """Build the full markdown document."""
    parts: list[str] = []

    # YAML frontmatter
    parts.append("---")
    parts.append(f"title: \"{_escape_yaml(episode.title)}\"")
    parts.append(f"date: \"{episode.published}\"")
    if episode.author:
        parts.append(f"author: \"{_escape_yaml(episode.author)}\"")
    parts.append(f"audio_url: \"{episode.audio_url}\"")
    parts.append(f"transcription_source: \"{transcript.source}\"")
    parts.append(f"processed: \"{datetime.now().isoformat(timespec='seconds')}\"")
    if summary.themes:
        parts.append("themes:")
        for theme in summary.themes:
            parts.append(f"  - \"{_escape_yaml(theme)}\"")
    parts.append("tags:")
    parts.append("  - podcast")
    parts.append("  - transcript")
    parts.append("---")
    parts.append("")

    # Episode description
    parts.append(f"# {episode.title}")
    parts.append("")
    parts.append(f"> **Published:** {episode.published}")
    if episode.author:
        parts.append(f"> **Author:** {episode.author}")
    parts.append("")

    # Summary
    parts.append("## Summary")
    parts.append("")
    parts.append(summary.summary)
    parts.append("")

    # Key Themes
    if summary.themes:
        parts.append("## Key Themes")
        parts.append("")
        for theme in summary.themes:
            parts.append(f"- {theme}")
        parts.append("")

    # Trade Recommendations
    if summary.trade_recommendations:
        parts.append("## Trade Recommendations & Market Views")
        parts.append("")
        for rec in summary.trade_recommendations:
            parts.append(f"- {rec}")
        parts.append("")

    # Notable Quotes
    if summary.notable_quotes:
        parts.append("## Notable Quotes")
        parts.append("")
        for quote in summary.notable_quotes:
            parts.append(f"> {quote}")
            parts.append("")

    # Full Transcript
    parts.append("## Full Transcript")
    parts.append("")
    if transcript.utterances:
        for u in transcript.utterances:
            parts.append(f"**{u.speaker}:** {u.text}")
            parts.append("")
    else:
        parts.append(transcript.raw_text)
        parts.append("")

    return "\n".join(parts)


def _safe_filename(title: str) -> str:
    """Convert a title to a safe filename."""
    # Remove or replace problematic characters
    safe = re.sub(r'[<>:"/\\|?*]', "", title)
    safe = re.sub(r"\s+", "-", safe.strip())
    safe = safe[:200]  # truncate overly long names
    return safe


def _escape_yaml(value: str) -> str:
    """Escape a string for safe inclusion in YAML."""
    return value.replace('"', '\\"')
