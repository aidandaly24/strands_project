"""Entry point for the automated equity research copilot."""
from __future__ import annotations

import argparse
import json
from typing import Iterable, Optional

from agent import ResearchAgent, RunArtifacts
from settings import Settings


def run(tickers: Iterable[str], *, focus: Optional[str] = None) -> RunArtifacts:
    """Run the research agent for the provided tickers and persist artifacts."""
    settings = Settings.load()
    settings.ensure_directories()
    agent = ResearchAgent(settings)
    artifacts = agent.run(tickers, focus=focus)

    json_path = artifacts.output_dir / "brief.json"
    md_path = artifacts.output_dir / "brief.md"

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(artifacts.json_payload, handle, indent=2)
    md_path.write_text(artifacts.markdown, encoding="utf-8")

    print(artifacts.markdown)
    print(f"Saved outputs to {artifacts.output_dir}")
    return artifacts


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate equity research briefs using the Strands runner.")
    parser.add_argument("tickers", nargs="*", help="Ticker symbols to analyse", default=["PLTR"])
    parser.add_argument("--focus", help="Optional focus prompt to steer the brief", default=None)
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    tickers = args.tickers or ["PLTR"]
    run(tickers, focus=args.focus)


if __name__ == "__main__":
    main()
