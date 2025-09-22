from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from settings import Settings


def test_fixture_mode_is_disabled(monkeypatch):
    monkeypatch.setenv("USE_FIXTURES", "1")
    with pytest.raises(ValueError, match="Offline fixture mode is disabled"):
        Settings.load()
