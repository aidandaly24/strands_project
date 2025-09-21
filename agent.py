"""Research orchestration that runs on top of the Strands Agent runtime."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean
from typing import Any, Dict, Iterable, List, Optional, cast

from strands import Agent
from strands.tools.decorator import DecoratedFunctionTool

from tools import (
    build_edgar_tool,
    build_news_tool,
    build_peers_tool,
    build_prices_tool,
    build_ratios_tool,
    extract_json_content,
)

from settings import Settings


@dataclass(slots=True)
class RunArtifacts:
    json_payload: Dict[str, Any]
    markdown: str
    output_dir: Path


class ResearchAgent:
    """Aggregate the individual tools to produce research artifacts."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

        self._tool_objects: Dict[str, DecoratedFunctionTool] = {
            "prices": build_prices_tool(
                use_fixtures=settings.use_fixtures,
                fixtures_path=settings.fixtures_path,
            ),
            "news": build_news_tool(
                use_fixtures=settings.use_fixtures,
                fixtures_path=settings.fixtures_path,
                news_token=settings.news_token,
            ),
            "edgar": build_edgar_tool(
                use_fixtures=settings.use_fixtures,
                fixtures_path=settings.fixtures_path,
                sec_user_agent=settings.sec_user_agent,
            ),
            "ratios": build_ratios_tool(
                use_fixtures=settings.use_fixtures,
                fixtures_path=settings.fixtures_path,
            ),
            "peers": build_peers_tool(
                use_fixtures=settings.use_fixtures,
                fixtures_path=settings.fixtures_path,
            ),
        }

        self.agent = Agent(
            tools=list(self._tool_objects.values()),
            system_prompt=(
                "You are an equity research assistant that combines structured data sources "
                "to produce concise, citation-backed insights."
            ),
        )

    def run(self, tickers: Iterable[str], *, focus: Optional[str] = None) -> RunArtifacts:
        tickers = [ticker.upper() for ticker in tickers]
        generated_at = datetime.now(UTC)
        run_id = generated_at.strftime("%Y%m%d_%H%M%S")
        output_dir = self.settings.runs_dir / run_id
        output_dir.mkdir(parents=True, exist_ok=True)

        ticker_payloads: List[Dict[str, Any]] = []
        markdown_sections: List[str] = ["# Research Brief"]
        for ticker in tickers:
            payload = self._gather_for_ticker(ticker)
            payload["focus"] = focus
            ticker_payloads.append(payload)
            markdown_sections.append(self._format_markdown_for_ticker(payload))

        json_payload = {
            "run_id": run_id,
            "generated_at": generated_at.isoformat() + "Z",
            "tickers": ticker_payloads,
        }
        markdown = "\n\n".join(markdown_sections).strip() + "\n"
        return RunArtifacts(json_payload=json_payload, markdown=markdown, output_dir=output_dir)

    def _gather_for_ticker(self, ticker: str) -> Dict[str, Any]:
        price_data = self._invoke_tool("prices", ticker=ticker)
        ratio_data = self._invoke_tool("ratios", price_payload=price_data)
        news_data = self._invoke_tool("news", ticker=ticker)
        edgar_data = self._invoke_tool("edgar", ticker=ticker)
        peers_data = self._invoke_tool("peers", ticker=ticker)

        articles = news_data.get("articles", [])
        avg_sentiment = fmean([article.get("sentiment", 0.0) for article in articles]) if articles else 0.0
        positive_articles = [article for article in articles if article.get("sentiment", 0) >= 0]
        negative_articles = [article for article in articles if article.get("sentiment", 0) < 0]

        citations: List[Dict[str, str]] = []
        for article in articles:
            citations.append(
                {
                    "ticker": ticker,
                    "title": article.get("title"),
                    "url": article.get("url"),
                    "source": article.get("source"),
                    "published_at": article.get("published_at"),
                }
            )
        citations.append(
            {
                "ticker": ticker,
                "title": "Management discussion and analysis excerpt",
                "url": str(self.settings.fixtures_path / f"filing_{ticker}_item7.html"),
                "source": "SEC Filing Fixture" if self.settings.use_fixtures else "SEC EDGAR",
                "published_at": "",
            }
        )

        overview = self._build_overview(price_data, ratio_data, avg_sentiment)
        moat = edgar_data.get("section", "Management commentary unavailable.")
        performance = self._build_performance(ratio_data, price_data)
        catalysts = self._summarise_articles(positive_articles)
        risks = self._summarise_articles(negative_articles)
        valuation = self._build_valuation(price_data)

        return {
            "ticker": ticker,
            "prices": price_data,
            "ratios": ratio_data,
            "news": news_data,
            "edgar": edgar_data,
            "peers": peers_data,
            "sentiment": {
                "average": round(avg_sentiment, 2),
                "article_count": len(articles),
            },
            "sections": {
                "overview": overview,
                "moat": moat,
                "performance": performance,
                "catalysts": catalysts,
                "risks": risks,
                "valuation": valuation,
            },
            "citations": citations,
        }

    def _format_markdown_for_ticker(self, payload: Dict[str, Any]) -> str:
        ticker = payload["ticker"]
        sections = payload["sections"]
        peers = payload.get("peers", {}).get("peers", [])
        citations = payload.get("citations", [])
        focus = payload.get("focus")

        lines = [f"## {ticker}"]
        if focus:
            lines.append(f"_Focus: {focus}_")
        lines.extend(
            [
                "### Overview",
                sections["overview"],
                "### Moat",
                sections["moat"],
                "### Performance",
                sections["performance"],
                "### Catalysts",
                sections["catalysts"],
                "### Risks",
                sections["risks"],
                "### Valuation",
                sections["valuation"],
            ]
        )
        if peers:
            lines.append("### Peers")
            lines.append(", ".join(peers))

        if citations:
            lines.append("### Sources")
            for idx, citation in enumerate(citations, start=1):
                url = citation.get("url")
                title = citation.get("title")
                source = citation.get("source")
                published = citation.get("published_at")
                label = f"{title} — {source}"
                if published:
                    label += f" ({published})"
                if url:
                    lines.append(f"{idx}. [{label}]({url})")
                else:
                    lines.append(f"{idx}. {label}")
        return "\n\n".join(lines)

    def _invoke_tool(self, name: str, **kwargs: Any) -> Dict[str, Any]:
        """Execute a Strands tool and extract its JSON payload."""

        tool = self._tool_objects[name]
        tool_caller = getattr(self.agent.tool, tool.tool_name)
        result = tool_caller(**kwargs)
        payload = extract_json_content(result)
        return cast(Dict[str, Any], payload)

    @staticmethod
    def _build_overview(price_data: Dict[str, Any], ratio_data: Dict[str, float], sentiment: float) -> str:
        latest_close = ratio_data.get("latest_close")
        high = price_data.get("fifty_two_week_high")
        low = price_data.get("fifty_two_week_low")
        return (
            f"Shares trade at ${latest_close:.2f} within a 52-week range of ${low:.2f}–${high:.2f}. "
            f"Headline sentiment over the past week averages {sentiment:.2f}."
        )

    @staticmethod
    def _build_performance(ratio_data: Dict[str, float], price_data: Dict[str, Any]) -> str:
        sma20 = ratio_data.get("sma20")
        sma50 = ratio_data.get("sma50")
        rsi = ratio_data.get("rsi14")
        latest = ratio_data.get("latest_close")
        currency = price_data.get("currency", "USD")
        return (
            f"Latest close: {currency} {latest:.2f}. SMA20: {sma20:.2f}, SMA50: {sma50:.2f}, "
            f"RSI14: {rsi:.2f}."
        )

    @staticmethod
    def _summarise_articles(articles: List[Dict[str, Any]]) -> str:
        if not articles:
            return "No notable items in the latest coverage."
        bullets = []
        for article in articles[:3]:
            summary = article.get("summary") or article.get("title")
            source = article.get("source", "")
            bullets.append(f"- {summary} ({source})")
        return "\n".join(bullets)

    @staticmethod
    def _build_valuation(price_data: Dict[str, Any]) -> str:
        high = price_data.get("fifty_two_week_high")
        low = price_data.get("fifty_two_week_low")
        latest = price_data.get("history", [])[-1]["close"] if price_data.get("history") else 0.0
        distance_to_high = ((high - latest) / high * 100) if high else 0.0
        return (
            f"Trading {distance_to_high:.1f}% below the 52-week high of ${high:.2f}, "
            f"with downside to the 52-week low at ${low:.2f}."
        )
