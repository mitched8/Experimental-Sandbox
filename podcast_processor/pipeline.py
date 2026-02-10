"""Main pipeline orchestrator — single-run script for processing a podcast episode."""

import argparse
import logging
import os
import sys
import tempfile

from dotenv import load_dotenv

from .audio_download import download_audio
from .audio_split import split_audio
from .output import save_markdown, save_transcript_markdown
from .rss_parser import EpisodeMetadata, get_latest_episode
from .speaker_attribution import attribute_speakers
from .summary import generate_summary
from .transcription import transcribe, transcribe_segments

logger = logging.getLogger(__name__)

DEFAULT_FEED_URL = "https://feed.podbean.com/atanyrate/feed.xml"


def run_pipeline(
    feed_url: str,
    output_dir: str,
    split_duration_sec: int = 0,
) -> None:
    """Execute the full podcast processing pipeline.

    Args:
        feed_url: RSS feed URL.
        output_dir: Directory for output markdown.
        split_duration_sec: If > 0, split audio into segments of this many seconds
            before transcribing (reduces timeouts on long episodes). Default 0 = no split.
    """

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if not anthropic_key:
        logger.error("ANTHROPIC_API_KEY is required for speaker attribution and summary generation")
        sys.exit(1)

    # Step 1: Parse RSS feed
    logger.info("=" * 60)
    logger.info("STEP 1: Parsing RSS feed")
    logger.info("=" * 60)
    episode = get_latest_episode(feed_url)
    logger.info("Latest episode: %s", episode.title)
    logger.info("Published: %s", episode.published)

    # Step 2: Download audio
    logger.info("=" * 60)
    logger.info("STEP 2: Downloading audio")
    logger.info("=" * 60)
    tmp_dir = tempfile.mkdtemp(prefix="podcast_")
    audio_path = download_audio(episode.audio_url, dest_dir=tmp_dir)

    # Step 2b: Optionally split audio into segments
    if split_duration_sec > 0:
        logger.info("=" * 60)
        logger.info("STEP 2b: Splitting audio (%d s segments)", split_duration_sec)
        logger.info("=" * 60)
        segment_paths = split_audio(audio_path, segment_duration_sec=split_duration_sec, dest_dir=tmp_dir)
    else:
        segment_paths = [audio_path]

    # Step 3: Transcription + diarisation
    logger.info("=" * 60)
    logger.info("STEP 3: Transcribing audio")
    logger.info("=" * 60)
    if len(segment_paths) > 1:
        transcript = transcribe_segments(segment_paths, segment_duration_sec=split_duration_sec)
    else:
        transcript = transcribe(audio_path)
    logger.info(
        "Transcription complete: %d utterances, %d chars, source=%s, diarisation=%s",
        len(transcript.utterances),
        len(transcript.raw_text),
        transcript.source,
        transcript.has_diarisation,
    )

    # Save transcript to markdown immediately (so we keep it if later steps fail)
    transcript_path = save_transcript_markdown(episode, transcript, output_dir=output_dir)
    logger.info("Transcript saved to: %s", transcript_path)

    # Step 4: Speaker attribution
    logger.info("=" * 60)
    logger.info("STEP 4: Attributing speakers")
    logger.info("=" * 60)
    transcript = attribute_speakers(
        transcript,
        episode_description=episode.description,
        anthropic_api_key=anthropic_key,
    )
    speakers = sorted({u.speaker for u in transcript.utterances})
    logger.info("Identified speakers: %s", ", ".join(speakers))

    # Step 5: Summary generation
    logger.info("=" * 60)
    logger.info("STEP 5: Generating summary")
    logger.info("=" * 60)
    summary = generate_summary(
        transcript,
        episode_title=episode.title,
        anthropic_api_key=anthropic_key,
    )
    logger.info("Summary generated: %d themes, %d quotes", len(summary.themes), len(summary.notable_quotes))

    # Step 6: Output
    logger.info("=" * 60)
    logger.info("STEP 6: Saving output")
    logger.info("=" * 60)
    filepath = save_markdown(episode, transcript, summary, output_dir=output_dir)
    logger.info("Pipeline complete! Output saved to: %s", filepath)

    # Cleanup hint
    logger.info("Temporary audio file at: %s (delete manually if no longer needed)", audio_path)


def main() -> None:
    """CLI entry point."""
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Process a podcast episode into a structured transcript and summary.",
    )
    parser.add_argument(
        "--feed-url",
        default=DEFAULT_FEED_URL,
        help=f"RSS feed URL (default: {DEFAULT_FEED_URL})",
    )
    parser.add_argument(
        "--output-dir",
        default=os.environ.get("OUTPUT_DIR", "data/podcast_transcripts"),
        help="Output directory for transcript/summary markdown (default: data/podcast_transcripts or $OUTPUT_DIR)",
    )
    parser.add_argument(
        "--split-duration",
        type=int,
        default=0,
        metavar="SECONDS",
        help="Split audio into segments of this many seconds before transcribing (e.g. 600 = 10 min). 0 = no split.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose/debug logging",
    )
    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        run_pipeline(
            feed_url=args.feed_url,
            output_dir=args.output_dir,
            split_duration_sec=args.split_duration,
        )
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(130)
    except Exception:
        logger.exception("Pipeline failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
