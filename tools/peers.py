"""Hard-coded peer groups for key tickers."""
from __future__ import annotations

from typing import Dict, List

from strands.tools import tool
from strands.tools.decorator import DecoratedFunctionTool

from .base import json_tool_response


_PEER_MAP: Dict[str, List[str]] = {
    "AMZN": ["MSFT", "GOOGL", "WMT"],
    "MSFT": ["GOOGL", "AMZN", "AAPL"],
    "SNOW": ["DDOG", "MDB", "NOW"],
}


class PeersTool:
    """Return a static peer group for a ticker."""

    def fetch(self, ticker: str) -> Dict[str, List[str]]:
        ticker = ticker.upper()
        peers = _PEER_MAP.get(ticker, [])
        return {"ticker": ticker, "peers": peers}


def build_peers_tool() -> DecoratedFunctionTool:
    """Create a Strands tool that returns static peer groups."""

    backend = PeersTool()

    @tool(name="peers", description="Return a static list of comparable tickers for the target company.")
    def peers_tool(ticker: str) -> Dict[str, List[str]]:
        payload = backend.fetch(ticker)
        return json_tool_response(payload)

    return peers_tool
