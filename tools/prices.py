"""Price history and snapshot metrics sourced from Yahoo Finance."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

import statistics

try:
    import yfinance as yf
except Exception:  # pragma: no cover - optional dependency for offline mode
    yf = None

from strands.tools import tool
from strands.tools.decorator import DecoratedFunctionTool

from .base import BaseTool, json_tool_response


class PricesTool(BaseTool):
    """Fetch price history and derived metrics for a ticker."""

    def fetch(self, ticker: str) -> Dict[str, Any]:
        ticker = ticker.upper()
        if self.use_fixtures:
            return self.load_fixture_json(f"prices_{ticker}.json")
        if yf is None:
            raise RuntimeError("yfinance is required for live price fetching but is not installed.")

        history = self._download_history(ticker)
        closes = [item["close"] for item in history]
        latest_close = closes[-1]
        return {
            "ticker": ticker,
            "currency": "USD",
            "history": history,
            "fifty_two_week_high": max(closes),
            "fifty_two_week_low": min(closes),
            "latest_close": latest_close,
            "avg_close_30d": round(statistics.fmean(closes[-30:]), 2) if len(closes) >= 30 else latest_close,
        }

    def _download_history(self, ticker: str) -> List[Dict[str, Any]]:
        end = datetime.utcnow()
        start = end - timedelta(days=120)
        data = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
        if data.empty:
            raise ValueError(f"No price data returned for {ticker}.")
        history: List[Dict[str, Any]] = []
        for index, row in data.tail(90).iterrows():
            history.append({
                "date": index.strftime("%Y-%m-%d"),
                "close": round(float(row["Close"]), 2),
            })
        return history


def build_prices_tool(*, use_fixtures: bool, fixtures_path: Path) -> DecoratedFunctionTool:
    """Create a Strands tool for fetching price payloads."""

    backend = PricesTool(use_fixtures=use_fixtures, fixtures_path=fixtures_path)

    @tool(name="prices", description="Fetch price history and summary statistics for an equity ticker.")
    def prices_tool(ticker: str) -> Dict[str, Any]:
        payload = backend.fetch(ticker)
        return json_tool_response(payload)

    return prices_tool
