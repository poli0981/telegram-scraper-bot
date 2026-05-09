"""Tests for bot.handlers.error — global exception sink."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Chat, Message, Update, User
from telegram.ext import ContextTypes

from bot.handlers.error import error_handler


def _make_context_with_error(err: Exception) -> ContextTypes.DEFAULT_TYPE:
    """Build a Context whose .error is set, mimicking PTB's error_handler dispatch."""
    ctx = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    ctx.error = err
    return ctx


def _make_update_with_message() -> Update:
    user = User(id=42, first_name="T", is_bot=False)
    chat = Chat(id=1000, type="private")
    msg = MagicMock(spec=Message)
    msg.reply_text = AsyncMock()
    update = Update(update_id=1, message=msg)
    update._effective_user = user
    update._effective_chat = chat
    update._effective_message = msg
    return update


class TestErrorHandler:
    async def test_logs_traceback(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        try:
            raise ValueError("test exception with unique-token-9c4b")
        except ValueError as e:
            err = e

        ctx = _make_context_with_error(err)
        update = _make_update_with_message()

        with caplog.at_level(logging.ERROR):
            await error_handler(update, ctx)

        # Traceback contains both the error message and the file context
        log_output = caplog.text
        assert "unique-token-9c4b" in log_output
        assert "Unhandled exception" in log_output

    async def test_replies_to_user(self) -> None:
        ctx = _make_context_with_error(RuntimeError("internal detail"))
        update = _make_update_with_message()

        await error_handler(update, ctx)

        update.effective_message.reply_text.assert_called_once()
        reply = update.effective_message.reply_text.call_args.args[0]
        assert "Internal error" in reply
        # Internal details should NOT leak to user
        assert "internal detail" not in reply
        assert "RuntimeError" not in reply

    async def test_no_error_in_context_no_op(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        ctx = _make_context_with_error(None)  # type: ignore[arg-type]
        update = _make_update_with_message()

        with caplog.at_level(logging.ERROR):
            await error_handler(update, ctx)

        update.effective_message.reply_text.assert_not_called()

    async def test_handles_non_update_object(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """PTB sometimes passes non-Update objects (e.g. string) for non-update errors."""
        ctx = _make_context_with_error(ValueError("background task error"))

        with caplog.at_level(logging.ERROR):
            # Should log the error but not try to reply (no chat available)
            await error_handler("not an update", ctx)

        assert "background task error" in caplog.text

    async def test_handles_update_without_message(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """An Update can have effective_message=None (e.g. callback queries)."""
        update = Update(update_id=1)  # no message
        ctx = _make_context_with_error(RuntimeError("boom"))

        with caplog.at_level(logging.ERROR):
            # Should not raise even though there's nowhere to reply
            await error_handler(update, ctx)

        assert "boom" in caplog.text

    async def test_reply_failure_does_not_propagate(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """If the reply itself fails (e.g. blocked user), error_handler must swallow."""
        update = _make_update_with_message()
        update.effective_message.reply_text.side_effect = RuntimeError("send failed")
        ctx = _make_context_with_error(ValueError("original"))

        with caplog.at_level(logging.ERROR):
            # Must not raise
            await error_handler(update, ctx)

        # Both errors logged
        assert "original" in caplog.text
        assert "failed to notify user" in caplog.text
