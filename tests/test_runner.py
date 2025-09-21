from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import runner


def test_runner_generates_expected_artifacts(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_FIXTURES", "1")
    monkeypatch.setenv("RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("FIXTURES_PATH", str(PROJECT_ROOT / "fixtures"))

    artifacts = runner.run(["PLTR"], focus="AI adoption in defense")

    json_path = artifacts.output_dir / "brief.json"
    md_path = artifacts.output_dir / "brief.md"

    assert json_path.exists()
    assert md_path.exists()

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["tickers"][0]["ticker"] == "PLTR"
    sections = payload["tickers"][0]["sections"]
    for key in ["overview", "moat", "performance", "catalysts", "risks", "valuation"]:
        assert key in sections
        assert sections[key]

    citations = payload["tickers"][0]["citations"]
    assert len(citations) >= 3

    markdown = md_path.read_text(encoding="utf-8")
    for heading in ["### Overview", "### Moat", "### Performance", "### Catalysts", "### Risks", "### Valuation", "### Sources"]:
        assert heading in markdown
