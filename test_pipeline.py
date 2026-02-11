"""End-to-end test: reprocess the existing transcript through the rebuilt pipeline."""

import logging
import os
import sys
import types

# Mock feedparser since it won't install in this environment
sys.modules["feedparser"] = types.ModuleType("feedparser")

from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("test_pipeline")

from podcast_processor.config import load_config
from podcast_processor.corrections import apply_corrections as apply_transcript_corrections
from podcast_processor.correction_applier import apply_corrections as apply_validation_corrections
from podcast_processor.output import (
    extract_stance_yaml,
    get_transcript_filename,
    save_summary,
    save_transcript,
)
from podcast_processor.pipeline import _parse_transcript_markdown
from podcast_processor.stance import apply_stance_updates, load_stance, save_stance
from podcast_processor.summary import generate_summary
from podcast_processor.validation import validate_summary


def main():
    transcript_path = "data/podcast_transcripts/Global-FX-RBA,-JP-elections,-euroAPAC-rotation,-dovish-BoE,-US-data.md"
    series_id = "jpm_at_any_rate"

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if not anthropic_key:
        logger.error("ANTHROPIC_API_KEY not set")
        sys.exit(1)

    config = load_config(Path("config/pipeline.yaml"))
    podcast_config = config.podcasts[series_id]
    corrections = podcast_config.corrections

    # Step 1: Parse existing transcript
    logger.info("=" * 60)
    logger.info("STEP 1: Parsing existing transcript")
    logger.info("=" * 60)
    transcript, episode = _parse_transcript_markdown(transcript_path)
    logger.info("Loaded: %d utterances, title='%s'", len(transcript.utterances), episode.title)

    # Step 2: Apply correction dictionaries
    logger.info("=" * 60)
    logger.info("STEP 2: Pre-processing — applying correction dictionaries")
    logger.info("=" * 60)
    transcript = apply_transcript_corrections(transcript, corrections)

    # Show a sample of corrected text
    logger.info("Sample corrected utterances:")
    for u in transcript.utterances[:3]:
        logger.info("  %s: %s", u.speaker, u.text[:120] + "...")

    # Step 3: Load stance (none should exist yet)
    logger.info("=" * 60)
    logger.info("STEP 3: Loading stance file")
    logger.info("=" * 60)
    stance_path = Path(podcast_config.stance_file)
    stance = load_stance(stance_path)

    # Step 4: Pass 1 — Summary generation (Sonnet)
    logger.info("=" * 60)
    logger.info("STEP 4: Pass 1 — Summary generation (Sonnet)")
    logger.info("=" * 60)
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
    logger.info("Pass 1 output: %d characters", len(summary_text))

    # Step 5: Pass 2 — Validation (Haiku)
    logger.info("=" * 60)
    logger.info("STEP 5: Pass 2 — Validation (Haiku)")
    logger.info("=" * 60)
    validation = validate_summary(
        summary_text=summary_text,
        transcript=transcript,
        anthropic_api_key=anthropic_key,
        config=config.summarisation,
    )
    logger.info("Validation: %d issues, %d sections clean", len(validation.issues), len(validation.validated_sections))
    for issue in validation.issues:
        logger.info("  [%s] %s: %s — %s", issue.confidence, issue.section, issue.category, issue.in_summary[:80] if issue.in_summary else "(empty)")

    # Step 6: Apply corrections from Pass 2
    logger.info("=" * 60)
    logger.info("STEP 6: Applying corrections from validation")
    logger.info("=" * 60)
    corrections_path = Path(podcast_config.corrections_file)
    corrected_summary, skipped = apply_validation_corrections(
        summary_text=summary_text,
        validation=validation,
        corrections=corrections,
        corrections_path=corrections_path,
        series_id=series_id,
    )

    # Step 7: Save outputs
    logger.info("=" * 60)
    logger.info("STEP 7: Saving outputs")
    logger.info("=" * 60)

    # Save transcript
    transcript_out = save_transcript(
        episode=episode,
        transcript=transcript,
        corrections=corrections,
        output_config=config.output,
    )

    # Save summary
    transcript_filename = get_transcript_filename(episode)
    summary_out = save_summary(
        episode=episode,
        summary_text=corrected_summary,
        transcript_filename=transcript_filename,
        output_config=config.output,
    )

    # Update stance file
    stance_yaml = extract_stance_yaml(corrected_summary)
    if stance_yaml:
        updated_stance = apply_stance_updates(stance, stance_yaml, episode.title)
        save_stance(stance_path, updated_stance)
        logger.info("Stance file saved: %s", stance_path)
    else:
        logger.warning("No stance updates extracted")

    logger.info("=" * 60)
    logger.info("PIPELINE COMPLETE!")
    logger.info("  Summary:    %s", summary_out)
    logger.info("  Transcript: %s", transcript_out)
    logger.info("  Stance:     %s", stance_path)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
