"""Tests for /retry command."""

from __future__ import annotations

import time

from telegram import InlineKeyboardMarkup
from telegram.ext import Application

from bot.handlers.dispatch_flow import LAST_DISPATCH_TTL_SECONDS
from bot.handlers.retry import retry_command
from tests.conftest import make_context, make_update


class TestRetry:
    async def test_no_prior_dispatch_returns_friendly_message(self, app: Application) -> None:
        update = make_update("/retry")
        ctx = make_context(app)
        await retry_command(update, ctx)

        text = update.message.reply_text.call_args.args[0]
        assert "No dispatch to retry" in text

    async def test_replays_with_inline_buttons(self, app: Application) -> None:
        # Seed a fresh last_dispatch entry
        app.bot_data["last_dispatch"][42] = {
            "steam": ["https://store.steampowered.com/app/440/"],
            "itch": ["https://x.itch.io/y"],
            "ts": time.time(),
        }

        update = make_update("/retry")
        ctx = make_context(app)
        await retry_command(update, ctx)

        # Inline confirm/cancel buttons attached
        kwargs = update.message.reply_text.call_args.kwargs
        assert isinstance(kwargs["reply_markup"], InlineKeyboardMarkup)
        text = update.message.reply_text.call_args.args[0]
        assert "Replaying" in text or "Replay" in text

    async def test_expired_dispatch_treated_as_missing(self, app: Application) -> None:
        # ts is older than the TTL → treated as if no entry exists
        app.bot_data["last_dispatch"][42] = {
            "steam": ["https://store.steampowered.com/app/440/"],
            "itch": [],
            "ts": time.time() - LAST_DISPATCH_TTL_SECONDS - 60,
        }

        update = make_update("/retry")
        ctx = make_context(app)
        await retry_command(update, ctx)

        text = update.message.reply_text.call_args.args[0]
        assert "No dispatch to retry" in text

    async def test_unauthorized_rejected(self, app: Application) -> None:
        update = make_update("/retry", user_id=999)
        ctx = make_context(app)
        result = await retry_command(update, ctx)
        assert result is None
