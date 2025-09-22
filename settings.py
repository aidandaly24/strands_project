"""Settings loader for the Strands research runner."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:  # pragma: no cover - optional dependency in offline mode
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - fallback when python-dotenv is absent
    def load_dotenv(*args, **kwargs):
        return False


@dataclass(slots=True)
class Settings:
    """Configuration derived from environment variables or `.env`."""

    openai_api_key: str | None
    sec_user_agent: str | None
    news_token: str | None
    env: str
    log_level: str
    use_fixtures: bool
    fixtures_path: Path
    runs_dir: Path

    @classmethod
    def load(cls) -> "Settings":
        load_dotenv()
        def _get_bool(name: str, default: bool = False) -> bool:
            value = os.getenv(name)
            if value is None:
                return default
            return value.strip().lower() in {"1", "true", "yes", "on"}

        fixtures_path = Path(os.getenv("FIXTURES_PATH", "fixtures"))
        runs_dir = Path(os.getenv("RUNS_DIR", "runs"))

        if _get_bool("USE_FIXTURES", default=False):
            raise ValueError("Offline fixture mode is disabled. Remove USE_FIXTURES from the environment.")

        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            sec_user_agent=os.getenv("SEC_UA"),
            news_token=os.getenv("NEWS_TOKEN"),
            env=os.getenv("ENV", "dev"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            use_fixtures=False,
            fixtures_path=fixtures_path,
            runs_dir=runs_dir,
        )

    def ensure_directories(self) -> None:
        self.fixtures_path.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
