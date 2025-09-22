"""Shared helpers for Strands tool implementations."""
from __future__ import annotations

import json
from typing import Any, Iterable, Mapping


ToolResult = dict[str, Any]


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
