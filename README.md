# Automated Equity Research Copilot

This repository contains a live-data Strands-powered equity research copilot. The `runner.py` entrypoint loads configuration from environment variables (or a `.env` file), instantiates the official `strands.Agent` runtime with custom research tools that call OpenAI (or AWS Bedrock), Yahoo Finance, NewsAPI/GDELT, and the SEC submissions API, then produces Markdown and JSON briefs for the requested tickers.

## How the Agent Works

The `ResearchAgent` wires Strands’ structured-output runtime to a handful of live tools:

- **Prices & ratios:** Pulls ~4 months of history from Yahoo Finance (`yfinance`) and computes SMA20/SMA50/RSI14 on the fly.
- **News feed:** Hits NewsAPI when `NEWS_TOKEN` is set, otherwise falls back to live GDELT headlines (with a naïve sentiment score).
- **SEC filings:** Walks the SEC submissions JSON, downloads the latest HTML 10-K/10-Q/20-F/40-F/F-10/6-K, and extracts Item 7 MD&A (or captures the filing metadata when that section isn’t present).
- **Peer list:** Provides a small static peer map for context.

Those payloads, plus the optional `--focus` hint, are passed to `strands.Agent.structured_output(...)`, which runs against your chosen large-language model (OpenAI by default, AWS Bedrock when AWS creds are present) to generate a fully structured brief. The Markdown and JSON artifacts land in `runs/<timestamp>/`, or you can run `python runner.py <ticker> --test` to collect tool failures without writing files.


