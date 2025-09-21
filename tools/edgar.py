"""SEC EDGAR helper to retrieve filing excerpts."""
from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from typing import Dict

try:  # pragma: no cover - optional dependency for live mode
    import httpx
except Exception:  # pragma: no cover - offline fallback
    httpx = None

from strands.tools import tool
from strands.tools.decorator import DecoratedFunctionTool

from .base import BaseTool, json_tool_response


class EdgarTool(BaseTool):
    """Fetch Item 7 style MD&A snippets for a ticker."""

    def __init__(self, *, use_fixtures: bool, fixtures_path: Path, sec_user_agent: str | None) -> None:
        super().__init__(use_fixtures=use_fixtures, fixtures_path=fixtures_path)
        self.sec_user_agent = sec_user_agent

    def fetch(self, ticker: str) -> Dict[str, str]:
        ticker = ticker.upper()
        if self.use_fixtures or not self.sec_user_agent:
            html = self.load_fixture_text(f"filing_{ticker}_item7.html")
            return {"ticker": ticker, "section": self._extract_text(html)}
        return self._fetch_live_html(ticker)

    def _fetch_live_html(self, ticker: str) -> Dict[str, str]:
        if not self.sec_user_agent:
            raise RuntimeError("SEC user agent is required for live EDGAR calls.")
        if httpx is None:
            raise RuntimeError("httpx is required for live EDGAR calls but is not installed.")
        headers = {"User-Agent": self.sec_user_agent}
        params = {"ticker": ticker, "type": "10-K", "count": 1}
        with httpx.Client(timeout=10, headers=headers) as client:
            response = client.get("https://data.sec.gov/submissions/CIK0001321655.json", params=params)
            response.raise_for_status()
        # Placeholder: in real implementation parse JSON to locate filing URL.
        return {"ticker": ticker, "section": "Live EDGAR fetching not implemented in this offline build."}

    @staticmethod
    def _extract_text(html: str) -> str:
        class ParagraphCollector(HTMLParser):
            def __init__(self) -> None:
                super().__init__()
                self.in_paragraph = False
                self.chunks: list[str] = []

            def handle_starttag(self, tag, attrs):  # type: ignore[override]
                if tag.lower() == "p":
                    self.in_paragraph = True

            def handle_endtag(self, tag):  # type: ignore[override]
                if tag.lower() == "p":
                    self.in_paragraph = False

            def handle_data(self, data):  # type: ignore[override]
                if self.in_paragraph:
                    text = data.strip()
                    if text:
                        self.chunks.append(text)

        parser = ParagraphCollector()
        parser.feed(html)
        return " ".join(parser.chunks)


def build_edgar_tool(
    *, use_fixtures: bool, fixtures_path: Path, sec_user_agent: str | None
) -> DecoratedFunctionTool:
    """Create a Strands tool for fetching SEC MD&A excerpts."""

    backend = EdgarTool(use_fixtures=use_fixtures, fixtures_path=fixtures_path, sec_user_agent=sec_user_agent)

    @tool(name="edgar", description="Fetch Item 7 management commentary for a ticker.")
    def edgar_tool(ticker: str) -> Dict[str, str]:
        payload = backend.fetch(ticker)
        return json_tool_response(payload)

    return edgar_tool
