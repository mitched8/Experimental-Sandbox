"""Configuration loader — read pipeline.yaml and podcast correction files."""

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path("config/pipeline.yaml")


@dataclass
class TranscriptionConfig:
    provider: str = "assemblyai"
    whisper_model: str = "whisper-1"
    assemblyai_speaker_diarization: bool = True


@dataclass
class SummarisationConfig:
    pass1_model: str = "claude-sonnet-4-20250514"
    pass2_model: str = "claude-haiku-4-5-20251001"
    max_tokens_pass1: int = 4096
    max_tokens_pass2: int = 2048


@dataclass
class OutputConfig:
    summary_dir: str = "results/"
    transcript_dir: str = "results/transcripts/"
    stance_dir: str = "data/stances/"


@dataclass
class SpeakerInfo:
    name: str
    role: str = ""
    coverage: str = ""


@dataclass
class PodcastCorrections:
    speaker_corrections: dict[str, str] = field(default_factory=dict)
    proper_noun_corrections: dict[str, str] = field(default_factory=dict)
    context_dependent_corrections: dict[str, str] = field(default_factory=dict)
    fx_context_terms: list[str] = field(default_factory=list)
    speaker_roster: list[SpeakerInfo] = field(default_factory=list)


@dataclass
class PodcastConfig:
    feed_url: str = ""
    corrections_file: str = ""
    stance_file: str = ""
    keywords_filter: list[str] = field(default_factory=list)
    corrections: PodcastCorrections = field(default_factory=PodcastCorrections)


@dataclass
class PipelineConfig:
    transcription: TranscriptionConfig = field(default_factory=TranscriptionConfig)
    summarisation: SummarisationConfig = field(default_factory=SummarisationConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    podcasts: dict[str, PodcastConfig] = field(default_factory=dict)


def load_config(config_path: Path = DEFAULT_CONFIG_PATH) -> PipelineConfig:
    """Load pipeline configuration from YAML."""
    if not config_path.exists():
        logger.warning("Config file not found at %s, using defaults", config_path)
        return PipelineConfig()

    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    config = PipelineConfig()

    # Transcription
    if "transcription" in raw:
        t = raw["transcription"]
        config.transcription = TranscriptionConfig(
            provider=t.get("provider", "assemblyai"),
            whisper_model=t.get("whisper_model", "whisper-1"),
            assemblyai_speaker_diarization=t.get("assemblyai_speaker_diarization", True),
        )

    # Summarisation
    if "summarisation" in raw:
        s = raw["summarisation"]
        config.summarisation = SummarisationConfig(
            pass1_model=s.get("pass1_model", "claude-sonnet-4-20250514"),
            pass2_model=s.get("pass2_model", "claude-haiku-4-5-20251001"),
            max_tokens_pass1=s.get("max_tokens_pass1", 4096),
            max_tokens_pass2=s.get("max_tokens_pass2", 2048),
        )

    # Output
    if "output" in raw:
        o = raw["output"]
        config.output = OutputConfig(
            summary_dir=o.get("summary_dir", "results/"),
            transcript_dir=o.get("transcript_dir", "results/transcripts/"),
            stance_dir=o.get("stance_dir", "data/stances/"),
        )

    # Podcasts
    if "podcasts" in raw:
        for series_id, p in raw["podcasts"].items():
            pc = PodcastConfig(
                feed_url=p.get("feed_url", ""),
                corrections_file=p.get("corrections_file", ""),
                stance_file=p.get("stance_file", ""),
                keywords_filter=p.get("keywords_filter", []),
            )
            # Load corrections if file specified
            if pc.corrections_file:
                pc.corrections = load_corrections(
                    Path(pc.corrections_file), series_id
                )
            config.podcasts[series_id] = pc

    return config


def load_corrections(corrections_path: Path, series_id: str) -> PodcastCorrections:
    """Load correction dictionary for a specific podcast series."""
    if not corrections_path.exists():
        logger.warning("Corrections file not found: %s", corrections_path)
        return PodcastCorrections()

    with open(corrections_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    series_data = raw.get(series_id, {})
    if not series_data:
        logger.warning("No corrections found for series '%s' in %s", series_id, corrections_path)
        return PodcastCorrections()

    roster = []
    for s in series_data.get("speaker_roster", []):
        roster.append(SpeakerInfo(
            name=s.get("name", ""),
            role=s.get("role", ""),
            coverage=s.get("coverage", ""),
        ))

    return PodcastCorrections(
        speaker_corrections=series_data.get("speaker_corrections", {}),
        proper_noun_corrections=series_data.get("proper_noun_corrections", {}),
        context_dependent_corrections=series_data.get("context_dependent_corrections", {}),
        fx_context_terms=series_data.get("fx_context_terms", []),
        speaker_roster=roster,
    )


def save_corrections(corrections_path: Path, series_id: str, corrections: PodcastCorrections) -> None:
    """Save updated correction dictionary back to YAML."""
    if corrections_path.exists():
        with open(corrections_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    else:
        raw = {}

    roster_data = []
    for s in corrections.speaker_roster:
        roster_data.append({
            "name": s.name,
            "role": s.role,
            "coverage": s.coverage,
        })

    raw[series_id] = {
        "speaker_corrections": corrections.speaker_corrections,
        "proper_noun_corrections": corrections.proper_noun_corrections,
        "context_dependent_corrections": corrections.context_dependent_corrections,
        "fx_context_terms": corrections.fx_context_terms,
        "speaker_roster": roster_data,
    }

    corrections_path.parent.mkdir(parents=True, exist_ok=True)
    with open(corrections_path, "w", encoding="utf-8") as f:
        yaml.dump(raw, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    logger.info("Updated corrections file: %s", corrections_path)
