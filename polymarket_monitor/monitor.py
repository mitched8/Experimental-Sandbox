"""Polymarket FX Monitor — orchestrator class."""

import logging
import os

from .classifier import ScoredMarket, classify_markets
from .db import SnapshotDB
from .fetcher import fetch_active_markets
from .keywords import FilteredMarket, filter_markets
from .report import generate_report

logger = logging.getLogger(__name__)


class PolymarketFXMonitor:
    """Orchestrates the full Polymarket FX monitoring pipeline.

    Usage::

        monitor = PolymarketFXMonitor()
        report_md = monitor.run()
    """

    def __init__(
        self,
        db_path: str = "data/polymarket.db",
        anthropic_api_key: str | None = None,
    ):
        self._db_path = db_path
        self._anthropic_key = anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")

    def run(self, dry_run: bool = False) -> str:
        """Execute the full pipeline and return a markdown report.

        Args:
            dry_run: If True, fetch and filter only — skip Claude classification.
                     Useful for tuning the keyword list without API cost.

        Returns:
            A markdown string with the full report.
        """
        # Step 1: Fetch active markets from Polymarket
        logger.info("=" * 60)
        logger.info("STEP 1: Fetching active markets from Polymarket")
        logger.info("=" * 60)
        raw_markets = fetch_active_markets()

        # Step 2: Keyword filter
        logger.info("=" * 60)
        logger.info("STEP 2: Keyword filtering")
        logger.info("=" * 60)
        filtered = filter_markets(raw_markets)

        if not filtered:
            logger.warning("No markets matched keyword filter")
            return "# Polymarket FX Monitor\n\nNo FX-relevant markets found.\n"

        if dry_run:
            return self._dry_run_report(filtered)

        # Step 3: Claude classification
        logger.info("=" * 60)
        logger.info("STEP 3: Claude FX relevance classification")
        logger.info("=" * 60)
        if not self._anthropic_key:
            logger.error("ANTHROPIC_API_KEY required for classification")
            raise RuntimeError("ANTHROPIC_API_KEY not set")

        scored = classify_markets(filtered, self._anthropic_key)

        # Step 4: Store snapshot
        logger.info("=" * 60)
        logger.info("STEP 4: Storing snapshot")
        logger.info("=" * 60)
        db = SnapshotDB(self._db_path)
        try:
            db.store_snapshot(scored)
            snapshots = db.get_snapshots_with_deltas()
        finally:
            db.close()

        # Step 5: Generate report
        logger.info("=" * 60)
        logger.info("STEP 5: Generating report")
        logger.info("=" * 60)
        report = generate_report(snapshots)
        logger.info("Report generated (%d chars)", len(report))
        return report

    def _dry_run_report(self, filtered: list[FilteredMarket]) -> str:
        """Generate a simple dry-run summary (no Claude, no DB)."""
        lines = [
            "# Polymarket FX Monitor — Dry Run",
            "",
            f"**Markets fetched that matched keywords:** {len(filtered)}",
            "",
            "| # | Market | Yes Price | Volume 24h | Matched Categories |",
            "|---|--------|----------|-----------|-------------------|",
        ]
        for i, fm in enumerate(filtered, 1):
            q = fm.market.question
            if len(q) > 65:
                q = q[:64] + "…"
            price = f"{fm.market.yes_price * 100:.0f}%" if fm.market.yes_price else "—"
            vol = f"${fm.market.volume_24h:,.0f}"
            cats = ", ".join(fm.matched_categories)
            lines.append(f"| {i} | {q} | {price} | {vol} | {cats} |")

        lines.append("")
        lines.append("*Dry run — no Claude classification or DB storage performed.*")
        return "\n".join(lines)
