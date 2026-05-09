"""Tests for /q one-shot quick dispatch."""

from __future__ import annotations

from telegram import InlineKeyboardMarkup
from telegram.ext import Application

from bot.handlers.shortcuts import quick_dispatch
from tests.conftest import make_context, make_update


def _quick_ctx(app: Application, args: list[str]):
    """Build a Context with `args` populated as PTB does for /q <args>."""
    ctx = make_context(app)
    ctx.args = args
    return ctx


class TestQuickDispatch:
    async def test_no_args_prints_usage(self, app: Application) -> None:
        update = make_update("/q")
        ctx = _quick_ctx(app, [])

        await quick_dispatch(update, ctx)

        text = update.message.reply_text.call_args.args[0]
        assert "Usage" in text
        # No pending entry created
        assert not app.bot_data["pending_quick"]

    async def test_valid_urls_create_pending_with_inline_buttons(self, app: Application) -> None:
        update = make_update("/q")
        ctx = _quick_ctx(
            app,
            [
                "https://store.steampowered.com/app/440/",
                "https://x.itch.io/y",
            ],
        )

        await quick_dispatch(update, ctx)

        # Pending payload stored under user_id=42
        pending = app.bot_data["pending_quick"][42]
        assert len(pending["steam"]) == 1
        assert len(pending["itch"]) == 1
        # Inline buttons attached
        kwargs = update.message.reply_text.call_args.kwargs
        assert isinstance(kwargs["reply_markup"], InlineKeyboardMarkup)

    async def test_no_valid_urls_warns_user(self, app: Application) -> None:
        update = make_update("/q")
        ctx = _quick_ctx(app, ["nope", "alsogarbage"])

        await quick_dispatch(update, ctx)

        text = update.message.reply_text.call_args.args[0]
        assert "No valid links" in text
        assert not app.bot_data["pending_quick"]

    async def test_too_many_urls_rejected(self, app: Application) -> None:
        # Test config caps max_links_per_dispatch=5 — pass 6 valid steam URLs.
        update = make_update("/q")
        ctx = _quick_ctx(
            app,
            [f"https://store.steampowered.com/app/{i}/" for i in range(100, 106)],
        )

        await quick_dispatch(update, ctx)

        text = update.message.reply_text.call_args.args[0]
        assert "Too many" in text
        assert not app.bot_data["pending_quick"]

    async def test_unauthorized_rejected(self, app: Application) -> None:
        update = make_update("/q", user_id=999)
        ctx = _quick_ctx(app, ["https://store.steampowered.com/app/440/"])

        result = await quick_dispatch(update, ctx)
        assert result is None
        assert not app.bot_data["pending_quick"]
