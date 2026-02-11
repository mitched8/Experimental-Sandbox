"""Stance file management — track and update podcast series views over time."""

import logging
from datetime import date
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


def load_stance(stance_path: Path) -> dict | None:
    """Load an existing stance file, or return None if it doesn't exist."""
    if not stance_path.exists():
        logger.info("No existing stance file at %s — will create from scratch", stance_path)
        return None

    with open(stance_path, encoding="utf-8") as f:
        stance = yaml.safe_load(f) or {}

    logger.info(
        "Loaded stance file: %s (last updated: %s)",
        stance_path,
        stance.get("last_updated", "unknown"),
    )
    return stance


def save_stance(stance_path: Path, stance_data: dict) -> None:
    """Write stance data to YAML file."""
    stance_path.parent.mkdir(parents=True, exist_ok=True)
    with open(stance_path, "w", encoding="utf-8") as f:
        yaml.dump(
            stance_data,
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
    logger.info("Saved stance file: %s", stance_path)


def format_stance_for_prompt(stance: dict | None) -> str:
    """Format the stance file as a string for inclusion in the Claude prompt.

    Returns empty string if no stance exists.
    """
    if not stance:
        return ""

    return yaml.dump(stance, default_flow_style=False, allow_unicode=True, sort_keys=False)


def apply_stance_updates(
    existing_stance: dict | None,
    updates_yaml: str,
    episode_title: str,
) -> dict:
    """Parse stance updates from the summary output and merge into existing stance.

    Args:
        existing_stance: Current stance dict (or None for first run).
        updates_yaml: Raw YAML string from the summary's stance_updates section.
        episode_title: Episode title for metadata.

    Returns:
        Updated stance dict.
    """
    today = date.today().isoformat()

    # Parse the updates YAML
    try:
        updates = yaml.safe_load(updates_yaml)
    except yaml.YAMLError:
        logger.warning("Failed to parse stance updates YAML, returning existing stance")
        return existing_stance or _empty_stance(today, episode_title)

    if not isinstance(updates, dict):
        logger.warning("Stance updates is not a dict, returning existing stance")
        return existing_stance or _empty_stance(today, episode_title)

    if existing_stance is None:
        # First run — build from scratch
        stance = _empty_stance(today, episode_title)
    else:
        stance = existing_stance.copy()
        stance["last_updated"] = today
        stance["source_episode"] = episode_title

    # Merge macro_framework updates
    if "macro_framework" in updates:
        if "macro_framework" not in stance:
            stance["macro_framework"] = {}
        for key, value in updates["macro_framework"].items():
            if isinstance(value, dict):
                stance["macro_framework"][key] = value
            else:
                stance["macro_framework"][key] = {"view": str(value), "since": today}

    # Merge currency_views updates
    if "currency_views" in updates:
        if "currency_views" not in stance:
            stance["currency_views"] = {}
        for ccy, view_data in updates["currency_views"].items():
            if isinstance(view_data, dict):
                # Track what changed
                old_view = stance["currency_views"].get(ccy, {})
                new_view = view_data.copy()

                # Set last_changed if direction/target differs
                if old_view.get("direction") != new_view.get("direction"):
                    new_view["last_changed"] = today
                    if old_view.get("direction"):
                        new_view["change_type"] = "view_reversal"
                    else:
                        new_view["change_type"] = "new"
                elif old_view.get("target") != new_view.get("target"):
                    new_view["last_changed"] = today
                    new_view.setdefault("change_type", "target_update")

                # Preserve 'since' if direction unchanged
                if old_view.get("direction") == new_view.get("direction") and "since" in old_view:
                    new_view.setdefault("since", old_view["since"])
                else:
                    new_view.setdefault("since", today)

                stance["currency_views"][ccy] = new_view

    return stance


def _empty_stance(today: str, episode_title: str) -> dict:
    """Create an empty stance structure."""
    return {
        "last_updated": today,
        "source_episode": episode_title,
        "macro_framework": {},
        "currency_views": {},
    }
