"""SQLite snapshot storage and delta computation."""

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .classifier import ScoredMarket

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = "data/polymarket.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    market_id TEXT NOT NULL,
    slug TEXT,
    question TEXT NOT NULL,
    yes_price REAL,
    no_price REAL,
    volume_24h REAL,
    liquidity REAL,
    fx_score INTEGER,
    fx_reason TEXT,
    affected_pairs TEXT,
    matched_categories TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_market_run
    ON snapshots(market_id, run_id);
"""


@dataclass
class MarketSnapshot:
    """A stored snapshot with optional delta information."""

    market_id: str
    slug: str
    question: str
    yes_price: float | None
    no_price: float | None
    volume_24h: float
    liquidity: float
    fx_score: int
    fx_reason: str
    affected_pairs: list[str]
    matched_categories: list[str]
    fetched_at: str
    # Deltas vs previous snapshot (None if no prior data)
    yes_price_delta: float | None = None
    volume_delta: float | None = None

    @property
    def url(self) -> str:
        return f"https://polymarket.com/event/{self.slug}"


class SnapshotDB:
    """Manages SQLite storage for market snapshots."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def store_snapshot(self, scored_markets: list[ScoredMarket]) -> int:
        """Insert a batch of scored markets as a new snapshot run.

        Returns the run_id for this snapshot.
        """
        cursor = self._conn.execute("INSERT INTO runs DEFAULT VALUES")
        run_id = cursor.lastrowid

        rows = []
        for sm in scored_markets:
            m = sm.market.market
            rows.append((
                run_id,
                m.market_id,
                m.slug,
                m.question,
                m.yes_price,
                m.no_price,
                m.volume_24h,
                m.liquidity,
                sm.fx_score,
                sm.fx_reason,
                json.dumps(sm.affected_pairs),
                json.dumps(sm.market.matched_categories),
            ))

        self._conn.executemany(
            """INSERT INTO snapshots
               (run_id, market_id, slug, question, yes_price, no_price,
                volume_24h, liquidity, fx_score, fx_reason,
                affected_pairs, matched_categories)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        self._conn.commit()
        logger.info("Stored %d market snapshots (run %d)", len(rows), run_id)
        return run_id

    def get_snapshots_with_deltas(self) -> list[MarketSnapshot]:
        """Get the latest snapshot for each market, with deltas vs the previous run."""
        # Get the most recent run_id
        row = self._conn.execute(
            "SELECT MAX(run_id) as latest FROM runs"
        ).fetchone()
        if not row or not row["latest"]:
            return []

        latest_run = row["latest"]
        latest_ts_row = self._conn.execute(
            "SELECT fetched_at FROM runs WHERE run_id = ?", (latest_run,)
        ).fetchone()
        latest_ts = latest_ts_row["fetched_at"] if latest_ts_row else ""

        # Find the previous run_id
        prev_row = self._conn.execute(
            "SELECT MAX(run_id) as prev FROM runs WHERE run_id < ?", (latest_run,)
        ).fetchone()
        prev_run = prev_row["prev"] if prev_row and prev_row["prev"] else None

        # Build a lookup of previous prices if a prior run exists
        prev_prices: dict[str, tuple[float | None, float | None]] = {}
        if prev_run is not None:
            for p in self._conn.execute(
                "SELECT market_id, yes_price, volume_24h FROM snapshots WHERE run_id = ?",
                (prev_run,),
            ):
                prev_prices[p["market_id"]] = (p["yes_price"], p["volume_24h"])

        # Get all markets from the latest run
        current_rows = self._conn.execute(
            "SELECT * FROM snapshots WHERE run_id = ?", (latest_run,)
        ).fetchall()

        snapshots: list[MarketSnapshot] = []
        for cur in current_rows:
            yes_delta = None
            vol_delta = None
            prev = prev_prices.get(cur["market_id"])
            if prev is not None:
                prev_yes, prev_vol = prev
                if cur["yes_price"] is not None and prev_yes is not None:
                    yes_delta = cur["yes_price"] - prev_yes
                if cur["volume_24h"] is not None and prev_vol is not None:
                    vol_delta = cur["volume_24h"] - prev_vol

            snapshots.append(
                MarketSnapshot(
                    market_id=cur["market_id"],
                    slug=cur["slug"],
                    question=cur["question"],
                    yes_price=cur["yes_price"],
                    no_price=cur["no_price"],
                    volume_24h=cur["volume_24h"],
                    liquidity=cur["liquidity"],
                    fx_score=cur["fx_score"],
                    fx_reason=cur["fx_reason"],
                    affected_pairs=json.loads(cur["affected_pairs"] or "[]"),
                    matched_categories=json.loads(cur["matched_categories"] or "[]"),
                    fetched_at=latest_ts,
                    yes_price_delta=yes_delta,
                    volume_delta=vol_delta,
                )
            )

        return snapshots

    def close(self) -> None:
        self._conn.close()
