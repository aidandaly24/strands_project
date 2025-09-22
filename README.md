# Automated Equity Research Copilot (Local Runner)

This repository contains a local-first prototype of the Strands-powered equity research copilot. The `runner.py` entrypoint loads configuration from environment variables (or a `.env` file), instantiates the official `strands.Agent` runtime with custom research tools, and produces Markdown and JSON briefs for the requested tickers.

## Getting Started

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python runner.py AMZN --focus "AWS's power to keep on bringing strong revenue gains"
```

Outputs are saved to `runs/<timestamp>/brief.json` and `runs/<timestamp>/brief.md`.

## Environment Variables

| Variable         | Description                                                      |
| ---------------- | ---------------------------------------------------------------- |
| `OPENAI_API_KEY` | OpenAI API key for model inference. Optional when using Bedrock. |
| `OPENAI_MODEL_ID`| Override the default OpenAI model (`gpt-4o-mini`).               |
| `SEC_UA`         | SEC EDGAR user agent string. Required for live filing retrieval. |
| `NEWS_TOKEN`     | NewsAPI token. Optional when falling back to GDELT headlines.    |
| `BEDROCK_MODEL_ID` | Optional Bedrock model id (default `anthropic.claude-3-haiku-20240307-v1:0`). |
| `AWS_REGION`     | AWS region for Bedrock when using AWS credentials.               |
| `RUNS_DIR`       | Override output directory for generated briefs.                  |

A sample `.env` file:

```ini
OPENAI_API_KEY="sk-..."  # or omit when using AWS Bedrock
SEC_UA="Example Contact (dev@example.com)"
NEWS_TOKEN="newsapi-token"  # optional, falls back to GDELT when absent
BEDROCK_MODEL_ID="anthropic.claude-3-haiku-20240307-v1:0"  # optional
AWS_REGION="us-east-1"  # required when using Bedrock
```

## Testing

Run the pytest suite to verify configuration guards:

```bash
pytest
```
