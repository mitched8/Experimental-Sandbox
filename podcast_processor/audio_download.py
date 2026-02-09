"""Download podcast audio files to a temporary directory."""

import logging
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

CHUNK_SIZE = 8192
TIMEOUT = 60


def download_audio(audio_url: str, dest_dir: str | None = None) -> Path:
    """Download an MP3 from *audio_url* and return the local file path.

    If *dest_dir* is None a temporary directory is created automatically.
    """
    if dest_dir is None:
        dest_dir = tempfile.mkdtemp(prefix="podcast_")

    dest_path = Path(dest_dir)
    dest_path.mkdir(parents=True, exist_ok=True)

    filename = _filename_from_url(audio_url)
    filepath = dest_path / filename

    logger.info("Downloading audio: %s -> %s", audio_url, filepath)

    response = requests.get(audio_url, stream=True, timeout=TIMEOUT)
    response.raise_for_status()

    total = int(response.headers.get("content-length", 0))
    downloaded = 0

    with open(filepath, "wb") as f:
        for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
            f.write(chunk)
            downloaded += len(chunk)
            if total:
                pct = downloaded / total * 100
                if downloaded % (CHUNK_SIZE * 128) == 0:
                    logger.info("Download progress: %.1f%%", pct)

    logger.info("Download complete: %s (%.1f MB)", filepath, filepath.stat().st_size / 1e6)
    return filepath


def _filename_from_url(url: str) -> str:
    """Extract a reasonable filename from a URL."""
    parsed = urlparse(url)
    name = Path(parsed.path).name
    if not name or not name.endswith(".mp3"):
        name = "episode.mp3"
    return name
