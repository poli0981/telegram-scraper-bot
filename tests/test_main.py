"""Smoke tests for bot.main.build_application.

We don't run the actual application (would need real network) but verify it
constructs without error, including the PicklePersistence wiring added in 3c.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import User

from bot.config import Config
from bot.main import build_application


def _stub_bot_methods(app) -> AsyncMock:
    """Replace network-touching ExtBot methods with AsyncMock.

    Returns the get_me mock so tests can assert on it. ExtBot is frozen, so
    we go through ``object.__setattr__`` to inject.
    """
    fake_me = MagicMock(spec=User)
    fake_me.username = "test_bot"
    fake_me.id = 777
    fake_me.first_name = "Test"
    get_me_mock = AsyncMock(return_value=fake_me)
    object.__setattr__(app.bot, "get_me", get_me_mock)
    object.__setattr__(app.bot, "set_my_commands", AsyncMock())
    object.__setattr__(app.bot, "set_my_short_description", AsyncMock())
    object.__setattr__(app.bot, "set_my_description", AsyncMock())
    return get_me_mock


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(
        bot_token="fake-token",
        gh_pat="fake-pat",
        allowed_user_ids=frozenset({42}),
        steam_repo="user/steam",
        itch_repo="user/itch",
        persistence_path=tmp_path / "state" / "bot.pickle",
    )


class TestBuildApplication:
    def test_constructs_without_error(self, config: Config) -> None:
        app = build_application(config)
        assert app is not None
        # Note: config is NOT in bot_data at build time — it's injected via
        # closure into post_init, which runs after PicklePersistence loads.
        # Setting it here would be silently overwritten on first run.
        assert "config" not in app.bot_data

    def test_creates_persistence_directory(self, config: Config) -> None:
        # Parent dir doesn't exist yet
        assert not config.persistence_path.parent.exists()

        build_application(config)

        # build_application creates it
        assert config.persistence_path.parent.is_dir()

    def test_persistence_is_attached(self, config: Config) -> None:
        app = build_application(config)
        # The Application has a persistence object, configured to our path
        assert app.persistence is not None
        # PicklePersistence stores filepath as a Path attribute
        assert Path(app.persistence.filepath) == config.persistence_path

    def test_error_handler_registered(self, config: Config) -> None:
        app = build_application(config)
        # PTB stores error handlers on Application.error_handlers
        assert len(app.error_handlers) >= 1

    def test_conversation_handler_registered(self, config: Config) -> None:
        app = build_application(config)
        # At least one handler in the default group
        assert len(app.handlers.get(0, [])) >= 1

    async def test_post_init_populates_bot_data(self, config: Config) -> None:
        """Regression test: PicklePersistence overwrites bot_data on post_init.

        This caught a real bug where setting bot_data["config"] inside
        build_application gave a KeyError on first run because the empty
        pickle file overwrote it. The fix: populate bot_data INSIDE post_init
        (via closure over config), not in build_application.
        """
        from bot.dispatcher import Dispatcher
        from bot.gates import ConcurrencyLock, RateLimit

        app = build_application(config)
        _stub_bot_methods(app)
        # Simulate PTB's lifecycle: post_init runs after persistence load.
        # We invoke it directly to verify the closure populates bot_data.
        post_init = app.post_init
        assert post_init is not None
        await post_init(app)

        try:
            assert app.bot_data["config"] is config
            assert isinstance(app.bot_data["dispatcher"], Dispatcher)
            assert isinstance(app.bot_data["lock"], ConcurrencyLock)
            assert isinstance(app.bot_data["rate_limit"], RateLimit)
            # Phase-6: pending_quick + last_dispatch dicts exist
            assert app.bot_data["pending_quick"] == {}
            assert app.bot_data["last_dispatch"] == {}
        finally:
            # Clean up the httpx client we just created
            client = app.bot_data.get("http_client")
            if client is not None:
                await client.aclose()

    async def test_post_init_calls_get_me(self, config: Config) -> None:
        """Token sanity check: post_init must hit /getMe so bad tokens fail loud."""
        app = build_application(config)
        get_me_mock = _stub_bot_methods(app)

        await app.post_init(app)

        try:
            get_me_mock.assert_awaited_once()
        finally:
            client = app.bot_data.get("http_client")
            if client is not None:
                await client.aclose()

    async def test_post_init_raises_when_get_me_fails(self, config: Config) -> None:
        """Bad BOT_TOKEN: getMe raises, post_init must propagate (don't run zombie bot)."""
        app = build_application(config)
        _stub_bot_methods(app)
        # Override get_me to fail
        object.__setattr__(app.bot, "get_me", AsyncMock(side_effect=RuntimeError("Unauthorized")))

        with pytest.raises(RuntimeError, match="Unauthorized"):
            await app.post_init(app)

        client = app.bot_data.get("http_client")
        if client is not None:
            await client.aclose()
