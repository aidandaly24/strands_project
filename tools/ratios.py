"""Technical ratio helpers derived from price history."""
from __future__ import annotations

from typing import Any, Dict, Iterable, List

from strands.tools import tool
from strands.tools.decorator import DecoratedFunctionTool

from .base import json_tool_response


def _sma(values: Iterable[float]) -> float:
    values = list(values)
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


def _rsi(prices: List[float], period: int = 14) -> float:
    if len(prices) < period + 1:
        return 50.0
    gains = []
    losses = []
    for i in range(1, period + 1):
        change = prices[-i] - prices[-i - 1]
        if change >= 0:
            gains.append(change)
        else:
            losses.append(abs(change))
    avg_gain = sum(gains) / period if gains else 0.0
    avg_loss = sum(losses) / period if losses else 0.0
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


class RatiosTool:
    """Compute SMA20, SMA50, and RSI14 from price history."""

    def compute(self, price_payload: Dict[str, Any]) -> Dict[str, float]:
        history = price_payload.get("history", [])
        closes = [float(row["close"]) for row in history]
        return {
            "sma20": _sma(closes[-20:]),
            "sma50": _sma(closes[-50:]),
            "rsi14": _rsi(closes, period=14),
            "latest_close": closes[-1] if closes else 0.0,
        }


def build_ratios_tool() -> DecoratedFunctionTool:
    """Create a Strands tool to compute technical ratios from price payloads."""

    backend = RatiosTool()

    @tool(name="ratios", description="Compute SMA and RSI metrics from price history data.")
    def ratios_tool(price_payload: Dict[str, Any]) -> Dict[str, float]:
        payload = backend.compute(price_payload)
        return json_tool_response(payload)

    return ratios_tool
