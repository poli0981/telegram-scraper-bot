"""Configuration loader.

Loads from environment (with .env support via python-dotenv).
All access goes through `Config.load()` — no scattered os.environ calls.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


class ConfigError(Exception):
    """Raised when required env vars are missing or malformed."""


@dataclass(frozen=True, slots=True)
class Config:
    """Immutable runtime config. Build via `Config.load()`."""

    # Required
    bot_token: str
    gh_pat: str
    allowed_user_ids: frozenset[int]
    steam_repo: str
    itch_repo: str

    # Optional with defaults
    workflow_file: str = "bot-ingest.yml"
    workflow_ref: str = "main"
    persistence_path: Path = field(default_factory=lambda: Path("./state/bot.pickle"))
    rate_limit_user_max: int = 3
    rate_limit_user_window: int = 1800
    rate_limit_global_max: int = 10
    rate_limit_global_window: int = 3600
    max_links_per_dispatch: int = 100
    log_level: str = "INFO"
    log_format: str = "text"  # "text" or "json"
    git_sha: str = "dev"  # injected at Docker build via ARG GIT_SHA

    @classmethod
    def load(cls, env_file: str | os.PathLike | None = ".env") -> Config:
        """Load + validate. Raises ConfigError on missing/malformed values."""
        if env_file:
            load_dotenv(env_file, override=False)

        bot_token = _required("BOT_TOKEN")
        gh_pat = _required("GH_PAT")
        steam_repo = _required("STEAM_REPO")
        itch_repo = _required("ITCH_REPO")

        # Parse comma-separated user IDs
        raw_users = _required("ALLOWED_USER_IDS")
        try:
            user_ids = frozenset(int(x.strip()) for x in raw_users.split(",") if x.strip())
        except ValueError as e:
            raise ConfigError(f"ALLOWED_USER_IDS must be comma-separated integers: {e}") from e
        if not user_ids:
            raise ConfigError("ALLOWED_USER_IDS must contain at least one ID")

        return cls(
            bot_token=bot_token,
            gh_pat=gh_pat,
            allowed_user_ids=user_ids,
            steam_repo=steam_repo,
            itch_repo=itch_repo,
            workflow_file=os.environ.get("WORKFLOW_FILE", "bot-ingest.yml"),
            workflow_ref=os.environ.get("WORKFLOW_REF", "main"),
            persistence_path=Path(os.environ.get("PERSISTENCE_PATH", "./state/bot.pickle")),
            rate_limit_user_max=_int_env("RATE_LIMIT_USER_MAX", 3),
            rate_limit_user_window=_int_env("RATE_LIMIT_USER_WINDOW", 1800),
            rate_limit_global_max=_int_env("RATE_LIMIT_GLOBAL_MAX", 10),
            rate_limit_global_window=_int_env("RATE_LIMIT_GLOBAL_WINDOW", 3600),
            max_links_per_dispatch=_int_env("MAX_LINKS_PER_DISPATCH", 100),
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
            log_format=os.environ.get("LOG_FORMAT", "text").lower(),
            git_sha=os.environ.get("BOT_GIT_SHA", "dev"),
        )

    def setup_logging(self) -> None:
        """Configure root logger. Idempotent."""
        if self.log_format == "json":
            handler = logging.StreamHandler()
            handler.setFormatter(_make_json_formatter())
            root = logging.getLogger()
            root.handlers.clear()
            root.addHandler(handler)
            root.setLevel(self.log_level)
        else:
            logging.basicConfig(
                level=self.log_level,
                format="%(asctime)s %(levelname)-8s %(name)s :: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
                force=True,
            )
        # PTB is chatty at DEBUG; quiet it unless we explicitly want it
        if self.log_level != "DEBUG":
            logging.getLogger("httpx").setLevel(logging.WARNING)
            logging.getLogger("telegram").setLevel(logging.INFO)
            logging.getLogger("apscheduler").setLevel(logging.WARNING)


# ─── helpers ────────────────────────────────────────────────────


def _make_json_formatter() -> logging.Formatter:
    """Build a JSON log formatter, falling back to text if dependency missing.

    python-json-logger is in requirements.txt; if it's missing (e.g. dev install
    skipped), we degrade to plain text rather than crash.
    """
    try:
        from pythonjsonlogger.jsonlogger import JsonFormatter

        return JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    except ImportError:
        return logging.Formatter(
            "%(asctime)s %(levelname)-8s %(name)s :: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )


def _required(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        raise ConfigError(f"Required env var not set: {name}")
    return val


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as e:
        raise ConfigError(f"{name} must be an integer, got: {raw!r}") from e
