"""News headlines and naive sentiment scoring."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List

try:  # pragma: no cover - optional dependency for live mode
    import httpx
except Exception:  # pragma: no cover - offline fallback
    httpx = None

from strands.tools import tool
from strands.tools.decorator import DecoratedFunctionTool

from .base import json_tool_response


class NewsTool:
    """Fetch recent headlines for a ticker using live news providers."""

    def __init__(self, *, news_token: str | None) -> None:
        self.news_token = news_token

    def fetch(self, ticker: str) -> Dict[str, Any]:
        ticker = ticker.upper()
        if self.news_token:
            return self._fetch_newsapi_headlines(ticker)
        return self._fetch_gdelt_headlines(ticker)

    def _fetch_newsapi_headlines(self, ticker: str) -> Dict[str, Any]:
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
        return {
            "ticker": ticker,
            "articles": [
                {
                    "title": article.get("title"),
                    "summary": article.get("description"),
                    "url": article.get("url"),
                    "published_at": (article.get("publishedAt") or "")[:10],
                    "sentiment": self._naive_sentiment(article.get("description", "")),
                    "source": article.get("source", {}).get("name"),
                }
                for article in payload.get("articles", [])
            ],
        }

    def _fetch_gdelt_headlines(self, ticker: str) -> Dict[str, Any]:
        if httpx is None:
            raise RuntimeError("httpx is required for live news fetching but is not installed.")

        params = {
            "query": ticker,
            "mode": "ArtList",
            "format": "json",
            "maxrecords": 10,
        }
        with httpx.Client(timeout=10) as client:
            response = client.get("https://api.gdeltproject.org/api/v2/doc/doc", params=params)
            response.raise_for_status()
        payload = response.json()
        articles: List[Dict[str, Any]] = []
        for article in payload.get("articles", []):
            summary = article.get("seendescription") or article.get("themes") or ""
            raw_date = article.get("seendate", "") or ""
            if len(raw_date) == 8 and raw_date.isdigit():
                published_at = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
            else:
                published_at = raw_date
            articles.append(
                {
                    "title": article.get("title") or article.get("sourcecommonname"),
                    "summary": summary,
                    "url": article.get("url"),
                    "published_at": published_at,
                    "sentiment": self._naive_sentiment(summary),
                    "source": article.get("sourcecommonname"),
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


def build_news_tool(*, news_token: str | None) -> DecoratedFunctionTool:
    """Create a Strands tool that fetches recent news articles."""

    backend = NewsTool(news_token=news_token)

    @tool(name="news", description="Fetch NewsAPI headlines and naive sentiment for a ticker symbol.")
    def news_tool(ticker: str) -> Dict[str, Any]:
        payload = backend.fetch(ticker)
        return json_tool_response(payload)

    return news_tool
