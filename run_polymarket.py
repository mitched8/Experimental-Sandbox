#!/usr/bin/env python3
"""CLI entry point for the Polymarket FX Monitor."""

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from polymarket_monitor.monitor import PolymarketFXMonitor


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Monitor Polymarket prediction markets for FX-relevant events.",
    )
    parser.add_argument(
        "--output",
        default="data/polymarket_fx_report.md",
        help="Path for the markdown report (default: data/polymarket_fx_report.md)",
    )
    parser.add_argument(
        "--db",
        default="data/polymarket.db",
        help="Path for the SQLite database (default: data/polymarket.db)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and filter only — skip Claude classification (no API cost)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose/debug logging",
    )
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        monitor = PolymarketFXMonitor(db_path=args.db)
        report = monitor.run(dry_run=args.dry_run)

        # Save report
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
        logging.info("Report saved to %s", out_path)

        # Also print to stdout
        print(report)

    except KeyboardInterrupt:
        logging.info("Interrupted by user")
        sys.exit(130)
    except Exception:
        logging.exception("Pipeline failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
