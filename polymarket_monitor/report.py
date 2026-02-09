"""Markdown report generation from market snapshots."""

import logging
from datetime import datetime

from .db import MarketSnapshot

logger = logging.getLogger(__name__)


def generate_report(snapshots: list[MarketSnapshot]) -> str:
    """Generate a structured markdown report from the latest snapshots."""
    if not snapshots:
        return "# Polymarket FX Monitor\n\nNo markets tracked yet.\n"

    parts: list[str] = []

    parts.append("# Polymarket FX Monitor Report")
    parts.append(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
    parts.append("")

    # --- Summary stats ---
    parts.append("## Summary")
    parts.append("")
    parts.append(f"- **Markets tracked:** {len(snapshots)}")

    high_rel = [s for s in snapshots if s.fx_score >= 7]
    parts.append(f"- **High FX relevance (score >= 7):** {len(high_rel)}")

    movers = [s for s in snapshots if s.yes_price_delta is not None]
    parts.append(f"- **Markets with price history:** {len(movers)}")
    parts.append("")

    # --- Biggest movers ---
    movers_sorted = sorted(
        [s for s in snapshots if s.yes_price_delta is not None],
        key=lambda s: abs(s.yes_price_delta or 0),
        reverse=True,
    )[:10]

    if movers_sorted:
        parts.append("## Biggest Movers")
        parts.append("")
        parts.append("| Market | Yes Price | Change | FX Score | Pairs |")
        parts.append("|--------|----------|--------|----------|-------|")
        for s in movers_sorted:
            delta_str = _format_delta(s.yes_price_delta)
            pairs_str = ", ".join(s.affected_pairs) if s.affected_pairs else "—"
            question = _truncate(s.question, 60)
            parts.append(
                f"| [{question}]({s.url}) | {_pct(s.yes_price)} | {delta_str} | {s.fx_score}/10 | {pairs_str} |"
            )
        parts.append("")

    # --- High FX relevance ---
    high_sorted = sorted(high_rel, key=lambda s: s.fx_score, reverse=True)

    if high_sorted:
        parts.append("## High FX Relevance (Score >= 7)")
        parts.append("")
        for s in high_sorted:
            delta_str = _format_delta(s.yes_price_delta)
            pairs_str = ", ".join(s.affected_pairs) if s.affected_pairs else "—"
            parts.append(f"### [{s.question}]({s.url})")
            parts.append("")
            parts.append(f"- **FX Score:** {s.fx_score}/10 — {s.fx_reason}")
            parts.append(f"- **Yes Price:** {_pct(s.yes_price)} {delta_str}")
            parts.append(f"- **24h Volume:** ${s.volume_24h:,.0f}")
            parts.append(f"- **Affected Pairs:** {pairs_str}")
            parts.append(f"- **Categories:** {', '.join(s.matched_categories)}")
            parts.append("")

    # --- Watchlist ---
    watchlist = sorted(
        [s for s in snapshots if 4 <= s.fx_score <= 6],
        key=lambda s: s.fx_score,
        reverse=True,
    )

    if watchlist:
        parts.append("## Watchlist (Score 4-6)")
        parts.append("")
        parts.append("| Market | Yes Price | Change | FX Score | Reason |")
        parts.append("|--------|----------|--------|----------|--------|")
        for s in watchlist:
            delta_str = _format_delta(s.yes_price_delta)
            question = _truncate(s.question, 55)
            reason = _truncate(s.fx_reason, 50)
            parts.append(
                f"| [{question}]({s.url}) | {_pct(s.yes_price)} | {delta_str} | {s.fx_score}/10 | {reason} |"
            )
        parts.append("")

    # --- Low relevance (collapsed) ---
    low = [s for s in snapshots if s.fx_score < 4]
    if low:
        parts.append(f"<details><summary>Low relevance ({len(low)} markets, score < 4)</summary>")
        parts.append("")
        for s in low:
            parts.append(f"- **{s.question}** — {_pct(s.yes_price)} (score {s.fx_score})")
        parts.append("")
        parts.append("</details>")
        parts.append("")

    return "\n".join(parts)


def _pct(price: float | None) -> str:
    if price is None:
        return "—"
    return f"{price * 100:.0f}%"


def _format_delta(delta: float | None) -> str:
    if delta is None:
        return "(new)"
    sign = "+" if delta >= 0 else ""
    return f"({sign}{delta * 100:.1f}pp)"


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"
