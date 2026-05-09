"""Tests for bot.config — env parsing + validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from bot.config import Config, ConfigError


def _set_minimum_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set just enough env to satisfy required fields."""
    monkeypatch.setenv("BOT_TOKEN", "fake-bot-token")
    monkeypatch.setenv("GH_PAT", "fake-pat")
    monkeypatch.setenv("ALLOWED_USER_IDS", "111,222")
    monkeypatch.setenv("STEAM_REPO", "user/steam-repo")
    monkeypatch.setenv("ITCH_REPO", "user/itch-repo")


class TestConfigLoad:
    def test_loads_with_minimum_required_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_minimum_env(monkeypatch)
        cfg = Config.load(env_file=None)
        assert cfg.bot_token == "fake-bot-token"
        assert cfg.gh_pat == "fake-pat"
        assert cfg.allowed_user_ids == frozenset({111, 222})
        assert cfg.steam_repo == "user/steam-repo"
        assert cfg.itch_repo == "user/itch-repo"

    def test_defaults_applied(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_minimum_env(monkeypatch)
        cfg = Config.load(env_file=None)
        assert cfg.workflow_file == "bot-ingest.yml"
        assert cfg.workflow_ref == "main"
        assert cfg.persistence_path == Path("./state/bot.pickle")
        assert cfg.rate_limit_user_max == 3
        assert cfg.rate_limit_user_window == 1800
        assert cfg.rate_limit_global_max == 10
        assert cfg.rate_limit_global_window == 3600
        assert cfg.max_links_per_dispatch == 100
        assert cfg.log_level == "INFO"

    def test_optional_overrides_applied(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_minimum_env(monkeypatch)
        monkeypatch.setenv("WORKFLOW_FILE", "custom.yml")
        monkeypatch.setenv("RATE_LIMIT_USER_MAX", "5")
        monkeypatch.setenv("MAX_LINKS_PER_DISPATCH", "200")
        monkeypatch.setenv("LOG_LEVEL", "debug")
        cfg = Config.load(env_file=None)
        assert cfg.workflow_file == "custom.yml"
        assert cfg.rate_limit_user_max == 5
        assert cfg.max_links_per_dispatch == 200
        assert cfg.log_level == "DEBUG"  # uppercased

    @pytest.mark.parametrize(
        "missing", ["BOT_TOKEN", "GH_PAT", "ALLOWED_USER_IDS", "STEAM_REPO", "ITCH_REPO"]
    )
    def test_raises_on_missing_required(
        self, monkeypatch: pytest.MonkeyPatch, missing: str
    ) -> None:
        _set_minimum_env(monkeypatch)
        monkeypatch.delenv(missing, raising=False)
        with pytest.raises(ConfigError, match=missing):
            Config.load(env_file=None)

    def test_user_ids_must_be_integers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_minimum_env(monkeypatch)
        monkeypatch.setenv("ALLOWED_USER_IDS", "111,abc,222")
        with pytest.raises(ConfigError, match="ALLOWED_USER_IDS"):
            Config.load(env_file=None)

    def test_user_ids_handles_whitespace(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_minimum_env(monkeypatch)
        monkeypatch.setenv("ALLOWED_USER_IDS", " 111 , 222 , ")
        cfg = Config.load(env_file=None)
        assert cfg.allowed_user_ids == frozenset({111, 222})

    def test_user_ids_all_empty_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_minimum_env(monkeypatch)
        monkeypatch.setenv("ALLOWED_USER_IDS", " , , ")
        with pytest.raises(ConfigError, match="at least one"):
            Config.load(env_file=None)

    def test_int_env_invalid_value_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_minimum_env(monkeypatch)
        monkeypatch.setenv("RATE_LIMIT_USER_MAX", "not-a-number")
        with pytest.raises(ConfigError, match="RATE_LIMIT_USER_MAX"):
            Config.load(env_file=None)

    def test_config_is_frozen(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_minimum_env(monkeypatch)
        cfg = Config.load(env_file=None)
        with pytest.raises(AttributeError):
            cfg.bot_token = "changed"  # type: ignore[misc]
