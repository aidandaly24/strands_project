"""News headlines and naive sentiment scoring."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

try:  # pragma: no cover - optional dependency for live mode
    import httpx
except Exception:  # pragma: no cover - offline fallback
    httpx = None

from strands.tools import tool
from strands.tools.decorator import DecoratedFunctionTool

from .base import BaseTool, json_tool_response


class NewsTool(BaseTool):
    """Fetch recent headlines for a ticker using NewsAPI or fixtures."""

    def __init__(self, *, use_fixtures: bool, fixtures_path: Path, news_token: str | None) -> None:
        super().__init__(use_fixtures=use_fixtures, fixtures_path=fixtures_path)
        self.news_token = news_token

    def fetch(self, ticker: str) -> Dict[str, Any]:
        ticker = ticker.upper()
        if self.use_fixtures or not self.news_token:
            return self.load_fixture_json(f"news_{ticker}.json")
        return self._fetch_live_news(ticker)

    def _fetch_live_news(self, ticker: str) -> Dict[str, Any]:
        if httpx is None:
            raise RuntimeError("httpx is required for live news fetching but is not installed.")
        end = datetime.utcnow()
        start = end - timedelta(days=7)
        params = {
            "q": ticker,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 10,
            "from": start.strftime("%Y-%m-%d"),
            "to": end.strftime("%Y-%m-%d"),
            "apiKey": self.news_token,
        }
        with httpx.Client(timeout=10) as client:
            response = client.get("https://newsapi.org/v2/everything", params=params)
            response.raise_for_status()
        payload = response.json()
        articles = []
        for article in payload.get("articles", []):
            articles.append(
                {
                    "title": article.get("title"),
                    "summary": article.get("description"),
                    "url": article.get("url"),
                    "published_at": article.get("publishedAt", "")[:10],
                    "sentiment": self._naive_sentiment(article.get("description", "")),
                    "source": article.get("source", {}).get("name"),
                }
            )
        return {"ticker": ticker, "articles": articles}

    @staticmethod
    def _naive_sentiment(text: str) -> float:
        text = text.lower()
        positive = sum(text.count(word) for word in ("growth", "beat", "win", "strong"))
        negative = sum(text.count(word) for word in ("risk", "concern", "loss", "slow"))
        if positive == negative:
            return 0.0
        total = positive + negative
        if total == 0:
            return 0.0
        return round((positive - negative) / total, 2)


def build_news_tool(
    *, use_fixtures: bool, fixtures_path: Path, news_token: str | None
) -> DecoratedFunctionTool:
    """Create a Strands tool that fetches recent news articles."""

    backend = NewsTool(use_fixtures=use_fixtures, fixtures_path=fixtures_path, news_token=news_token)

    @tool(name="news", description="Fetch NewsAPI headlines and naive sentiment for a ticker symbol.")
    def news_tool(ticker: str) -> Dict[str, Any]:
        payload = backend.fetch(ticker)
        return json_tool_response(payload)

    return news_tool
