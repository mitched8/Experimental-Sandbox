"""Main pipeline orchestrator — two-pass podcast processing with stance tracking."""

import logging
import os
import sys
import tempfile
from pathlib import Path

from .audio_download import download_audio
from .audio_split import split_audio
from .config import PipelineConfig, PodcastConfig, load_config
from .correction_applier import apply_corrections as apply_validation_corrections
from .corrections import apply_corrections as apply_transcript_corrections
from .output import (
    extract_stance_yaml,
    get_transcript_filename,
    save_summary,
    save_transcript,
)
from .rss_parser import EpisodeMetadata, get_latest_episode, parse_feed
from .speaker_attribution import attribute_speakers
from .stance import apply_stance_updates, load_stance, save_stance
from .summary import generate_summary
from .transcription import TranscriptResult, transcribe, transcribe_segments
from .validation import validate_summary

logger = logging.getLogger(__name__)


def process_audio(
    audio_path: str,
    series_id: str,
    config: PipelineConfig | None = None,
    episode_title: str | None = None,
    episode_date: str | None = None,
) -> None:
    """Process a specific audio file through the full pipeline.

    Args:
        audio_path: Path to the audio file.
        series_id: Podcast series identifier (e.g. 'jpm_at_any_rate').
        config: Pipeline configuration. Loaded from config/pipeline.yaml if None.
        episode_title: Optional episode title override.
        episode_date: Optional episode date override.
    """
    if config is None:
        config = load_config()

    podcast_config = config.podcasts.get(series_id)
    if not podcast_config:
        logger.warning("No config for series '%s', using defaults", series_id)
        podcast_config = PodcastConfig()

    anthropic_key = _require_anthropic_key()

    # Build episode metadata
    episode = EpisodeMetadata(
        title=episode_title or Path(audio_path).stem,
        published=episode_date or "",
        description="",
        audio_url=str(audio_path),
        author=None,
    )

    # Step 1: Transcription
    _log_step(1, "Transcribing audio")
    audio_p = Path(audio_path)
    transcript = transcribe(audio_p)
    _log_transcript_stats(transcript)

    # Step 2: Speaker attribution
    _log_step(2, "Attributing speakers")
    transcript = attribute_speakers(
        transcript,
        episode_description=episode.description,
        anthropic_api_key=anthropic_key,
    )

    # Run the post-transcription pipeline
    _run_post_transcription(
        episode=episode,
        transcript=transcript,
        series_id=series_id,
        podcast_config=podcast_config,
        config=config,
        anthropic_key=anthropic_key,
    )


def check_feed(
    series_id: str,
    config: PipelineConfig | None = None,
) -> None:
    """Check RSS feed for new episodes and process them.

    Args:
        series_id: Podcast series identifier.
        config: Pipeline configuration.
    """
    if config is None:
        config = load_config()

    podcast_config = config.podcasts.get(series_id)
    if not podcast_config:
        logger.error("No config for series '%s'", series_id)
        sys.exit(1)

    if not podcast_config.feed_url:
        logger.error("No feed_url configured for series '%s'", series_id)
        sys.exit(1)

    anthropic_key = _require_anthropic_key()

    # Parse feed
    _log_step(1, "Parsing RSS feed")
    episode = get_latest_episode(podcast_config.feed_url)
    logger.info("Latest episode: %s", episode.title)
    logger.info("Published: %s", episode.published)

    # Download audio
    _log_step(2, "Downloading audio")
    tmp_dir = tempfile.mkdtemp(prefix="podcast_")
    audio_path = download_audio(episode.audio_url, dest_dir=tmp_dir)

    # Transcription
    _log_step(3, "Transcribing audio")
    transcript = transcribe(audio_path)
    _log_transcript_stats(transcript)

    # Speaker attribution
    _log_step(4, "Attributing speakers")
    transcript = attribute_speakers(
        transcript,
        episode_description=episode.description,
        anthropic_api_key=anthropic_key,
    )

    # Run post-transcription pipeline
    _run_post_transcription(
        episode=episode,
        transcript=transcript,
        series_id=series_id,
        podcast_config=podcast_config,
        config=config,
        anthropic_key=anthropic_key,
    )

    logger.info("Temporary audio at: %s (delete manually if no longer needed)", audio_path)


