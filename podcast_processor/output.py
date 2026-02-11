"""Output — generate separate summary, transcript, and stance file outputs."""

import logging
import re
from datetime import date, datetime
from pathlib import Path

from .config import OutputConfig, PodcastCorrections
from .rss_parser import EpisodeMetadata
from .transcription import TranscriptResult

logger = logging.getLogger(__name__)


def save_summary(
    episode: EpisodeMetadata,
    summary_text: str,
    transcript_filename: str,
    output_config: OutputConfig | None = None,
) -> Path:
    """Save the corrected summary note as markdown.

    The summary_text is the raw markdown from Pass 1 (after Pass 2 corrections).
    Appends a link to the separate transcript file at the bottom.
    """
    if output_config is None:
        output_config = OutputConfig()

    output_dir = Path(output_config.summary_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    date_str = _extract_date(episode.published)
    filename = f"{date_str} — {_safe_source(episode)} — {_safe_title(episode.title)}.md"
    filepath = output_dir / filename

    # Append transcript link at bottom
    transcript_link = f"\n\n---\n*Full transcript: [[transcripts/{transcript_filename}]]*\n"
    content = summary_text + transcript_link

    filepath.write_text(content, encoding="utf-8")
    logger.info("Summary saved to: %s", filepath)
    return filepath


def save_transcript(
    episode: EpisodeMetadata,
    transcript: TranscriptResult,
    corrections: PodcastCorrections | None = None,
    output_config: OutputConfig | None = None,
) -> Path:
    """Save the cleaned transcript as a separate markdown file.

    Includes YAML frontmatter, speaker roster, transcription warning,
    and the full speaker-attributed text.
    """
    if output_config is None:
        output_config = OutputConfig()

    output_dir = Path(output_config.transcript_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    date_str = _extract_date(episode.published)
    filename = f"{date_str} — {_safe_source(episode)} — transcript.md"
    filepath = output_dir / filename

    content = _build_transcript_markdown(episode, transcript, corrections)
    filepath.write_text(content, encoding="utf-8")

    logger.info("Transcript saved to: %s", filepath)
    return filepath


def get_transcript_filename(episode: EpisodeMetadata) -> str:
    """Get the transcript filename for linking from the summary."""
    date_str = _extract_date(episode.published)
    return f"{date_str} — {_safe_source(episode)} — transcript.md"


def _build_transcript_markdown(
    episode: EpisodeMetadata,
    transcript: TranscriptResult,
    corrections: PodcastCorrections | None = None,
) -> str:
    """Build transcript markdown with frontmatter, roster, and text."""
    parts: list[str] = []

    # YAML frontmatter
    parts.append("---")
    parts.append(f'title: "{_escape_yaml(episode.title)} — Transcript"')
    parts.append(f'date: "{episode.published}"')
    parts.append(f'audio_url: "{episode.audio_url}"')
    parts.append(f'transcription_source: "{transcript.source}"')
    parts.append(f'processed: "{datetime.now().isoformat(timespec="seconds")}"')
    parts.append("tags:")
    parts.append("  - podcast")
    parts.append("  - transcript")
    parts.append("---")
    parts.append("")

    # Title
    parts.append(f"# {episode.title} — Transcript")
    parts.append("")

    # Speaker roster
    if corrections and corrections.speaker_roster:
        parts.append("## Speaker Roster")
        parts.append("")
        parts.append("| Speaker | Role | Coverage |")
        parts.append("|---|---|---|")
        for s in corrections.speaker_roster:
            parts.append(f"| {s.name} | {s.role} | {s.coverage} |")
        parts.append("")

    # Transcription warning
    parts.append("> **Warning:** Auto-transcribed. Speaker attribution and proper nouns may contain errors.")
    parts.append("")

    # Full transcript
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


def extract_stance_yaml(summary_text: str) -> str:
    """Extract the stance updates YAML block from the summary output.

    Looks for the ```yaml block under the ## Stance Updates section.
    """
    # Find the Stance Updates section
    stance_section_match = re.search(
        r"## Stance Updates\s*\n(.*?)(?=\n## |\Z)",
        summary_text,
        re.DOTALL,
    )
    if not stance_section_match:
        logger.warning("No Stance Updates section found in summary")
        return ""

    section_text = stance_section_match.group(1)

    # Extract YAML from code block
    yaml_match = re.search(r"```ya?ml\s*\n(.*?)```", section_text, re.DOTALL)
    if yaml_match:
        return yaml_match.group(1).strip()

    # Fallback: try to find raw YAML content (no code fence)
    # Look for lines starting with known keys
    lines = section_text.strip().split("\n")
    yaml_lines = []
    in_yaml = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(("macro_framework:", "currency_views:")) or in_yaml:
            in_yaml = True
            yaml_lines.append(line)

    if yaml_lines:
        return "\n".join(yaml_lines).strip()

    logger.warning("Could not extract YAML from Stance Updates section")
    return ""


def _extract_date(published: str) -> str:
    """Extract a YYYY-MM-DD date string from the published field."""
    # Try ISO format first
    if re.match(r"\d{4}-\d{2}-\d{2}", published):
        return published[:10]

    # Try common RSS date formats
    for fmt in [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S",
        "%d %b %Y",
    ]:
        try:
            dt = datetime.strptime(published.strip(), fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    # Fallback to today
    logger.warning("Could not parse date from '%s', using today", published)
    return date.today().isoformat()


def _safe_source(episode: EpisodeMetadata) -> str:
    """Extract a short source name from the episode author/metadata."""
    if episode.author:
        # Shorten common names
        author = episode.author
        if "J.P. Morgan" in author or "JPMorgan" in author:
            return "JPM At Any Rate"
        return _safe_filename_part(author)[:30]
    return "Unknown"


def _safe_title(title: str) -> str:
    """Create a safe, shortened title for filenames."""
    # Take first meaningful segment before common separators
    parts = re.split(r"[—–:|\-]", title, maxsplit=1)
    short = parts[0].strip() if parts else title
    return _safe_filename_part(short)[:60]


def _safe_filename_part(text: str) -> str:
    """Convert text to a safe filename component."""
    safe = re.sub(r'[<>:"/\\|?*]', "", text)
    safe = re.sub(r"\s+", " ", safe.strip())
    return safe


def _escape_yaml(value: str) -> str:
    """Escape a string for safe inclusion in YAML."""
    return value.replace('"', '\\"')
