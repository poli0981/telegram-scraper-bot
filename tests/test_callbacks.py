"""Tests for inline-button callback handlers."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock

from telegram.ext import Application, ConversationHandler

from bot.handlers.callbacks import (
    confirm_callback,
    mode_callback,
    quick_callback,
    retry_callback,
)
from bot.handlers.conversation import State
from tests.conftest import make_callback_update, make_context

# ─── mode:* (CHOOSE state) ──────────────────────────────────────


class TestModeCallback:
    async def test_steam_advances_to_collect(self, app: Application) -> None:
        update = make_callback_update("mode:steam")
        ctx = make_context(app)
        next_state = await mode_callback(update, ctx)
        assert next_state == State.COLLECT
        assert ctx.user_data["mode"] == "steam"
        assert ctx.user_data["buffer"] == []
        update.callback_query.answer.assert_awaited_once()
        update.callback_query.edit_message_text.assert_awaited_once()

    async def test_cancel_ends_conversation(self, app: Application) -> None:
        update = make_callback_update("mode:cancel")
        ctx = make_context(app)
        ctx.user_data["leftover"] = "x"
        next_state = await mode_callback(update, ctx)
        assert next_state == ConversationHandler.END
        assert ctx.user_data == {}

    async def test_unknown_mode_logs_and_does_nothing(self, app: Application) -> None:
        update = make_callback_update("mode:bogus")
        ctx = make_context(app)
        next_state = await mode_callback(update, ctx)
        assert next_state is None


# ─── confirm:* (CONFIRM state) ──────────────────────────────────


class TestConfirmCallback:
    async def test_cancel_clears_state_and_ends(self, app: Application) -> None:
        update = make_callback_update("confirm:cancel")
        ctx = make_context(app)
        ctx.user_data["preview"] = {"steam": ["x"], "itch": []}
        next_state = await confirm_callback(update, ctx)
        assert next_state == ConversationHandler.END
        assert ctx.user_data == {}

    async def test_edit_returns_to_collect_keeping_buffer(self, app: Application) -> None:
        update = make_callback_update("confirm:edit")
        ctx = make_context(app)
        ctx.user_data["preview"] = {"steam": ["x"], "itch": []}
        ctx.user_data["buffer"] = ["x"]
        next_state = await confirm_callback(update, ctx)
        assert next_state == State.COLLECT
        # Buffer must still be there for editing
        assert ctx.user_data["buffer"] == ["x"]

    async def test_yes_dispatches_via_gated_dispatch(
        self, app: Application, mock_dispatcher: AsyncMock
    ) -> None:
        update = make_callback_update("confirm:yes")
        ctx = make_context(app)
        ctx.user_data["preview"] = {
            "mode": "steam",
            "steam": ["https://store.steampowered.com/app/440/"],
            "itch": [],
            "invalid_count": 0,
        }
        next_state = await confirm_callback(update, ctx)
        assert next_state == ConversationHandler.END
        assert mock_dispatcher.dispatch.call_count == 1
        assert ctx.user_data == {}

    async def test_yes_without_preview_ends_cleanly(self, app: Application) -> None:
        update = make_callback_update("confirm:yes")
        ctx = make_context(app)
        # No preview in user_data
        next_state = await confirm_callback(update, ctx)
        assert next_state == ConversationHandler.END


# ─── quick:* (one-shot /q) ──────────────────────────────────────


class TestQuickCallback:
    async def test_cancel_clears_pending(self, app: Application) -> None:
        app.bot_data["pending_quick"][42] = {
            "steam": ["https://store.steampowered.com/app/440/"],
            "itch": [],
            "ts": time.time(),
        }
        update = make_callback_update("quick:cancel")
        ctx = make_context(app)
        await quick_callback(update, ctx)
        assert 42 not in app.bot_data["pending_quick"]

    async def test_yes_dispatches_pending_payload(
        self, app: Application, mock_dispatcher: AsyncMock
    ) -> None:
        app.bot_data["pending_quick"][42] = {
            "steam": ["https://store.steampowered.com/app/440/"],
            "itch": [],
            "ts": time.time(),
        }
        update = make_callback_update("quick:yes")
        ctx = make_context(app)
        await quick_callback(update, ctx)
        # Dispatcher hit once for steam
        assert mock_dispatcher.dispatch.call_count == 1
        # Pending consumed
        assert 42 not in app.bot_data["pending_quick"]
        # last_dispatch populated for /retry
        assert 42 in app.bot_data["last_dispatch"]

    async def test_yes_with_no_pending_warns(self, app: Application) -> None:
        update = make_callback_update("quick:yes")
        ctx = make_context(app)
        # No pending entry
        await quick_callback(update, ctx)
        update.callback_query.edit_message_text.assert_awaited()


# ─── retry:* ────────────────────────────────────────────────────


class TestRetryCallback:
    async def test_cancel_acks_only(self, app: Application) -> None:
        update = make_callback_update("retry:cancel")
        ctx = make_context(app)
        await retry_callback(update, ctx)
        update.callback_query.edit_message_text.assert_awaited()

    async def test_last_replays_full_payload(
        self, app: Application, mock_dispatcher: AsyncMock
    ) -> None:
        app.bot_data["last_dispatch"][42] = {
            "steam": ["https://store.steampowered.com/app/440/"],
            "itch": ["https://x.itch.io/y"],
            "ts": time.time(),
        }
        update = make_callback_update("retry:last")
        ctx = make_context(app)
        await retry_callback(update, ctx)
        # Both platforms dispatched
        assert mock_dispatcher.dispatch.call_count == 2

    async def test_platform_replays_only_named_platform(
        self, app: Application, mock_dispatcher: AsyncMock
    ) -> None:
        app.bot_data["last_dispatch"][42] = {
            "steam": ["https://store.steampowered.com/app/440/"],
            "itch": ["https://x.itch.io/y"],
            "ts": time.time(),
        }
        update = make_callback_update("retry:platform:steam")
        ctx = make_context(app)
        await retry_callback(update, ctx)
        # Only steam dispatched
        assert mock_dispatcher.dispatch.call_count == 1
        assert mock_dispatcher.dispatch.call_args.kwargs["repo"] == "user/steam"

    async def test_no_last_dispatch_warns(self, app: Application) -> None:
        update = make_callback_update("retry:last")
        ctx = make_context(app)
        await retry_callback(update, ctx)
        update.callback_query.edit_message_text.assert_awaited()
