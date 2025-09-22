from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from settings import Settings


def test_settings_is_online_only(monkeypatch):
    monkeypatch.setenv("USE_FIXTURES", "1")
    settings = Settings.load()
    assert not hasattr(settings, "use_fixtures")
