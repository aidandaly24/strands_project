"""SEC EDGAR helper to retrieve filing excerpts."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional

try:  # pragma: no cover - optional dependency for live mode
    import httpx
except Exception:  # pragma: no cover - offline fallback
    httpx = None

from bs4 import BeautifulSoup
from strands.tools import tool
from strands.tools.decorator import DecoratedFunctionTool

from .base import json_tool_response


SEC_TICKER_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data/{cik_no_zeros}/{accession_no_dashes}/{doc}"

DEFAULT_FORMS: tuple[str, ...] = ("10-K", "10-Q", "20-F", "40-F", "F-10", "6-K")
DEFAULT_SECTION_PATTERNS: tuple[str, ...] = (
    r"Item\s+7\.",
    r"Item\s+5\.\s+Management's Discussion and Analysis",
    r"MANAGEMENT['\"]?S\s+DISCUSSION\s+AND\s+ANALYSIS",
    r"Management.?s\s+Discussion\s+and\s+Analysis",
)


def _ensure_http_client() -> None:
    if httpx is None:  # pragma: no cover - dependency enforcement
        raise RuntimeError("httpx is required for live EDGAR calls but is not installed.")


def _headers(sec_user_agent: str) -> Dict[str, str]:
    return {"User-Agent": sec_user_agent, "Accept-Encoding": "gzip, deflate"}


def _throttled_get(url: str, *, headers: Dict[str, str], params: Optional[Dict[str, str]] = None, retries: int = 3) -> httpx.Response:
    last_exc: Optional[Exception] = None
    for attempt in range(retries):
        try:
            response = httpx.get(url, params=params, headers=headers, timeout=30)
            if response.status_code in {429, 500, 502, 503, 504}:
                time.sleep(0.5 * (2 ** attempt))
                continue
            response.raise_for_status()
            time.sleep(0.25)
            return response
        except Exception as exc:  # pragma: no cover - network specific
            last_exc = exc
            time.sleep(0.5 * (2 ** attempt))
    if last_exc:
        raise last_exc
    raise RuntimeError(f"Request to {url} failed without exception detail")


def _load_ticker_map(headers: Dict[str, str], cache_path: Path) -> Dict[str, str]:
    if cache_path.exists() and time.time() - cache_path.stat().st_mtime < 7 * 24 * 3600:
        data = json.loads(cache_path.read_text())
    else:
        response = _throttled_get(SEC_TICKER_URL, headers=headers)
        data = response.json()
        cache_path.write_text(json.dumps(data))

    mapping: Dict[str, str] = {}
    for payload in data.values():
        cik = str(payload["cik_str"]).zfill(10)
        mapping[payload["ticker"].upper()] = cik
    return mapping


def _recent_filing_metadata(
    cik: str,
    *,
    forms: Iterable[str],
    headers: Dict[str, str],
    limit: int = 5,
) -> List[Dict[str, str]]:
    response = _throttled_get(SEC_SUBMISSIONS_URL.format(cik=cik), headers=headers)
    data = response.json()

    filings = data.get("filings", {}).get("recent", {})
    form_list = filings.get("form", [])
    accession_numbers = filings.get("accessionNumber", [])
    primary_documents = filings.get("primaryDocument", [])
    filed_dates = filings.get("filingDate", [])

    target_forms = {form.upper() for form in forms}
    results: List[Dict[str, str]] = []
    for form, accession, primary_doc, filed_on in zip(form_list, accession_numbers, primary_documents, filed_dates):
        if form.upper() not in target_forms:
            continue
        if not primary_doc.lower().endswith((".htm", ".html")):
            continue
        accession_no_dashes = accession.replace("-", "")
        cik_no_zeros = cik.lstrip("0") or "0"
        url = SEC_ARCHIVES_URL.format(
            cik_no_zeros=cik_no_zeros,
            accession_no_dashes=accession_no_dashes,
            doc=primary_doc,
        )
        results.append(
            {
                "form": form,
                "accession": accession,
                "filing_date": filed_on,
                "primary_document": primary_doc,
                "url": url,
            }
        )
        if len(results) >= limit:
            break
    return results


def _extract_section(html: str, patterns: Iterable[str], *, max_chars: int = 20000) -> str:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n")
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        start = match.start()
        end = min(len(text), start + max_chars)
        snippet = text[start:end]
        snippet = re.sub(r"\s+", " ", snippet)
        return snippet.strip()
    raise ValueError("Requested filing section not found in document.")


class EdgarTool:
    """Fetch filing sections from live SEC data using the submissions API."""

    def __init__(self, *, sec_user_agent: str | None) -> None:
        self.sec_user_agent = sec_user_agent
        self.cache_dir = Path(".sec_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch(self, ticker: str) -> Dict[str, str]:
        ticker = ticker.upper()
        if not self.sec_user_agent or "@" not in self.sec_user_agent:
            raise RuntimeError("SEC_UA must be set with a valid contact email for EDGAR access.")

        _ensure_http_client()
        headers = _headers(self.sec_user_agent)
        ticker_map = _load_ticker_map(headers, self.cache_dir / "company_tickers.json")
        cik = ticker_map.get(ticker)
        if not cik:
            raise ValueError(f"Ticker '{ticker}' not found in SEC company list.")

        metadata_candidates = _recent_filing_metadata(cik, forms=DEFAULT_FORMS, headers=headers)
        if not metadata_candidates:
            raise RuntimeError("Unable to locate a recent filing with an HTML primary document for this ticker.")

        extraction_errors: List[str] = []
        for metadata in metadata_candidates:
            filing_response = _throttled_get(metadata["url"], headers=headers)
            try:
                section_text = _extract_section(filing_response.text, DEFAULT_SECTION_PATTERNS)
            except ValueError as exc:
                extraction_errors.append(f"{metadata['form']} {metadata['accession']}: {exc}")
                continue

            return {
                "ticker": ticker,
                "section": section_text,
                "source_url": metadata["url"],
                "filed_on": metadata["filing_date"],
                "filing_type": metadata["form"],
                "accession": metadata["accession"],
            }

        fallback = metadata_candidates[0]
        return {
            "ticker": ticker,
            "section": "",
            "source_url": fallback["url"],
            "filed_on": fallback["filing_date"],
            "filing_type": fallback["form"],
            "accession": fallback["accession"],
            "error": "; ".join(extraction_errors) or "Requested filing section not found",
        }


def build_edgar_tool(*, sec_user_agent: str | None) -> DecoratedFunctionTool:
    """Create a Strands tool for fetching SEC MD&A excerpts."""

    backend = EdgarTool(sec_user_agent=sec_user_agent)

    @tool(name="edgar", description="Fetch Item 7 management commentary for a ticker.")
    def edgar_tool(ticker: str) -> Dict[str, str]:
        payload = backend.fetch(ticker)
        return json_tool_response(payload)

    return edgar_tool
