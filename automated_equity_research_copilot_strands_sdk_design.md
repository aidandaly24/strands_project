# Automated Equity Research Copilot — Strands SDK Design

**Owner:** Aidan / AI Platform  
**Status:** Draft v3 (2025-09-21, Local-first)  
**Goal:** Build a local Strands agent runner that produces defensible, citation-backed equity research briefs (JSON + Markdown). Start with a simple `runner.py` script, not a public API. Extend later into a FastAPI service if needed.

---

## 0) Project Overview

This project is an **Automated Equity Research Copilot** built on the Strands SDK. The aim is to generate equity research briefs with citations from SEC filings, Yahoo Finance, and news sources. The agent uses an OpenAI model to orchestrate a small set of Python tools, producing both JSON (for structured data) and Markdown (for human-readable notes).

The first deliverable is **local-only**: a Python script (`runner.py`) that accepts tickers, runs the agent, and saves outputs to disk. It requires no client/server setup, but includes a clear path to evolve into a FastAPI service later. The MVP stack is free to run — OpenAI models, Yahoo Finance (`yfinance`), SEC filings (with a user agent string), and NewsAPI’s free tier (or GDELT fallback).

---

## 1) Objectives

**Primary**
- Generate structured JSON and Markdown briefs for 1–3 tickers.
- Run locally via `runner.py` with minimal dependencies.
- Save results (JSON + Markdown) into a timestamped folder under `runs/`.

**Secondary**
- Support comparative analysis across tickers.
- Provide fixtures mode for offline testing.
- Later extend to FastAPI for API clients.

**Non-goals (v1)**
- Public HTTP API.
- Executing trades or giving individualized advice.
- Real-time low-latency streaming.

---

## 2) User Stories

- *As a developer*, I run `python runner.py` and get research briefs for given tickers saved to disk.
- *As an investor*, I view Markdown notes with metrics, catalysts, risks, and citations.
- *As a PM*, I want reproducibility: runs are versioned and saved under `runs/<timestamp>/`.

---

## 3) System Overview

### 3.1 High-level Flow

```
 runner.py  ──> Strands Agent (system prompt + tools)
                 ├─ EDGAR Tool (filing sections)
                 ├─ Prices Tool (Yahoo Finance)
                 ├─ Ratios Tool (SMA/RSI)
                 ├─ Peers Tool (static peer lists)
                 ├─ News Tool (NewsAPI or GDELT)
                 └─ Sentiment Tool
                 ↓
         JSON + Markdown outputs → saved to runs/<timestamp>/
```

### 3.2 Data Flow
1) Runner script loads `.env`.  
2) Agent orchestrates tools (filings, prices, news, peers, ratios).  
3) Output is split into JSON + Markdown.  
4) Both are saved to disk. Markdown is printed to console.

---

## 4) Environment Variables

| Var | Required | Example |
|---|---|---|
| `OPENAI_API_KEY` | yes | `sk-...` |
| `SEC_UA` | yes | `Aidan Daly (aidan@example.com)` |
| `NEWS_TOKEN` | optional | `newsapi_abc123` |
| `ENV` | optional | `dev` |
| `LOG_LEVEL` | optional | `INFO` |

`.env` example:
```ini
OPENAI_API_KEY=sk-...
SEC_UA="Aidan Daly (aidan@example.com)"
NEWS_TOKEN=newsapi_abcdef12345
ENV=dev
LOG_LEVEL=INFO
```

---

## 5) Local Runner

**runner.py** responsibilities:
- Load env vars.
- Build Strands agent with tools.
- Construct query (tickers + focus).
- Run agent.
- Extract JSON block + Markdown from model output.
- Print Markdown to console.
- Save both JSON + Markdown to `runs/<timestamp>/`.

Outputs:
```
runs/20250921_153000/
  brief.json
  brief.md
```

---

## 6) Tools (Free Stack)

- **prices.py:** fetch price history + key stats using `yfinance`.  
- **news.py:** fetch headlines using NewsAPI (with `NEWS_TOKEN`); fallback to GDELT if missing. Includes `naive_sentiment` tool.  
- **edgar.py:** fetch SEC filing sections with `SEC_UA` header.  
- **ratios.py:** compute SMA20, SMA50, RSI14, latest close.  
- **peers.py:** return small hard-coded peer sets.  

---

## 7) Fixtures & Offline Mode

Directory: `fixtures/`
```
fixtures/
  news_PLTR.json
  prices_PLTR.json
  filing_ORCL_item7.html
```

A global flag `USE_FIXTURES` allows tools to load canned payloads instead of live calls for development without internet access.

---

## 8) Acceptance Criteria

- Running `runner.py` with `tickers=["PLTR"]` prints Markdown and saves JSON/MD to disk.
- JSON contains metrics, peers, sentiment, and ≥2 citations.
- Markdown has structured sections: Overview, Moat, Performance, Catalysts, Risks, Valuation.
- Run completes in < 8s p95 on free stack.

---

## 9) Future Extension (API)

Later iterations can:
- Wrap the agent in a FastAPI service.
- Reuse schemas, settings, and tools.
- Expose `/v1/research` endpoint.

---

## 10) Runbook

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python runner.py
```

---

## 11) Testing

- Unit: verify tools parse Yahoo/NewsAPI/SEC payloads correctly.  
- Contract: ensure runner saves both `.json` and `.md` files.  
- Fixture mode: run offline against canned data.  
- Regression: diff JSON output fields for stability.

---

## 12) Rollout
- v0.1: Local runner with PLTR, outputs JSON + Markdown.  
- v0.2: Add comparison for multiple tickers.  
- v0.3: Fixtures + offline toggle.  
- v1.0: FastAPI service for external clients.

---

## 13) Backlog
- Better symbol→CIK mapping for SEC filings.  
- Improve sentiment analysis with LLM classifier.  
- Richer ratios (ATR, drawdowns, 52w high/low).  
- Critic sub-agent to verify citations.  
- Extend peers tool with industry DB/API.

