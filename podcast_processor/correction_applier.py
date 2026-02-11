"""Correction application — apply validated corrections from Pass 2 to the summary."""

import logging
from pathlib import Path

from .config import PodcastCorrections, save_corrections
from .validation import ValidationIssue, ValidationResult

logger = logging.getLogger(__name__)

# Categories that should be auto-applied at HIGH/MEDIUM confidence
AUTO_APPLY_CATEGORIES = {"INCORRECT", "HALLUCINATED", "MISATTRIBUTED", "IMPRECISE", "GARBLED SOURCE", "MISSING"}


def apply_corrections(
    summary_text: str,
    validation: ValidationResult,
    corrections: PodcastCorrections | None = None,
    corrections_path: Path | None = None,
    series_id: str | None = None,
) -> tuple[str, list[ValidationIssue]]:
    """Apply validated corrections to the summary text.

    For HIGH and MEDIUM confidence issues:
    - INCORRECT/HALLUCINATED: Replace the flagged text with the correction
    - MISATTRIBUTED: Fix speaker attribution
    - IMPRECISE: Add caveats/hedging language
    - GARBLED SOURCE: Fix text AND add to correction dictionary
    - MISSING: Append to relevant section

    For LOW confidence issues: log but don't auto-apply.

    Returns:
        Tuple of (corrected_summary, list of issues that were NOT applied).
    """
    corrected = summary_text
    skipped: list[ValidationIssue] = []
    applied_count = 0
    garbled_additions: list[tuple[str, str]] = []

    for issue in validation.issues:
        if issue.confidence == "LOW":
            logger.info(
                "Skipping LOW confidence issue in %s: %s — %s",
                issue.section, issue.category, issue.in_summary[:80] if issue.in_summary else "(empty)",
            )
            skipped.append(issue)
            continue

        if issue.category not in AUTO_APPLY_CATEGORIES:
            logger.warning("Unknown issue category: %s", issue.category)
            skipped.append(issue)
            continue

        if issue.category in ("INCORRECT", "HALLUCINATED", "MISATTRIBUTED", "IMPRECISE"):
            corrected = _apply_text_replacement(corrected, issue)
            applied_count += 1

        elif issue.category == "GARBLED SOURCE":
            corrected = _apply_text_replacement(corrected, issue)
            applied_count += 1
            # Collect garbled source pairs for dictionary update
            if issue.in_summary and issue.correction:
                garbled_additions.append((issue.in_summary, issue.correction))

        elif issue.category == "MISSING":
            corrected = _apply_missing_content(corrected, issue)
            applied_count += 1

    # Update correction dictionary with GARBLED SOURCE findings
    if garbled_additions and corrections and corrections_path and series_id:
        _update_correction_dictionary(
            garbled_additions, corrections, corrections_path, series_id
        )

    logger.info(
        "Applied %d corrections, skipped %d (LOW confidence or unknown category)",
        applied_count, len(skipped),
    )

    return corrected, skipped


def _apply_text_replacement(text: str, issue: ValidationIssue) -> str:
    """Replace flagged text with the correction."""
    if not issue.in_summary or not issue.correction:
        logger.warning("Cannot apply correction — missing in_summary or correction text")
        return text

    # Guard: if the correction is much longer than the original and the target
    # is inside a markdown table row, skip to avoid breaking table formatting.
    target_in_table = _is_in_table_row(text, issue.in_summary)
    correction = issue.correction
    if target_in_table and len(correction) > len(issue.in_summary) * 3:
        logger.info(
            "Skipping verbose correction in table row (%s): would break formatting",
            issue.section,
        )
        return text

    # Try exact replacement first
    if issue.in_summary in text:
        text = text.replace(issue.in_summary, correction, 1)
        logger.debug("Applied %s correction in %s", issue.category, issue.section)
    else:
        # Try case-insensitive search
        lower_text = text.lower()
        lower_target = issue.in_summary.lower()
        idx = lower_text.find(lower_target)
        if idx != -1:
            text = text[:idx] + correction + text[idx + len(issue.in_summary):]
            logger.debug("Applied %s correction (case-insensitive) in %s", issue.category, issue.section)
        else:
            logger.warning(
                "Could not find text to replace in %s: '%s'",
                issue.section, issue.in_summary[:60],
            )

    return text


def _is_in_table_row(text: str, target: str) -> bool:
    """Check if the target text appears inside a markdown table row."""
    lower_target = target.lower()
    for line in text.split("\n"):
        if "|" in line and lower_target in line.lower():
            return True
    return False


def _apply_missing_content(text: str, issue: ValidationIssue) -> str:
    """Append missing content to the relevant section."""
    if not issue.correction:
        return text

    # Find the section header
    target_header = f"## {issue.section}"
    lines = text.split("\n")
    section_start = -1

    for i, line in enumerate(lines):
        if line.strip().lower() == target_header.lower() or line.strip().lower().startswith(target_header.lower()):
            section_start = i
            break

    if section_start == -1:
        logger.warning("Could not find section '%s' to append missing content", issue.section)
        return text

    # Find the next section header after this one
    insert_at = len(lines)
    for i in range(section_start + 1, len(lines)):
        if lines[i].strip().startswith("## "):
            insert_at = i
            break

    # Insert the missing content before the next section
    lines.insert(insert_at, f"\n{issue.correction}")
    logger.debug("Appended MISSING content to section: %s", issue.section)

    return "\n".join(lines)


def _update_correction_dictionary(
    garbled_pairs: list[tuple[str, str]],
    corrections: PodcastCorrections,
    corrections_path: Path,
    series_id: str,
) -> None:
    """Add GARBLED SOURCE findings to the correction dictionary for future runs."""
    added = 0
    for wrong, right in garbled_pairs:
        # Only add if not already in the dictionary
        wrong_clean = wrong.strip().strip('"').strip("'")
        right_clean = right.strip().strip('"').strip("'")

        if wrong_clean and right_clean and wrong_clean not in corrections.proper_noun_corrections:
            corrections.proper_noun_corrections[wrong_clean] = right_clean
            added += 1
            logger.info("Added to correction dictionary: '%s' -> '%s'", wrong_clean, right_clean)

    if added > 0:
        save_corrections(corrections_path, series_id, corrections)
        logger.info("Updated correction dictionary with %d new entries", added)
