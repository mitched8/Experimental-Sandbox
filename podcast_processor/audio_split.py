"""Split audio into fixed-duration segments for chunked transcription.

Uses ffmpeg (no pydub). Install: brew install ffmpeg
"""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Default segment length when splitting (seconds)
DEFAULT_SEGMENT_DURATION_SEC = 600  # 10 minutes


def split_audio(
    audio_path: Path,
    segment_duration_sec: int = DEFAULT_SEGMENT_DURATION_SEC,
    dest_dir: Path | str | None = None,
) -> list[Path]:
    """Split an audio file into segments of roughly equal duration using ffmpeg.

    Args:
        audio_path: Path to the source audio file (e.g. .mp3).
        segment_duration_sec: Target length of each segment in seconds.
        dest_dir: Directory to write segment files. If None, uses same dir as audio_path.

    Returns:
        List of paths to segment files (segment_000.mp3, segment_001.mp3, ...).
    """
    audio_path = Path(audio_path)
    if dest_dir is None:
        dest_dir = audio_path.parent
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    out_pattern = dest_dir / "segment_%03d.mp3"
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(audio_path),
        "-f", "segment",
        "-segment_time", str(segment_duration_sec),
        "-c", "copy",
        "-reset_timestamps", "1",
        "-map", "0:a",
        str(out_pattern),
    ]
    logger.info("Splitting audio: %s into %d s segments", audio_path.name, segment_duration_sec)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg split failed: {result.stderr or result.stdout}")

    segment_paths = sorted(dest_dir.glob("segment_*.mp3"))
    for i, p in enumerate(segment_paths):
        logger.info("Segment %d: %s", i, p.name)
    logger.info("Split into %d segments", len(segment_paths))
    return segment_paths
