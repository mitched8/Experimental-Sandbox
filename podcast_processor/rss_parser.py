"""RSS feed parsing — extract episode metadata from a podcast feed."""

import logging
from dataclasses import dataclass

import feedparser

logger = logging.getLogger(__name__)


@dataclass
class EpisodeMetadata:
    title: str
    published: str
    description: str
    audio_url: str
    author: str | None = None


def parse_feed(feed_url: str) -> list[EpisodeMetadata]:
    """Parse an RSS feed and return a list of EpisodeMetadata, newest first."""
    logger.info("Parsing RSS feed: %s", feed_url)
    feed = feedparser.parse(feed_url)

    if feed.bozo:
        logger.warning("Feed parse warning: %s", feed.bozo_exception)

    if not feed.entries:
        raise ValueError(f"No episodes found in feed: {feed_url}")

    episodes: list[EpisodeMetadata] = []
    for entry in feed.entries:
        audio_url = _extract_audio_url(entry)
        if not audio_url:
            logger.warning("Skipping entry with no audio URL: %s", entry.get("title"))
            continue

        episodes.append(
            EpisodeMetadata(
                title=entry.get("title", "Untitled"),
                published=entry.get("published", ""),
                description=entry.get("summary", ""),
                audio_url=audio_url,
                author=entry.get("author"),
            )
        )

    logger.info("Found %d episodes with audio", len(episodes))
    return episodes


def get_latest_episode(feed_url: str) -> EpisodeMetadata:
    """Return the most recent episode from a feed."""
    episodes = parse_feed(feed_url)
    if not episodes:
        raise ValueError("No episodes with audio found in feed")
    return episodes[0]


def _extract_audio_url(entry: dict) -> str | None:
    """Pull the audio enclosure URL from a feed entry."""
    # Check enclosures / links for audio types
    for link in entry.get("links", []):
        href = link.get("href", "")
        link_type = link.get("type", "")
        if link_type.startswith("audio/") or href.endswith(".mp3"):
            return href

    # Fallback: check enclosures directly
    for enc in entry.get("enclosures", []):
        href = enc.get("href", "")
        enc_type = enc.get("type", "")
        if enc_type.startswith("audio/") or href.endswith(".mp3"):
            return href

    return None
