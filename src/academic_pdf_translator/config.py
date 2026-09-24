"""Configuration from environment; credentials never enter PIR or exported files."""

import math
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class Settings:
    model: str = ""
    api_base_url: str = "https://api.openai.com/v1"
    api_key: str = field(default="", repr=False)
    target_language: str = "Simplified Chinese"
    timeout: float = 90
    max_retries: int = 2
    context_chars: int = 6000
    max_current_chars: int = 16000
    cache_dir: Path = Path(".apt-cache/translations")

    def __post_init__(self) -> None:
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError("APT_TIMEOUT must be a positive finite number")
        if not 0 <= self.max_retries <= 5:
            raise ValueError("APT_MAX_RETRIES must be between 0 and 5")
        if self.context_chars < 0 or self.max_current_chars <= 0:
            raise ValueError("Context budget must be nonnegative and current-block limit positive")

    @classmethod
    def from_env(cls) -> "Settings":
        # Installed console commands must read the user's working directory,
        # not search the package installation location for credentials.
        load_dotenv(dotenv_path=Path.cwd() / ".env")
        return cls(
            model=os.getenv("APT_MODEL", ""),
            api_base_url=os.getenv("APT_API_BASE_URL", "https://api.openai.com/v1"),
            api_key=os.getenv("APT_API_KEY", "") or os.getenv("OPENAI_API_KEY", ""),
            target_language=os.getenv("APT_TARGET_LANGUAGE", "Simplified Chinese"),
            timeout=float(os.getenv("APT_TIMEOUT", "90")),
            max_retries=int(os.getenv("APT_MAX_RETRIES", "2")),
            context_chars=int(os.getenv("APT_CONTEXT_CHARS", "6000")),
            max_current_chars=int(os.getenv("APT_MAX_CURRENT_CHARS", "16000")),
            cache_dir=Path(os.getenv("APT_CACHE_DIR", ".apt-cache/translations")),
        )
