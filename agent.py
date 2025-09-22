"""Research orchestration that runs on top of the Strands Agent runtime."""
from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Mapping
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


class ToolExecutionError(RuntimeError):
    """Raised when a tool fails but we want to continue collecting errors."""


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

    def __init__(self, settings: Settings, *, model: Any | None = None, collect_failures: bool = False) -> None:
        self.settings = settings
        self.collect_failures = collect_failures
        self.failures: List[Dict[str, Any]] = []
        self.partial_artifacts: Optional[RunArtifacts] = None

        self._tool_objects: Dict[str, DecoratedFunctionTool] = {
            "prices": build_prices_tool(),
            "news": build_news_tool(news_token=settings.news_token),
            "edgar": build_edgar_tool(sec_user_agent=settings.sec_user_agent),
            "ratios": build_ratios_tool(),
            "peers": build_peers_tool(),
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
            try:
                payload = self._gather_for_ticker(ticker)
            except ToolExecutionError:
                if self.collect_failures:
                    continue
                raise
            except Exception as exc:
                if self.collect_failures:
                    self.failures.append(
                        {
                            "ticker": ticker,
                            "stage": "analysis",
                            "error": str(exc),
                        }
                    )
                    continue
                raise

            payload["focus"] = focus
            ticker_payloads.append(payload)
            markdown_sections.append(self._format_markdown_for_ticker(payload))

        json_payload = {
            "run_id": run_id,
            "generated_at": generated_at.isoformat().replace("+00:00", "Z"),
            "tickers": ticker_payloads,
        }
        markdown = "\n\n".join(markdown_sections).strip() + "\n"
        artifacts = RunArtifacts(json_payload=json_payload, markdown=markdown, output_dir=output_dir)

        if self.collect_failures and self.failures:
            self.partial_artifacts = artifacts
            raise RuntimeError(self._format_failures())

        return artifacts

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
        edgar_source_url = cast(Optional[str], edgar_data.get("source_url") or edgar_data.get("url"))

        edgar_error = edgar_data.get("error")
        if edgar_error and self.collect_failures:
            self.failures.append(
                {
                    "ticker": ticker,
                    "stage": "tool",
                    "tool": "edgar",
                    "error": edgar_error,
                }
            )

        citations.append(
            {
                "ticker": ticker,
                "title": "Management discussion and analysis excerpt" + (" (not available)" if edgar_error else ""),
                "url": edgar_source_url,
                "source": "SEC EDGAR",
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
            raise RuntimeError("Configured agent does not support structured outputs; cannot generate analysis.")

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
        try:
            result = structured_fn(ResearchSections, prompt=prompt)
        except Exception as exc:
            raise RuntimeError("Structured generation failed") from exc

        if isinstance(result, ResearchSections):
            return result

        try:
            return ResearchSections.model_validate(result)
        except ValidationError as exc:
            raise RuntimeError("Structured generation returned invalid payload") from exc

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
        try:
            payload = extract_json_content(result)
        except Exception as exc:
            if self.collect_failures:
                self.failures.append(
                    {
                        "ticker": kwargs.get("ticker"),
                        "stage": "tool",
                        "tool": name,
                        "error": str(exc),
                    }
                )
                raise ToolExecutionError(str(exc)) from exc
            raise

        if isinstance(payload, Mapping):
            return dict(payload)

        raise RuntimeError(f"Tool '{name}' did not return JSON content: {payload}")

    def _format_failures(self) -> str:
        lines = ["Live run encountered the following issues:"]
        for idx, failure in enumerate(self.failures, start=1):
            parts = [f"[{idx}]", failure.get("stage", "unknown").upper()]
            if failure.get("ticker"):
                parts.append(f"ticker={failure['ticker']}")
            if failure.get("tool"):
                parts.append(f"tool={failure['tool']}")
            message = failure.get("error", "Unknown error")
            lines.append(f"{' '.join(parts)} -> {message}")
        return "\n".join(lines)

    def failure_report(self) -> str:
        return self._format_failures() if self.failures else ""
