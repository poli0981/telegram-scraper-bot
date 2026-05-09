"""Shared pytest fixtures.

Env isolation autouse fixture, plus the common Application/Config/Dispatcher
mocks reused by handler tests. Fixtures are intentionally generic — individual
tests override gates (RateLimit, ConcurrencyLock) when they need stricter
configurations.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import CallbackQuery, Chat, Message, Update, User
from telegram.ext import Application, ApplicationBuilder, ContextTypes

from bot.config import Config
from bot.dispatcher import DispatchResult
from bot.gates import ConcurrencyLock, RateLimit


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Strip every BOT_*/GH_*/etc env var so tests start from a clean slate.

    Tests that need specific values must set them via monkeypatch.setenv().
    Autouse=True so individual tests don't have to opt in.
    """
    for key in list(os.environ.keys()):
        if key.startswith(
            (
                "BOT_",
                "GH_",
                "ALLOWED_",
                "STEAM_",
                "ITCH_",
                "WORKFLOW_",
                "PERSISTENCE_",
                "RATE_LIMIT_",
                "MAX_LINKS_",
                "LOG_LEVEL",
                "LOG_FORMAT",
            )
        ):
            monkeypatch.delenv(key, raising=False)
    yield


# ─── Common fixtures for handler tests ──────────────────────────


@pytest.fixture
def config() -> Config:
    """Test config with one allowed user (id=42)."""
    return Config(
        bot_token="fake-token",
        gh_pat="fake-pat",
        allowed_user_ids=frozenset({42}),
        steam_repo="user/steam",
        itch_repo="user/itch",
        max_links_per_dispatch=5,  # small for tests
        git_sha="testsha",
    )


@pytest.fixture
def mock_dispatcher() -> AsyncMock:
    """Dispatcher mock — returns success by default."""
    d = AsyncMock()
    d.dispatch = AsyncMock(return_value=DispatchResult(ok=True, repo="user/repo", status_code=204))
    return d


@pytest.fixture
def app(config: Config, mock_dispatcher: AsyncMock) -> Application:
    """PTB Application with bot_data prewired.

    We don't enter the `async with application:` lifecycle since handler unit
    tests don't need polling, the job queue, or bot.initialize() (which would
    try to reach the Telegram API).

    PTB v21's ExtBot inherits from a frozen TelegramObject; we bypass the
    freeze with object.__setattr__ to inject AsyncMock methods.
    """
    application = ApplicationBuilder().token("fake-token").build()
    application.bot_data["config"] = config
    application.bot_data["dispatcher"] = mock_dispatcher
    application.bot_data["lock"] = ConcurrencyLock(stale_after=600.0)
    application.bot_data["rate_limit"] = RateLimit(
        user_max=100, user_window=60.0, global_max=1000, global_window=60.0
    )
    application.bot_data["last_dispatch"] = {}
    application.bot_data["pending_quick"] = {}

    bot = application.bot
    placeholder = MagicMock(spec=Message)
    placeholder.message_id = 9999
    object.__setattr__(bot, "send_message", AsyncMock(return_value=placeholder))
    object.__setattr__(bot, "edit_message_text", AsyncMock())
    return application


# ─── Update / Context builders ──────────────────────────────────


def make_update(
    text: str,
    *,
    user_id: int = 42,
    chat_id: int = 1000,
    message_id: int = 1,
    args: list[str] | None = None,
) -> Update:
    """Construct a minimal Update with a text message.

    Uses MagicMock for Message.reply_text so we can assert on it without
    going through the real Bot API.

    `args` is unused at the Update level — context.args is populated by PTB
    from the message text. Tests that exercise args-bearing commands (/q)
    should set ``context.args`` directly when invoking the handler.
    """
    user = User(id=user_id, first_name="Test", is_bot=False, username="testuser")
    chat = Chat(id=chat_id, type="private")
    message = MagicMock(spec=Message)
    message.text = text
    message.message_id = message_id
    message.chat = chat
    message.from_user = user
    message.reply_text = AsyncMock()
    update = Update(update_id=1, message=message)
    update._effective_user = user
    update._effective_chat = chat
    update._effective_message = message
    return update


def make_callback_update(
    data: str,
    *,
    user_id: int = 42,
    chat_id: int = 1000,
    message_id: int = 5000,
) -> Update:
    """Construct an Update simulating an inline button press.

    `query.answer` and `query.edit_message_text` are AsyncMock so handlers can
    await them. The attached message is a MagicMock so attribute access on
    `query.message.*` is forgiving.
    """
    user = User(id=user_id, first_name="Test", is_bot=False, username="testuser")
    chat = Chat(id=chat_id, type="private")

    fake_message = MagicMock(spec=Message)
    fake_message.message_id = message_id
    fake_message.chat = chat
    fake_message.from_user = user

    query = MagicMock(spec=CallbackQuery)
    query.id = "cbq-1"
    query.from_user = user
    query.message = fake_message
    query.data = data
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()

    update = Update(update_id=1, callback_query=query)
    update._effective_user = user
    update._effective_chat = chat
    update._effective_message = fake_message
    return update


def make_context(app: Application) -> ContextTypes.DEFAULT_TYPE:
    """Build a Context with bot_data + user_data shared via app."""
    return ContextTypes.DEFAULT_TYPE(application=app, chat_id=1000, user_id=42)