## Getting Started

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python runner.py AMZN --focus "AWS's power to keep on bringing strong revenue gains"
# smoke-test live tooling without writing outputs
python runner.py NXE --test
```

Outputs are saved to `runs/<timestamp>/brief.json` and `runs/<timestamp>/brief.md`.

## Environment Variables

| Variable         | Description                                                      |
| ---------------- | ---------------------------------------------------------------- |
| `OPENAI_API_KEY` | OpenAI API key for the analysis model. Required unless Bedrock is used. |
| `OPENAI_MODEL_ID`| Override the default OpenAI model (`gpt-4o-mini`).               |
| `SEC_UA`         | SEC EDGAR user agent string. Required for live filing retrieval. |
| `NEWS_TOKEN`     | NewsAPI token. Optional when falling back to GDELT headlines.    |
| `BEDROCK_MODEL_ID` | Optional Bedrock model id (default `anthropic.claude-3-haiku-20240307-v1:0`). |
| `AWS_REGION`     | AWS region for Bedrock (use with AWS credentials).               |
| `AWS_ACCESS_KEY_ID` / `AWS_PROFILE` / etc. | Provide one of the standard AWS credential mechanisms if you want Bedrock instead of OpenAI. |
| `RUNS_DIR`       | Override output directory for generated briefs.                  |

A sample `.env` file:

```ini
OPENAI_API_KEY="sk-..."  # omit when using AWS Bedrock auth
SEC_UA="Example Contact (dev@example.com)"
NEWS_TOKEN="newsapi-token"  # optional; falls back to GDELT when absent
BEDROCK_MODEL_ID="anthropic.claude-3-haiku-20240307-v1:0"  # optional override
AWS_REGION="us-east-1"  # required when using Bedrock
AWS_PROFILE="bedrock-programmatic"  # or AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY
```

> **Note:** The runner operates in live mode only. If model credentials, the SEC user agent, or external data sources are unavailable, execution aborts instead of falling back to cached data; use `--test` to surface a summary of any failing tools without writing artifacts.

## Example Output

```bash
python3 runner.py AMZN --focus "AWS's revenue growth"
```
----------------------
Output is given in Markdown:
# Research Brief

## AMZN

_Focus: AWS's revenue growth_

### Overview

Amazon.com, Inc. (AMZN) continues to demonstrate resilience in its performance with a current share price of $231.48, reflecting a substantial recovery from its year-to-date low of $204.72. The stock has achieved a 52-week high of $238.24, bolstered by strong earnings growth, which includes a dramatic increase in net income from $13.49 billion in Q2 2024 to $18.16 billion in Q2 2025. The company has effectively leveraged its massive customer base and technological infrastructure to sustain competitive advantages in eCommerce and cloud services, positioning itself favorably for future growth in diversified sectors like artificial intelligence and entertainment.

### Moat

Amazon's competitive moat is characterized by its broad range of services, customer-centric approach, and infrastructural prowess, particularly within its Amazon Web Services (AWS) segment. The latest financial results indicate a significant expansion of operating income, marking a 30% increase year-over-year, which underlines the company’s ability to maintain pricing power without sacrificing profitability. Additionally, the intricacies of the AWS ecosystem, supported by the company's commitment to innovation and continuous investment in advanced technologies, fortify its market presence against emerging competitors like Microsoft (MSFT) and Google (GOOGL).

### Performance

Analyzing recent performance metrics, AMZN has exhibited a stable recovery pattern with an average closing price of $229.14 over the last month, peaking at $238.24. The 14-day Relative Strength Index (RSI) stands at 52.93, indicating a balanced distribution of buy and sell signals, a positive hint for potential upward momentum. Furthermore, with a simple moving average (SMA) of 20-days at $230.84, AMZN remains above both its short-term indicators and well-positioned against broader market performance, suggesting investor confidence despite external market pressures.

### Catalysts

Several catalysts could drive Amazon's growth trajectory, including increased adoption of artificial intelligence and enhancements to its logistics network. Recent commentary from market analysts, including insights from Jim Cramer, suggests optimism regarding AMZN's strategic investment in AI and expansion into new digital services, which are expected to enhance customer engagement and operational efficiency. As the company ramps up efforts in original content production and streaming services, strengthened revenue from these sectors may yield robust earnings growth, compounding shareholder value. Additionally, the ongoing efforts in the AWS segment to offer innovative solutions could further invigorate revenue streams.

### Risks

While AMZN presents numerous growth opportunities, inherent risks persist, primarily stemming from regulatory scrutiny, increased competition, and potential supply chain disruptions. The recent filings noted a significant reliance on international markets, which could expose the company to foreign exchange fluctuations and geopolitical uncertainties. Future operating results could be affected negatively if Amazon fails to manage rising operational costs or if the adoption rates of new technologies do not meet stakeholder expectations, potentially undermining its robust market position.

### Valuation

Amazon's valuation reflects confidence in its long-term growth potential, with a current trading price that suggests steady investor optimism. By comparing valuation metrics, AMZN's price-to-earnings (P/E) ratio situates favorably against peers like Microsoft (MSFT) and Walmart (WMT) as it encapsulates a broader view of market expectations, affirming AMZN's status as a frontrunner in eCommerce and technology services. The company's forward-looking investments, while initially impacting short-term margins, are anticipated to yield favorable long-term returns, thereby enhancing its market valuation.

### Peers

MSFT, GOOGL, WMT

### Sources

1. [Aces High 1976 1008p AMZN WEB-DL H264-GPRS — Rlsbb.to (2025-09-20)](https://post.rlsbb.to/aces-high-1976-1008p-amzn-web-dl-h264-gprs-2/)
2. [Shadows in the Sun 2005 1080p AMZN WEB-DL H264-GPRS — Rlsbb.to (2025-09-20)](https://post.rlsbb.to/shadows-in-the-sun-2005-1080p-amzn-web-dl-h264-gprs/)
3. [TD Cowen Sees Upside in Alphabet (GOOGL) With Rising GenAI Adoption — Yahoo Entertainment (2025-09-20)](https://finance.yahoo.com/news/td-cowen-sees-upside-alphabet-211302489.html)
4. [Aces High 1976 1008p AMZN WEB-DL H264-GPRS — Rlsbb.to (2025-09-20)](https://post.rlsbb.to/aces-high-1976-1008p-amzn-web-dl-h264-gprs/)
5. [Glassland 2014 1080p AMZN WEB-DL H264-GPRS — Rlsbb.to (2025-09-20)](https://post.rlsbb.to/glassland-2014-1080p-amzn-web-dl-h264-gprs/)
6. [“We Were So Worried About” Amazon.com, Inc. (AMZN), Says Jim Cramer — Biztoc.com (2025-09-20)](https://biztoc.com/x/43cbbd936147aeac)
7. [Monsters And Men 2018 1080p AMZN WEB-DL H264-GPRS — Rlsbb.to (2025-09-20)](https://post.rlsbb.to/monsters-and-men-2018-1080p-amzn-web-dl-h264-gprs/)
8. [The Perfect Weapon 2016 1080p AMZN WEB-DL H264-GPRS — Rlsbb.to (2025-09-20)](https://post.rlsbb.to/the-perfect-weapon-2016-1080p-amzn-web-dl-h264-gprs/)
9. [Into The Deep 2022 1080p AMZN WEB-DL H264-GPRS — Rlsbb.to (2025-09-20)](https://post.rlsbb.to/into-the-deep-2022-1080p-amzn-web-dl-h264-gprs/)
10. [“We Were So Worried About” Amazon.com, Inc. (AMZN), Says Jim Cramer — Yahoo Entertainment (2025-09-20)](https://finance.yahoo.com/news/were-worried-amazon-com-inc-190530622.html)
11. [Management discussion and analysis excerpt — SEC EDGAR (2025-08-01)](https://www.sec.gov/Archives/edgar/data/1018724/000101872425000086/amzn-20250630.htm)


## Testing

Run the pytest suite to verify the live-only configuration wiring:

```bash
pytest
```
