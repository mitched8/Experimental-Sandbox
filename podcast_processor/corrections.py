"""Pre-processing — apply correction dictionaries to transcripts before summarisation."""

import logging
import re

from .config import PodcastCorrections
from .transcription import TranscriptResult, Utterance

logger = logging.getLogger(__name__)


def apply_corrections(
    transcript: TranscriptResult,
    corrections: PodcastCorrections,
) -> TranscriptResult:
    """Apply speaker and proper noun corrections to a transcript.

    Returns a new TranscriptResult with corrected text and speaker labels.
    """
    if not corrections.speaker_corrections and not corrections.proper_noun_corrections:
        logger.info("No corrections configured, skipping pre-processing")
        return transcript

    corrected_utterances = []
    total_fixes = 0

    for u in transcript.utterances:
        speaker = u.speaker
        text = u.text

        # Apply speaker corrections
        for wrong, right in corrections.speaker_corrections.items():
            if speaker == wrong or speaker.lower() == wrong.lower():
                logger.debug("Speaker correction: %s -> %s", speaker, right)
                speaker = right
                total_fixes += 1

        # Apply proper noun corrections (case-insensitive whole-word)
        for wrong, right in corrections.proper_noun_corrections.items():
            pattern = re.compile(r'\b' + re.escape(wrong) + r'\b', re.IGNORECASE)
            new_text = pattern.sub(right, text)
            if new_text != text:
                count = len(pattern.findall(text))
                total_fixes += count
                logger.debug("Proper noun correction: '%s' -> '%s' (%d occurrences)", wrong, right, count)
                text = new_text

        # Apply context-dependent corrections
        if corrections.context_dependent_corrections and corrections.fx_context_terms:
            text = _apply_context_corrections(
                text, corrections.context_dependent_corrections, corrections.fx_context_terms
            )

        corrected_utterances.append(Utterance(
            speaker=speaker,
            text=text,
            start_ms=u.start_ms,
            end_ms=u.end_ms,
        ))

    # Also correct raw_text
    corrected_raw = transcript.raw_text
    for wrong, right in corrections.proper_noun_corrections.items():
        pattern = re.compile(r'\b' + re.escape(wrong) + r'\b', re.IGNORECASE)
        corrected_raw = pattern.sub(right, corrected_raw)

    logger.info("Pre-processing applied %d corrections", total_fixes)

    return TranscriptResult(
        utterances=corrected_utterances,
        raw_text=corrected_raw,
        has_diarisation=transcript.has_diarisation,
        source=transcript.source,
    )


def _apply_context_corrections(
    text: str,
    context_corrections: dict[str, str],
    fx_context_terms: list[str],
) -> str:
    """Apply corrections only when the word appears near FX-related context terms.

    Uses a sliding window: if any fx_context_term appears within 50 words of the
    target word, apply the correction.
    """
    words = text.split()
    if len(words) < 2:
        return text

    # Build set of context terms (lowercased)
    context_set = {t.lower() for t in fx_context_terms}
    window_size = 50

    for wrong, right in context_corrections.items():
        pattern = re.compile(r'\b' + re.escape(wrong) + r'\b', re.IGNORECASE)
        matches = list(pattern.finditer(text))
        if not matches:
            continue

        # Check each match for nearby context
        for match in reversed(matches):  # reverse to preserve offsets
            start_pos = match.start()
            # Get surrounding text (roughly window_size words before and after)
            before_text = text[:start_pos].split()
            after_text = text[start_pos:].split()
            window_words = before_text[-window_size:] + after_text[:window_size]
            window_lower = [w.lower().strip(".,;:!?()[]") for w in window_words]

            if context_set & set(window_lower):
                text = text[:match.start()] + right + text[match.end():]
                logger.debug("Context-dependent correction: '%s' -> '%s'", wrong, right)

    return text
