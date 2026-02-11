"""Pass 2: Validation — fact-check the summary against the transcript using Claude Haiku."""

import logging
from dataclasses import dataclass

import anthropic

from .config import SummarisationConfig
from .transcription import TranscriptResult

logger = logging.getLogger(__name__)


@dataclass
class ValidationIssue:
    section: str
    category: str  # INCORRECT, MISATTRIBUTED, IMPRECISE, HALLUCINATED, MISSING, GARBLED SOURCE
    in_summary: str
    in_transcript: str
    correction: str
    confidence: str  # HIGH, MEDIUM, LOW


@dataclass
class ValidationResult:
    issues: list[ValidationIssue]
    validated_sections: list[str]
    raw_output: str


def validate_summary(
    summary_text: str,
    transcript: TranscriptResult,
    anthropic_api_key: str,
    config: SummarisationConfig | None = None,
) -> ValidationResult:
    """Run Pass 2 validation: check summary against transcript for errors.

    Returns a ValidationResult with parsed issues and validated sections.
    """
    if config is None:
        config = SummarisationConfig()

    client = anthropic.Anthropic(api_key=anthropic_api_key)

    # Build transcript text
    if transcript.utterances:
        transcript_text = "\n".join(
            f"{u.speaker}: {u.text}" for u in transcript.utterances
        )
    else:
        transcript_text = transcript.raw_text

    system_prompt = """You are an editorial fact-checker for a financial markets research desk.
Your job is to verify a podcast summary against the original transcript.
Be precise and specific. Flag real issues, not stylistic preferences.

For each section of the summary, check against the transcript and flag issues using EXACTLY these categories:

| Category        | Description                                            |
|-----------------|--------------------------------------------------------|
| INCORRECT       | Contradicts or is unsupported by transcript            |
| MISATTRIBUTED   | View attributed to wrong speaker                       |
| IMPRECISE       | Directionally right but missing caveats/conditionality |
| HALLUCINATED    | Information not in transcript at all                   |
| MISSING         | Material point in transcript not captured in summary   |
| GARBLED SOURCE  | Summary influenced by a transcription error            |

For each issue found, output in EXACTLY this format:

SECTION: [section name]
ISSUE: [category]
IN SUMMARY: "[quote from summary]"
IN TRANSCRIPT: "[relevant quote from transcript]"
CORRECTION: "[suggested fix]"
CONFIDENCE: [HIGH/MEDIUM/LOW]

For sections that pass validation with no issues, output:
SECTION: [section name]
STATUS: VALIDATED

Check these sections: What's Changed, Trade Recommendations, Summary, Notable Quotes, Desk Relevance, Stance Updates.

Be thorough but avoid false positives. Only flag genuine errors, not minor wording differences."""

    user_prompt = f"""Validate this podcast summary against the original transcript.

<summary>
{summary_text}
</summary>

<transcript>
{transcript_text}
</transcript>

Check each section for accuracy against the transcript. Output your findings using the specified format."""

    logger.info("Pass 2: Validating summary with %s", config.pass2_model)
    response = client.messages.create(
        model=config.pass2_model,
        max_tokens=config.max_tokens_pass2,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw_output = response.content[0].text
    logger.info("Pass 2 complete: %d characters", len(raw_output))

    return _parse_validation_output(raw_output)


def _parse_validation_output(text: str) -> ValidationResult:
    """Parse the structured validation output into a ValidationResult."""
    issues: list[ValidationIssue] = []
    validated_sections: list[str] = []

    # Split on "SECTION:" to get individual blocks
    # Normalize by ensuring each SECTION: starts on its own line
    blocks = _split_into_blocks(text)

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        lines = block.split("\n")
        section_name = lines[0].strip()

        # Check if this is a validated section
        block_text = "\n".join(lines[1:])
        if "STATUS:" in block_text and "VALIDATED" in block_text:
            validated_sections.append(section_name)
            continue

        # Parse issue fields
        issue_data: dict[str, str] = {"section": section_name}
        for line in lines[1:]:
            line = line.strip()
            if line.startswith("ISSUE:"):
                issue_data["category"] = line.removeprefix("ISSUE:").strip()
            elif line.startswith("IN SUMMARY:"):
                issue_data["in_summary"] = line.removeprefix("IN SUMMARY:").strip().strip('"')
            elif line.startswith("IN TRANSCRIPT:"):
                issue_data["in_transcript"] = line.removeprefix("IN TRANSCRIPT:").strip().strip('"')
            elif line.startswith("CORRECTION:"):
                issue_data["correction"] = line.removeprefix("CORRECTION:").strip().strip('"')
            elif line.startswith("CONFIDENCE:"):
                issue_data["confidence"] = line.removeprefix("CONFIDENCE:").strip()

        if "category" in issue_data:
            issues.append(ValidationIssue(
                section=issue_data.get("section", ""),
                category=issue_data.get("category", ""),
                in_summary=issue_data.get("in_summary", ""),
                in_transcript=issue_data.get("in_transcript", ""),
                correction=issue_data.get("correction", ""),
                confidence=issue_data.get("confidence", "LOW"),
            ))

    logger.info(
        "Validation parsed: %d issues found, %d sections validated clean",
        len(issues),
        len(validated_sections),
    )

    return ValidationResult(
        issues=issues,
        validated_sections=validated_sections,
        raw_output=text,
    )


def _split_into_blocks(text: str) -> list[str]:
    """Split validation output into blocks by SECTION: markers."""
    result: list[str] = []
    current_lines: list[str] = []

    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("SECTION:"):
            if current_lines:
                result.append("\n".join(current_lines))
            section_name = stripped.removeprefix("SECTION:").strip()
            current_lines = [section_name]
        else:
            current_lines.append(line)

    if current_lines:
        result.append("\n".join(current_lines))

    return result
