"""Speaker attribution — map generic speaker labels to real names using Claude."""

import logging
import re

import anthropic

from .transcription import TranscriptResult, Utterance

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"


def attribute_speakers(
    transcript: TranscriptResult,
    episode_description: str,
    anthropic_api_key: str,
) -> TranscriptResult:
    """Attribute speakers in the transcript using Claude.

    If the transcript already has diarisation (AssemblyAI), ask Claude to map
    the speaker labels to names based on episode description context.

    If no diarisation (Whisper), ask Claude to attribute the full text to
    speakers extracted from the description.
    """
    client = anthropic.Anthropic(api_key=anthropic_api_key)

    if transcript.has_diarisation:
        return _map_speaker_labels(client, transcript, episode_description)
    else:
        return _attribute_from_text(client, transcript, episode_description)


def _map_speaker_labels(
    client: anthropic.Anthropic,
    transcript: TranscriptResult,
    episode_description: str,
) -> TranscriptResult:
    """Map generic speaker labels (Speaker A, Speaker B) to real names."""
    # Build a sample of the transcript for context
    sample_lines = []
    for u in transcript.utterances[:40]:
        sample_lines.append(f"{u.speaker}: {u.text}")
    sample_text = "\n".join(sample_lines)

    # Get unique speaker labels
    labels = sorted({u.speaker for u in transcript.utterances})

    prompt = f"""You are analysing a podcast transcript. The episode description is:

<episode_description>
{episode_description}
</episode_description>

The transcript has these speaker labels: {', '.join(labels)}

Here is the beginning of the transcript:

<transcript_sample>
{sample_text}
</transcript_sample>

Based on the episode description and the content/style of what each speaker says, identify who each speaker label corresponds to. Consider:
- The episode description usually names the hosts and guests
- Hosts typically ask questions and guide the conversation
- Guests typically provide expertise and detailed answers

Return ONLY a JSON object mapping each speaker label to the real name, e.g.:
{{"Speaker A": "John Smith", "Speaker B": "Jane Doe"}}

If you cannot determine a speaker's name, keep the original label."""

    logger.info("Asking Claude to map speaker labels to names")
    response = client.messages.create(
        model=MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    mapping = _parse_speaker_mapping(response.content[0].text, labels)
    logger.info("Speaker mapping: %s", mapping)

    # Apply mapping
    for utterance in transcript.utterances:
        utterance.speaker = mapping.get(utterance.speaker, utterance.speaker)

    return transcript


def _attribute_from_text(
    client: anthropic.Anthropic,
    transcript: TranscriptResult,
    episode_description: str,
) -> TranscriptResult:
    """Attribute speakers from plain text (Whisper, no diarisation)."""
    prompt = f"""You are analysing a podcast transcript. The episode description is:

<episode_description>
{episode_description}
</episode_description>

Here is the full transcript (without speaker labels):

<transcript>
{transcript.raw_text}
</transcript>

Please attribute this dialogue to the speakers mentioned in the episode description.
Return the transcript as a series of lines, each formatted as:
SPEAKER_NAME: dialogue text

Use the actual names from the episode description. If there's a host, they typically ask questions.
Keep the dialogue text faithful to the original — do not summarise or alter it.
Return ONLY the attributed transcript, no other commentary."""

    logger.info("Asking Claude to attribute speakers from plain text")
    response = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        messages=[{"role": "user", "content": prompt}],
    )

    attributed_text = response.content[0].text
    utterances = _parse_attributed_text(attributed_text)

    transcript.utterances = utterances
    transcript.has_diarisation = True
    return transcript


def _parse_speaker_mapping(text: str, labels: list[str]) -> dict[str, str]:
    """Parse a JSON speaker mapping from Claude's response."""
    import json

    # Try to extract JSON from the response
    # Claude sometimes wraps it in markdown code blocks
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"```(?:json)?\s*", "", text)
        text = text.rstrip("`").strip()

    try:
        mapping = json.loads(text)
        if isinstance(mapping, dict):
            return mapping
    except json.JSONDecodeError:
        logger.warning("Failed to parse speaker mapping JSON, using original labels")

    return {label: label for label in labels}


def _parse_attributed_text(text: str) -> list[Utterance]:
    """Parse 'SPEAKER: text' formatted lines into Utterance objects."""
    utterances: list[Utterance] = []
    current_speaker = None
    current_text_parts: list[str] = []

    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        # Match "Name: dialogue" pattern
        match = re.match(r"^([A-Za-z\s.'-]+?):\s+(.+)$", line)
        if match:
            # Save previous utterance
            if current_speaker and current_text_parts:
                utterances.append(
                    Utterance(speaker=current_speaker, text=" ".join(current_text_parts))
                )
            current_speaker = match.group(1).strip()
            current_text_parts = [match.group(2).strip()]
        elif current_speaker:
            # Continuation of previous speaker's line
            current_text_parts.append(line)

    # Don't forget the last utterance
    if current_speaker and current_text_parts:
        utterances.append(
            Utterance(speaker=current_speaker, text=" ".join(current_text_parts))
        )

    return utterances
