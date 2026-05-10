"""Tests for /whoami — runs without auth (intentionally)."""

from __future__ import annotations

from telegram.ext import Application

from bot.handlers.whoami import whoami_command
from tests.conftest import make_context, make_update


class TestWhoami:
    async def test_authorized_user_sees_yes(self, app: Application) -> None:
        update = make_update("/whoami", user_id=42)  # 42 is in the test allow-list
        ctx = make_context(app)
        await whoami_command(update, ctx)

        text = update.message.reply_text.call_args.args[0]
        assert "42" in text
        assert "✅ yes" in text

    async def test_unauthorized_user_still_gets_id(self, app: Application) -> None:
        """The whole point: non-allow-listed users must be able to see their ID."""
        update = make_update("/whoami", user_id=999)
        ctx = make_context(app)
        await whoami_command(update, ctx)

        text = update.message.reply_text.call_args.args[0]
        assert "999" in text
        assert "❌ no" in text
        # And told how to recover
        assert "ALLOWED_USER_IDS" in text

    async def test_username_included_when_present(self, app: Application) -> None:
        update = make_update("/whoami", user_id=42)
        ctx = make_context(app)
        # The default fixture sets username="testuser"
        await whoami_command(update, ctx)
        text = update.message.reply_text.call_args.args[0]
        assert "@testuser" in text
