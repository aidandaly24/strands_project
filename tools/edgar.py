"""SEC EDGAR helper to retrieve filing excerpts."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urljoin
from xml.etree import ElementTree

try:  # pragma: no cover - optional dependency for live mode
    import httpx
except Exception:  # pragma: no cover - offline fallback
    httpx = None

from bs4 import BeautifulSoup, NavigableString
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
        if self.use_fixtures:
            raise RuntimeError("Fixture mode is disabled; live SEC data is required.")
        if not self.sec_user_agent:
            raise RuntimeError("SEC user agent is required for live EDGAR calls.")
        return self._fetch_live_html(ticker)

    def _fetch_live_html(self, ticker: str) -> Dict[str, str]:
        if not self.sec_user_agent:
            raise RuntimeError("SEC user agent is required for live EDGAR calls.")
        if httpx is None:
            raise RuntimeError("httpx is required for live EDGAR calls but is not installed.")
        headers = {"User-Agent": self.sec_user_agent}
        params = {
            "action": "getcompany",
            "CIK": ticker,
            "type": "10-K",
            "count": 1,
            "owner": "exclude",
            "output": "atom",
        }

        with httpx.Client(timeout=15, headers=headers) as client:
            feed_response = client.get("https://www.sec.gov/cgi-bin/browse-edgar", params=params)
            feed_response.raise_for_status()

            index_url, filed_on = self._parse_feed(feed_response.text)
            document_url = self._locate_primary_document(client, index_url)
            document_response = client.get(document_url)
            document_response.raise_for_status()

        section_text = self._extract_item7_section(document_response.text)
        return {
            "ticker": ticker,
            "section": section_text,
            "source_url": document_url,
            "filed_on": filed_on,
            "filing_type": "10-K",
        }

    def _parse_feed(self, feed_xml: str) -> tuple[str, Optional[str]]:
        """Return the filing index URL and filing date from an Atom feed."""

        namespace = {"atom": "http://www.w3.org/2005/Atom"}
        root = ElementTree.fromstring(feed_xml)
        entry = root.find("atom:entry", namespace)
        if entry is None:
            raise ValueError("No 10-K filings found in SEC feed.")

        link_element = entry.find("atom:link", namespace)
        if link_element is None or "href" not in link_element.attrib:
            raise ValueError("SEC feed entry did not include a filing index link.")

        summary = entry.findtext("atom:summary", default="", namespaces=namespace)
        filed_on = self._extract_filed_date(summary)
        if filed_on is None:
            updated = entry.findtext("atom:updated", default="", namespaces=namespace)
            filed_on = self._extract_updated_date(updated)

        return link_element.attrib["href"], filed_on

    @staticmethod
    def _extract_filed_date(summary_html: str) -> Optional[str]:
        """Extract the filed-on date from the summary block, if present."""

        if not summary_html:
            return None
        match = re.search(r"Filed:\s*(\d{4}-\d{2}-\d{2})", summary_html)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def _extract_updated_date(value: str) -> Optional[str]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            return None

    def _locate_primary_document(self, client: httpx.Client, index_url: str) -> str:
        """Find the primary 10-K document URL from the filing index page."""

        response = client.get(index_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        table = soup.find("table", class_="tableFile", summary="Document Format Files")
        if table is None:
            raise ValueError("Could not locate document table on the filing index page.")

        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if not cells or len(cells) < 2:
                continue
            form_type = cells[1].get_text(strip=True).upper()
            if form_type != "10-K":
                continue
            link = row.find("a")
            if link and link.get("href"):
                href = link["href"]
                if href.startswith("/ix?doc="):
                    href = href.split("=", 1)[1]
                return urljoin(index_url, href)

        first_link = table.find("a")
        if first_link and first_link.get("href"):
            href = first_link["href"]
            if href.startswith("/ix?doc="):
                href = href.split("=", 1)[1]
            return urljoin(index_url, href)
        raise ValueError("Unable to resolve primary 10-K document link.")

    @staticmethod
    def _extract_item7_section(document_html: str) -> str:
        """Extract Item 7 text from a 10-K HTML document."""

        soup = BeautifulSoup(document_html, "html.parser")
        heading = None
        for candidate in soup.find_all(string=re.compile(r"Item\s+7\.", re.IGNORECASE)):
            candidate_text = candidate.strip()
            if not candidate_text:
                continue
            style = (candidate.parent.get("style") or "").lower() if candidate.parent else ""
            if "font-weight:700" in style or candidate_text.isupper():
                heading = candidate.parent
                break
        if heading is None:
            matches = soup.find_all(string=re.compile(r"Item\s+7\.", re.IGNORECASE))
            if matches:
                heading = matches[-1].parent
        if heading is None:
            return "Unable to extract Item 7 management discussion from the filing."

        container = heading.find_parent(["div", "p", "section", "article", "body"]) or heading
        chunks: list[str] = []
        for sibling in container.next_siblings:
            if isinstance(sibling, NavigableString):
                text_block = str(sibling).strip()
            else:
                text_block = sibling.get_text(" ", strip=True)
            if not text_block:
                continue
            if re.search(r"Item\s+7A\.|Item\s+8\.", text_block, re.IGNORECASE):
                break
            chunks.append(text_block)
            if len(" ".join(chunks)) >= 4000:
                break

        if not chunks:
            return "Unable to extract Item 7 management discussion from the filing."

        normalized = re.sub(r"\s+", " ", " ".join(chunks))
        return normalized[:4000].strip()


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