def reprocess_transcript(
    transcript_path: str,
    series_id: str,
    config: PipelineConfig | None = None,
) -> None:
    """Reprocess an existing transcript through the summary pipeline.

    Skips transcription — reads the transcript from a markdown file and runs
    pre-processing, Pass 1, Pass 2, correction application, and output.

    Args:
        transcript_path: Path to existing transcript markdown file.
        series_id: Podcast series identifier.
        config: Pipeline configuration.
    """
    if config is None:
        config = load_config()

    podcast_config = config.podcasts.get(series_id)
    if not podcast_config:
        logger.warning("No config for series '%s', using defaults", series_id)
        podcast_config = PodcastConfig()

    anthropic_key = _require_anthropic_key()

    # Parse transcript from markdown
    _log_step(1, "Reading existing transcript")
    transcript, episode = _parse_transcript_markdown(transcript_path)
    logger.info("Loaded transcript: %d utterances from %s", len(transcript.utterances), transcript_path)

    # Run post-transcription pipeline
    _run_post_transcription(
        episode=episode,
        transcript=transcript,
        series_id=series_id,
        podcast_config=podcast_config,
        config=config,
        anthropic_key=anthropic_key,
    )


def show_stance(
    series_id: str,
    config: PipelineConfig | None = None,
) -> None:
    """Display the current stance for a podcast series.

    Args:
        series_id: Podcast series identifier.
        config: Pipeline configuration.
    """
    if config is None:
        config = load_config()

    podcast_config = config.podcasts.get(series_id)
    if not podcast_config:
        logger.error("No config for series '%s'", series_id)
        sys.exit(1)

    stance_path = Path(podcast_config.stance_file) if podcast_config.stance_file else Path(config.output.stance_dir) / f"{series_id}.yaml"

    stance = load_stance(stance_path)
    if stance is None:
        print(f"No stance file found for '{series_id}' at {stance_path}")
        return

    import yaml
    print(f"Current stance for '{series_id}' (last updated: {stance.get('last_updated', 'unknown')}):")
    print("---")
    print(yaml.dump(stance, default_flow_style=False, allow_unicode=True, sort_keys=False))


def _run_post_transcription(
    episode: EpisodeMetadata,
    transcript: TranscriptResult,
    series_id: str,
    podcast_config: PodcastConfig,
    config: PipelineConfig,
    anthropic_key: str,
) -> None:
    """Run the post-transcription pipeline: corrections, Pass 1, Pass 2, output.

    This is the core of the two-pass architecture, shared by all entry points.
    """
    corrections = podcast_config.corrections

    # Pre-processing: apply correction dictionaries
    _log_step("A", "Pre-processing: applying correction dictionaries")
    transcript = apply_transcript_corrections(transcript, corrections)

    # Load stance file
    stance_path = Path(podcast_config.stance_file) if podcast_config.stance_file else Path(config.output.stance_dir) / f"{series_id}.yaml"
    stance = load_stance(stance_path)

    # Pass 1: Summary generation
    _log_step("B", "Pass 1: Generating summary (Sonnet)")
    summary_text = generate_summary(
        transcript=transcript,
        episode_title=episode.title,
        episode_date=episode.published,
        series_name=series_id,
        anthropic_api_key=anthropic_key,
        stance=stance,
        corrections=corrections,
        config=config.summarisation,
    )

    # Pass 2: Validation
    _log_step("C", "Pass 2: Validating summary (Haiku)")
    validation = validate_summary(
        summary_text=summary_text,
        transcript=transcript,
        anthropic_api_key=anthropic_key,
        config=config.summarisation,
    )
    logger.info(
        "Validation: %d issues found, %d sections clean",
        len(validation.issues),
        len(validation.validated_sections),
    )

    # Apply corrections from Pass 2
    _log_step("D", "Applying corrections from validation")
    corrections_path = Path(podcast_config.corrections_file) if podcast_config.corrections_file else None
    corrected_summary, skipped = apply_validation_corrections(
        summary_text=summary_text,
        validation=validation,
        corrections=corrections,
        corrections_path=corrections_path,
        series_id=series_id,
    )
    if skipped:
        logger.info("Skipped %d low-confidence issues (logged only)", len(skipped))

    # Output
    _log_step("E", "Saving outputs")

    # 1. Save transcript
    transcript_path = save_transcript(
        episode=episode,
        transcript=transcript,
        corrections=corrections,
        output_config=config.output,
    )

    # 2. Save summary with transcript link
    transcript_filename = get_transcript_filename(episode)
    summary_path = save_summary(
        episode=episode,
        summary_text=corrected_summary,
        transcript_filename=transcript_filename,
        output_config=config.output,
    )

    # 3. Update stance file
    stance_yaml = extract_stance_yaml(corrected_summary)
    if stance_yaml:
        updated_stance = apply_stance_updates(stance, stance_yaml, episode.title)
        save_stance(stance_path, updated_stance)
    else:
        logger.warning("No stance updates extracted — stance file unchanged")

    logger.info("=" * 60)
    logger.info("Pipeline complete!")
    logger.info("  Summary:    %s", summary_path)
    logger.info("  Transcript: %s", transcript_path)
    logger.info("  Stance:     %s", stance_path)
    logger.info("=" * 60)


