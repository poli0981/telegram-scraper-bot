"""Tests for /help global command."""

from __future__ import annotations

from telegram.ext import Application

from bot.handlers.help import help_command
from tests.conftest import make_context, make_update


class TestHelp:
    async def test_help_lists_commands(self, app: Application) -> None:
        update = make_update("/help")
        ctx = make_context(app)
        await help_command(update, ctx)

        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args.args[0]
        # Sanity: every documented command should appear
        for cmd in (
            "/start",
            "/q",
            "/retry",
            "/status",
            "/version",
            "/whoami",
            "/cancel",
            "/reset",
            "/show",
        ):
            assert cmd in text

    async def test_help_rejects_unauthorized_user(self, app: Application) -> None:
        update = make_update("/help", user_id=999)
        ctx = make_context(app)
        result = await help_command(update, ctx)

        assert result is None
        text = update.message.reply_text.call_args.args[0]
        assert "Not authorized" in text
