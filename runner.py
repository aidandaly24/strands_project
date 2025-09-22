"""Entry point for the automated equity research copilot."""
from __future__ import annotations

import argparse
import json
import os
from typing import Iterable, Optional

from dotenv import load_dotenv
from strands.models.bedrock import BedrockModel
from strands.models.openai import OpenAIModel

from agent import ResearchAgent, RunArtifacts
from settings import Settings


load_dotenv()


def _create_model(settings: Settings) -> object:
    """Initialise a Strands model using OpenAI or Bedrock credentials."""

    api_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY")
    if api_key:
        model_id = os.getenv("OPENAI_MODEL_ID", "gpt-4o-mini")
        return OpenAIModel(
            client_args={"api_key": api_key},
            model_id=model_id,
            params={"max_tokens": 2000, "temperature": 0.2},
        )

    bedrock_model_id = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    has_aws_credentials = any(
        os.getenv(name)
        for name in (
            "AWS_PROFILE",
            "AWS_ACCESS_KEY_ID",
            "AWS_ROLE_ARN",
            "AWS_WEB_IDENTITY_TOKEN_FILE",
        )
    )
    if not has_aws_credentials:
        raise RuntimeError("Provide either OPENAI_API_KEY or AWS credentials to run the research agent.")

    model_args: dict[str, object] = {
        "model_id": bedrock_model_id,
        "max_tokens": 2000,
        "temperature": 0.2,
    }
    if region:
        model_args["region_name"] = region

    return BedrockModel(**model_args)


def run(
    tickers: Iterable[str], *, focus: Optional[str] = None, collect_failures: bool = False
) -> RunArtifacts:
    """Run the research agent for the provided tickers and persist artifacts."""
    settings = Settings.load()
    settings.ensure_directories()

    model = _create_model(settings)

    agent = ResearchAgent(settings, model=model, collect_failures=collect_failures)

    try:
        artifacts = agent.run(tickers, focus=focus)
    except RuntimeError as exc:
        if collect_failures and agent.failures:
            print(agent.failure_report())
            raise SystemExit(1) from exc
        raise

    if collect_failures:
        print("All tools succeeded without errors.")
        return artifacts

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
    parser.add_argument("tickers", nargs="*", help="Ticker symbols to analyse", default=["AMZN"])
    parser.add_argument("--focus", help="Optional focus prompt to steer the brief", default=None)
    parser.add_argument(
        "--test",
        action="store_true",
        help="Collect tool failures without writing output artifacts",
    )
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    tickers = args.tickers or ["AMZN"]
    run(tickers, focus=args.focus, collect_failures=args.test)


if __name__ == "__main__":
    main()
