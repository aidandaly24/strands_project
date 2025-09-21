# Automated Equity Research Copilot (Local Runner)

This repository contains a local-first prototype of the Strands-powered equity research copilot. The `runner.py` entrypoint loads configuration from environment variables (or a `.env` file), instantiates the official `strands.Agent` runtime with custom research tools, and produces Markdown and JSON briefs for the requested tickers.

## Getting Started

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python runner.py PLTR --focus "AI adoption in defense"
```

Outputs are saved to `runs/<timestamp>/brief.json` and `runs/<timestamp>/brief.md`.

## Environment Variables

| Variable | Description |
| --- | --- |
| `OPENAI_API_KEY` | Optional OpenAI API key for future extensions. |
| `SEC_UA` | SEC EDGAR user agent string. Required for live filing retrieval. |
| `NEWS_TOKEN` | NewsAPI token. Optional if using fixtures. |
| `USE_FIXTURES` | When `true`, load canned data from `fixtures/` (default). |
| `FIXTURES_PATH` | Override path to fixture directory. |
| `RUNS_DIR` | Override output directory for generated briefs. |

A sample `.env` file:

```ini
USE_FIXTURES=true
SEC_UA="Example Contact (dev@example.com)"
NEWS_TOKEN="newsapi-token"
```

## Testing

Run the pytest suite to validate the offline fixture workflow:

```bash
pytest
```
