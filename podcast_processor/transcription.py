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


def transcribe_segments(
    segment_paths: list[Path],
    segment_duration_sec: int,
) -> TranscriptResult:
    """Transcribe multiple audio segments and merge into one TranscriptResult.

    Each segment is sent to AssemblyAI separately (avoids long single-file timeouts).
    Utterance timestamps are offset by segment index so the full transcript is continuous.
    """
    assemblyai_key = os.environ.get("ASSEMBLYAI_API_KEY")
    if not assemblyai_key:
        raise RuntimeError("ASSEMBLYAI_API_KEY required for segment transcription")

    combined_utterances: list[Utterance] = []
    combined_raw: list[str] = []
    offset_ms = 0

    for i, seg_path in enumerate(segment_paths):
        logger.info("Transcribing segment %d/%d: %s", i + 1, len(segment_paths), seg_path.name)
        result = _transcribe_assemblyai(seg_path, assemblyai_key)
        for u in result.utterances:
            combined_utterances.append(
                Utterance(
                    speaker=u.speaker,
                    text=u.text,
                    start_ms=u.start_ms + offset_ms,
                    end_ms=u.end_ms + offset_ms,
                )
            )
        if result.raw_text:
            combined_raw.append(result.raw_text)
        offset_ms += segment_duration_sec * 1000

    return TranscriptResult(
        utterances=combined_utterances,
        raw_text=" ".join(combined_raw),
        has_diarisation=True,
        source="assemblyai",
    )


def _transcribe_assemblyai(audio_path: Path, api_key: str) -> TranscriptResult:
    """Transcribe with AssemblyAI including speaker diarisation."""
    import assemblyai as aai

    aai.settings.api_key = api_key

    # API requires speech_models: non-empty list of "universal-2" or "universal-3-pro"
    config = aai.TranscriptionConfig(
        speaker_labels=True,
        speech_models=["universal-2"],
    )
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
