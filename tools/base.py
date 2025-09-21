"""Base utilities shared by tool implementations."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping


ToolResult = dict[str, Any]


class BaseTool:
    """Provide helpers for loading fixture payloads and resolving paths."""

    def __init__(self, *, use_fixtures: bool, fixtures_path: Path) -> None:
        self.use_fixtures = use_fixtures
        self.fixtures_path = fixtures_path

    def _fixture_path(self, name: str) -> Path:
        path = self.fixtures_path / name
        if not path.exists():
            raise FileNotFoundError(f"Fixture '{name}' not found under {self.fixtures_path}.")
        return path

    def load_fixture_json(self, name: str) -> Any:
        path = self._fixture_path(name)
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def load_fixture_text(self, name: str) -> str:
        path = self._fixture_path(name)
        return path.read_text(encoding="utf-8")


def json_tool_response(payload: Any) -> ToolResult:
    """Return a Strands tool response containing structured JSON content."""

    return {
        "status": "success",
        "content": [{"json": payload}],
    }


def extract_json_content(tool_result: Mapping[str, Any], *, default: Any | None = None) -> Any:
    """Extract the first JSON block from a Strands tool result."""

    content: Iterable[Mapping[str, Any]] = tool_result.get("content", [])  # type: ignore[assignment]
    for block in content:
        if isinstance(block, Mapping) and "json" in block:
            return block["json"]
        if isinstance(block, Mapping) and "text" in block:
            text = block["text"]
            try:
                return json.loads(text)
            except (TypeError, ValueError):
                return text
    if default is not None:
        return default
    raise ValueError("Tool result did not include JSON or text content.")
