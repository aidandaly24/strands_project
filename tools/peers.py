"""Hard-coded peer groups for key tickers."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from strands.tools import tool
from strands.tools.decorator import DecoratedFunctionTool

from .base import BaseTool, json_tool_response


_PEER_MAP: Dict[str, List[str]] = {
    "AMZN": ["MSFT", "GOOGL", "WMT"],
    "MSFT": ["GOOGL", "AMZN", "AAPL"],
    "SNOW": ["DDOG", "MDB", "NOW"],
}


class PeersTool(BaseTool):
    """Return a static peer group for a ticker."""

    def __init__(self, *, use_fixtures: bool, fixtures_path: Path) -> None:
        super().__init__(use_fixtures=use_fixtures, fixtures_path=fixtures_path)

    def fetch(self, ticker: str) -> Dict[str, List[str]]:
        ticker = ticker.upper()
        peers = _PEER_MAP.get(ticker, [])
        return {"ticker": ticker, "peers": peers}


def build_peers_tool(*, use_fixtures: bool, fixtures_path: Path) -> DecoratedFunctionTool:
    """Create a Strands tool that returns static peer groups."""

    backend = PeersTool(use_fixtures=use_fixtures, fixtures_path=fixtures_path)

    @tool(name="peers", description="Return a static list of comparable tickers for the target company.")
    def peers_tool(ticker: str) -> Dict[str, List[str]]:
        payload = backend.fetch(ticker)
        return json_tool_response(payload)

    return peers_tool
