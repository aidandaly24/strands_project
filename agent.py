"""Research orchestration that runs on top of the Strands Agent runtime."""
from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
from typing import Any, Dict, Iterable, List, Optional, cast

from pydantic import BaseModel, ValidationError
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


SYSTEM_PROMPT = (
    "You are an equity research assistant who synthesises prices, fundamentals, "
    "filing excerpts, peer comparisons, and news flow into thorough, citation-"
    "aware investment briefs. Analyse the full data context and write multi-"
    "paragraph sections that highlight drivers, nuances, and supporting evidence."
)


class ResearchSections(BaseModel):
    """Structured representation of the narrative sections in a brief."""

    overview: str
    moat: str
    performance: str
    catalysts: str
    risks: str
    valuation: str


@dataclass(slots=True)
class RunArtifacts:
    json_payload: Dict[str, Any]
    markdown: str
    output_dir: Path


class ResearchAgent:
    """Aggregate the individual tools to produce research artifacts."""

    def __init__(self, settings: Settings, *, model: Any | None = None) -> None:
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

        agent_kwargs: Dict[str, Any] = {
            "tools": list(self._tool_objects.values()),
            "system_prompt": SYSTEM_PROMPT,
        }
        if model is not None:
            agent_kwargs["model"] = model
        self.agent = Agent(**agent_kwargs)

    def run(self, tickers: Iterable[str], *, focus: Optional[str] = None) -> RunArtifacts:
        tickers = [ticker.upper() for ticker in tickers]
        generated_at = datetime.now(timezone.utc)
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
            "generated_at": generated_at.isoformat().replace("+00:00", "Z"),
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
        edgar_source_url: Optional[str]
        if self.settings.use_fixtures:
            edgar_source_url = str(self.settings.fixtures_path / f"filing_{ticker}_item7.html")
        else:
            edgar_source_url = cast(Optional[str], edgar_data.get("source_url") or edgar_data.get("url"))

        citations.append(
            {
                "ticker": ticker,
                "title": "Management discussion and analysis excerpt",
                "url": edgar_source_url,
                "source": "SEC Filing Fixture" if self.settings.use_fixtures else "SEC EDGAR",
                "published_at": cast(str, edgar_data.get("filed_on", "")),
            }
        )

        generated_sections = self._generate_sections(
            ticker=ticker,
            price_data=price_data,
            ratio_data=ratio_data,
            news_data=news_data,
            edgar_data=edgar_data,
            peers_data=peers_data,
            avg_sentiment=avg_sentiment,
            positive_articles=positive_articles,
            negative_articles=negative_articles,
        )

        if generated_sections is None:
            overview = self._build_overview(price_data, ratio_data, avg_sentiment)
            moat = edgar_data.get("section", "Management commentary unavailable.")
            performance = self._build_performance(ratio_data, price_data)
            catalysts = self._summarise_articles(positive_articles)
            risks = self._summarise_articles(negative_articles)
            valuation = self._build_valuation(price_data)
            sections_payload = {
                "overview": overview,
                "moat": moat,
                "performance": performance,
                "catalysts": catalysts,
                "risks": risks,
                "valuation": valuation,
            }
        else:
            sections_payload = generated_sections.model_dump()

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
            "sections": sections_payload,
            "citations": citations,
        }

    def _generate_sections(
        self,
        *,
        ticker: str,
        price_data: Dict[str, Any],
        ratio_data: Dict[str, Any],
        news_data: Dict[str, Any],
        edgar_data: Dict[str, Any],
        peers_data: Dict[str, Any],
        avg_sentiment: float,
        positive_articles: List[Dict[str, Any]],
        negative_articles: List[Dict[str, Any]],
    ) -> Optional[ResearchSections]:
        """Request multi-paragraph sections from the hosted research agent."""

        structured_fn = getattr(self.agent, "structured_output", None)
        if structured_fn is None:
            return None

        prompt = textwrap.dedent(
            f"""
            You are preparing a comprehensive equity research brief for {ticker}. Analyse the
            structured context and produce nuanced paragraphs for each section below. Each
            section must contain at least two sentences or explicit paragraph breaks and should
            reference supporting evidence using markdown citations where possible.

            ## Price & performance snapshot
            {json.dumps(price_data, indent=2, default=str)}

            ## Technical and fundamental ratios
            {json.dumps(ratio_data, indent=2, default=str)}

            ## Recent news flow
            {json.dumps(news_data.get("articles", []), indent=2, default=str)}

            ## Filing excerpts
            {json.dumps(edgar_data, indent=2, default=str)}

            ## Peer benchmarks
            {json.dumps(peers_data, indent=2, default=str)}

            ## Sentiment summary
            {json.dumps({"average": avg_sentiment, "positives": len(positive_articles), "negatives": len(negative_articles)}, indent=2, default=str)}

            Craft analytical copy for the following fields: overview, moat, performance,
            catalysts, risks, valuation. Highlight what the data implies for the company,
            mention catalysts and watchpoints surfaced in the articles, and include peer or
            valuation context when appropriate. Do not return markdown headings; only the
            prose for each field. Use citation indices like [1] that can map onto the supplied
            sources.
            """
        ).strip()

        candidate_payloads = (
            {"prompt": prompt, "response_model": ResearchSections},
            {"prompt": prompt, "schema": ResearchSections},
            {"input": prompt, "response_model": ResearchSections},
        )

        for call_kwargs in candidate_payloads:
            try:
                result = structured_fn(**call_kwargs)
            except TypeError:
                continue
            except Exception:
                return None

            if isinstance(result, ResearchSections):
                return result

            try:
                return ResearchSections.model_validate(result)
            except ValidationError:
                continue

        return None

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
            return (
                "Recent monitoring did not surface fresh red flags for the company. "
                "Investors should remain mindful of execution risks and potential regulatory scrutiny in core markets."
            )
        tone = "favourable" if articles[0].get("sentiment", 0) >= 0 else "cautionary"
        bullets = []
        for article in articles[:3]:
            summary = article.get("summary") or article.get("title")
            source = article.get("source", "")
            bullets.append(f"- {summary} ({source})")
        intro = (
            f"Recent coverage surfaces {len(articles)} {tone} developments shaping investor "
            "sentiment."
        )
        return intro + "\n\n" + "\n".join(bullets)

    @staticmethod
    def _build_valuation(price_data: Dict[str, Any]) -> str:
        high = price_data.get("fifty_two_week_high")
        low = price_data.get("fifty_two_week_low")
        latest = price_data.get("history", [])[-1]["close"] if price_data.get("history") else 0.0
        distance_to_high = ((high - latest) / high * 100) if high else 0.0
        return (
            f"Trading {distance_to_high:.1f}% below the 52-week high of ${high:.2f}, "
            f"with downside to the 52-week low at ${low:.2f}. "
            f"The latest close near ${latest:.2f} frames the upside/downside skew investors are weighing."
        )
