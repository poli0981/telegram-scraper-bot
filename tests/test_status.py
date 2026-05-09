"""Tests for /status command."""

from __future__ import annotations

from telegram.ext import Application

from bot.gates import ConcurrencyLock, RateLimit
from bot.handlers.status import status_command
from tests.conftest import make_context, make_update


class TestStatus:
    async def test_idle_when_no_lock_and_no_usage(self, app: Application) -> None:
        update = make_update("/status")
        ctx = make_context(app)
        await status_command(update, ctx)

        text = update.message.reply_text.call_args.args[0]
        assert "idle" in text
        # User quota shows full available
        assert "100" in text  # user_max from default fixture

    async def test_in_flight_when_lock_held(self, app: Application) -> None:
        lock: ConcurrencyLock = app.bot_data["lock"]
        lock.try_acquire(42)

        update = make_update("/status")
        ctx = make_context(app)
        await status_command(update, ctx)

        text = update.message.reply_text.call_args.args[0]
        assert "in flight" in text

    async def test_quota_reflects_recent_dispatches(self, app: Application) -> None:
        rl: RateLimit = app.bot_data["rate_limit"]
        rl.record(42)
        rl.record(42)

        update = make_update("/status")
        ctx = make_context(app)
        await status_command(update, ctx)

        text = update.message.reply_text.call_args.args[0]
        # 100 - 2 = 98 left
        assert "98" in text

    async def test_buffer_size_shown_inside_wizard(self, app: Application) -> None:
        update = make_update("/status")
        ctx = make_context(app)
        ctx.user_data["buffer"] = ["a", "b", "c"]
        await status_command(update, ctx)

        text = update.message.reply_text.call_args.args[0]
        assert "Buffer" in text
        assert "3" in text

    async def test_unauthorized_rejected(self, app: Application) -> None:
        update = make_update("/status", user_id=999)
        ctx = make_context(app)
        result = await status_command(update, ctx)
        assert result is None
