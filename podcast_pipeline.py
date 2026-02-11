"""CLI entry point for the podcast summary pipeline.

Usage:
    python podcast_pipeline.py process --audio path/to/episode.mp3 --series jpm_at_any_rate
    python podcast_pipeline.py check --series jpm_at_any_rate
    python podcast_pipeline.py reprocess --transcript path/to/transcript.md --series jpm_at_any_rate
    python podcast_pipeline.py stance --series jpm_at_any_rate
"""

import argparse
import logging
import sys

from dotenv import load_dotenv

from podcast_processor.pipeline import (
    check_feed,
    process_audio,
    reprocess_transcript,
    show_stance,
)


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(
        prog="podcast_pipeline",
        description="Podcast summary pipeline with two-pass validation and stance tracking.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose/debug logging",
    )
    parser.add_argument(
        "--config",
        default="config/pipeline.yaml",
        help="Path to pipeline config YAML (default: config/pipeline.yaml)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Pipeline commands")

    # --- process: process a specific audio file ---
    process_parser = subparsers.add_parser(
        "process",
        help="Process a specific audio file through the full pipeline",
    )
    process_parser.add_argument(
        "--audio",
        required=True,
        help="Path to audio file (mp3)",
    )
    process_parser.add_argument(
        "--series",
        required=True,
        help="Podcast series identifier (e.g. jpm_at_any_rate)",
    )
    process_parser.add_argument(
        "--title",
        default=None,
        help="Episode title override",
    )
    process_parser.add_argument(
        "--date",
        default=None,
        help="Episode date override (YYYY-MM-DD)",
    )

    # --- check: check RSS feed for new episodes ---
    check_parser = subparsers.add_parser(
        "check",
        help="Check RSS feed for new episodes and process them",
    )
    check_parser.add_argument(
        "--series",
        required=True,
        help="Podcast series identifier",
    )

    # --- reprocess: reprocess an existing transcript ---
    reprocess_parser = subparsers.add_parser(
        "reprocess",
        help="Reprocess an existing transcript (skip transcription)",
    )
    reprocess_parser.add_argument(
        "--transcript",
        required=True,
        help="Path to existing transcript markdown file",
    )
    reprocess_parser.add_argument(
        "--series",
        required=True,
        help="Podcast series identifier",
    )

    # --- stance: view current stance ---
    stance_parser = subparsers.add_parser(
        "stance",
        help="View current stance for a podcast series",
    )
    stance_parser.add_argument(
        "--series",
        required=True,
        help="Podcast series identifier",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Load config
    from pathlib import Path

    from podcast_processor.config import load_config
    config = load_config(Path(args.config))

    try:
        if args.command == "process":
            process_audio(
                audio_path=args.audio,
                series_id=args.series,
                config=config,
                episode_title=args.title,
                episode_date=args.date,
            )
        elif args.command == "check":
            check_feed(
                series_id=args.series,
                config=config,
            )
        elif args.command == "reprocess":
            reprocess_transcript(
                transcript_path=args.transcript,
                series_id=args.series,
                config=config,
            )
        elif args.command == "stance":
            show_stance(
                series_id=args.series,
                config=config,
            )
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Interrupted by user")
        sys.exit(130)
    except Exception:
        logging.getLogger(__name__).exception("Pipeline failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
