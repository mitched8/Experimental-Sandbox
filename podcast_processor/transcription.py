"""Transcription + diarisation using AssemblyAI (preferred) or OpenAI Whisper (fallback)."""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Utterance:
    """A single utterance from the transcript."""
    speaker: str          # speaker label (e.g. "Speaker A" or a mapped name)
    text: str
    start_ms: int = 0
    end_ms: int = 0


@dataclass
class TranscriptResult:
    """Container for transcription output."""
    utterances: list[Utterance] = field(default_factory=list)
    raw_text: str = ""
    has_diarisation: bool = False
    source: str = ""      # "assemblyai" or "whisper"


def transcribe(audio_path: Path) -> TranscriptResult:
    """Transcribe the audio file, using AssemblyAI if available, else Whisper."""
    assemblyai_key = os.environ.get("ASSEMBLYAI_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")

    if assemblyai_key:
        logger.info("Using AssemblyAI for transcription + diarisation")
        return _transcribe_assemblyai(audio_path, assemblyai_key)

    if openai_key:
        logger.info("Using OpenAI Whisper for transcription (no diarisation)")
        return _transcribe_whisper(audio_path, openai_key)

    raise RuntimeError(
        "No transcription API key found. "
        "Set ASSEMBLYAI_API_KEY or OPENAI_API_KEY in your .env file."
    )


def _transcribe_assemblyai(audio_path: Path, api_key: str) -> TranscriptResult:
    """Transcribe with AssemblyAI including speaker diarisation."""
    import assemblyai as aai

    aai.settings.api_key = api_key

    config = aai.TranscriptionConfig(speaker_labels=True)
    transcriber = aai.Transcriber()

    logger.info("Submitting audio to AssemblyAI: %s", audio_path)
    transcript = transcriber.transcribe(str(audio_path), config=config)

    if transcript.status == aai.TranscriptStatus.error:
        raise RuntimeError(f"AssemblyAI transcription failed: {transcript.error}")

    utterances: list[Utterance] = []
    if transcript.utterances:
        for u in transcript.utterances:
            utterances.append(
                Utterance(
                    speaker=f"Speaker {u.speaker}",
                    text=u.text,
                    start_ms=u.start,
                    end_ms=u.end,
                )
            )

    return TranscriptResult(
        utterances=utterances,
        raw_text=transcript.text or "",
        has_diarisation=True,
        source="assemblyai",
    )


def _transcribe_whisper(audio_path: Path, api_key: str) -> TranscriptResult:
    """Transcribe with OpenAI Whisper (no diarisation)."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key)

    logger.info("Submitting audio to OpenAI Whisper: %s", audio_path)
    with open(audio_path, "rb") as f:
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="verbose_json",
        )

    raw_text = response.text if hasattr(response, "text") else str(response)

    return TranscriptResult(
        utterances=[],
        raw_text=raw_text,
        has_diarisation=False,
        source="whisper",
    )