def _parse_transcript_markdown(path: str) -> tuple[TranscriptResult, EpisodeMetadata]:
    """Parse a transcript markdown file back into TranscriptResult + EpisodeMetadata.

    Extracts YAML frontmatter for metadata and speaker-attributed text for the transcript.
    """
    import re

    import yaml

    from .transcription import Utterance

    text = Path(path).read_text(encoding="utf-8")

    # Extract YAML frontmatter
    fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    metadata = {}
    if fm_match:
        try:
            metadata = yaml.safe_load(fm_match.group(1)) or {}
        except yaml.YAMLError:
            pass

    episode = EpisodeMetadata(
        title=metadata.get("title", Path(path).stem),
        published=metadata.get("date", ""),
        description="",
        audio_url=metadata.get("audio_url", ""),
        author=metadata.get("author"),
    )

    # Extract the transcript section only (after "## Full Transcript")
    raw_text = ""
    transcript_section = re.search(r"## Full Transcript\s*\n(.*)", text, re.DOTALL)
    if transcript_section:
        raw_text = transcript_section.group(1).strip()

    # Extract utterances from the transcript section (not from summary/quotes above)
    # Format is **Speaker Name:** text (colon is inside the bold markers)
    utterances: list[Utterance] = []
    search_text = raw_text if raw_text else text
    for match in re.finditer(r"\*\*(.+?):\*\*\s*(.+?)(?=\n\n\*\*|\Z)", search_text, re.DOTALL):
        speaker = match.group(1).strip()
        utt_text = match.group(2).strip()
        utterances.append(Utterance(speaker=speaker, text=utt_text))

    transcript = TranscriptResult(
        utterances=utterances,
        raw_text=raw_text,
        has_diarisation=bool(utterances),
        source=metadata.get("transcription_source", "markdown"),
    )

    return transcript, episode


def _require_anthropic_key() -> str:
    """Get the Anthropic API key or exit."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        logger.error("ANTHROPIC_API_KEY is required — set it in .env or environment")
        sys.exit(1)
    return key


def _log_step(step: int | str, description: str) -> None:
    """Log a pipeline step header."""
    logger.info("=" * 60)
    logger.info("STEP %s: %s", step, description)
    logger.info("=" * 60)


def _log_transcript_stats(transcript: TranscriptResult) -> None:
    """Log basic transcript statistics."""
    logger.info(
        "Transcription complete: %d utterances, %d chars, source=%s, diarisation=%s",
        len(transcript.utterances),
        len(transcript.raw_text),
        transcript.source,
        transcript.has_diarisation,
    )
