"""Tests for bot.handlers.dispatch_flow — gate-protected dispatch helper."""

from __future__ import annotations

import contextlib
import time
from unittest.mock import AsyncMock

from telegram.ext import Application

from bot.dispatcher import DispatchResult
from bot.gates import ConcurrencyLock, RateLimit
from bot.handlers.dispatch_flow import (
    LAST_DISPATCH_TTL_SECONDS,
    check_gates,
    dispatch_one_platform,
    gated_dispatch,
    get_last_dispatch,
)


class TestCheckGates:
    def test_allows_when_idle(self, app: Application) -> None:
        decision = check_gates(user_id=42, bot_data=app.bot_data)
        assert decision.ok is True
        assert decision.user_message is None

    def test_blocks_when_lock_held(self, app: Application) -> None:
        lock: ConcurrencyLock = app.bot_data["lock"]
        lock.try_acquire(42)
        decision = check_gates(user_id=42, bot_data=app.bot_data)
        assert decision.ok is False
        assert "in flight" in decision.user_message

    def test_blocks_when_rate_limit_exceeded(self, app: Application) -> None:
        rl = RateLimit(user_max=1, user_window=60.0, global_max=10, global_window=60.0)
        rl.record(42)
        app.bot_data["rate_limit"] = rl
        decision = check_gates(user_id=42, bot_data=app.bot_data)
        assert decision.ok is False
        assert "Rate limit" in decision.user_message


class TestDispatchOnePlatform:
    async def test_success_returns_true_no_edit(
        self, app: Application, mock_dispatcher: AsyncMock
    ) -> None:
        ok = await dispatch_one_platform(
            platform="Steam",
            repo="user/steam",
            links=["https://store.steampowered.com/app/440/"],
            chat_id=1000,
            bot=app.bot,
            dispatcher=mock_dispatcher,
        )
        assert ok is True
        # Placeholder sent, no edit on success — workflow does that later
        assert app.bot.send_message.call_count == 1
        assert app.bot.edit_message_text.call_count == 0

    async def test_failure_edits_with_retry_button(
        self, app: Application, mock_dispatcher: AsyncMock
    ) -> None:
        mock_dispatcher.dispatch.return_value = DispatchResult(
            ok=False, repo="user/steam", status_code=403, error="forbidden"
        )
        ok = await dispatch_one_platform(
            platform="Steam",
            repo="user/steam",
            links=["https://store.steampowered.com/app/440/"],
            chat_id=1000,
            bot=app.bot,
            dispatcher=mock_dispatcher,
        )
        assert ok is False
        edit_kwargs = app.bot.edit_message_text.call_args.kwargs
        # Inline retry button attached
        assert edit_kwargs["reply_markup"] is not None
        assert "❌" in edit_kwargs["text"]


class TestGatedDispatch:
    async def test_happy_path_dispatches_and_records(
        self, app: Application, mock_dispatcher: AsyncMock
    ) -> None:
        ok, err = await gated_dispatch(
            user_id=42,
            chat_id=1000,
            steam=["https://store.steampowered.com/app/440/"],
            itch=[],
            bot_data=app.bot_data,
            bot=app.bot,
        )
        assert ok is True
        assert err is None
        # rate limit recorded
        rl: RateLimit = app.bot_data["rate_limit"]
        assert len(rl._global) == 1
        # last_dispatch populated for /retry
        assert 42 in app.bot_data["last_dispatch"]
        # lock released
        lock: ConcurrencyLock = app.bot_data["lock"]
        assert lock.is_held(42) is False

    async def test_rate_limit_block_skips_dispatch(
        self, app: Application, mock_dispatcher: AsyncMock
    ) -> None:
        rl = RateLimit(user_max=1, user_window=60.0, global_max=10, global_window=60.0)
        rl.record(42)
        app.bot_data["rate_limit"] = rl

        ok, err = await gated_dispatch(
            user_id=42,
            chat_id=1000,
            steam=["https://store.steampowered.com/app/440/"],
            itch=[],
            bot_data=app.bot_data,
            bot=app.bot,
        )
        assert ok is False
        assert "Rate limit" in err
        mock_dispatcher.dispatch.assert_not_called()

    async def test_lock_released_even_if_send_message_raises(
        self, app: Application, mock_dispatcher: AsyncMock
    ) -> None:
        # Make send_message blow up — simulates a transport error mid-dispatch.
        # ExtBot is frozen; use object.__setattr__ to bypass.
        object.__setattr__(app.bot, "send_message", AsyncMock(side_effect=RuntimeError("boom")))

        lock: ConcurrencyLock = app.bot_data["lock"]
        with contextlib.suppress(RuntimeError):
            await gated_dispatch(
                user_id=42,
                chat_id=1000,
                steam=["https://store.steampowered.com/app/440/"],
                itch=[],
                bot_data=app.bot_data,
                bot=app.bot,
            )
        # Despite exception, lock released
        assert lock.is_held(42) is False


class TestGetLastDispatch:
    def test_returns_fresh_entry(self, app: Application) -> None:
        app.bot_data["last_dispatch"][42] = {
            "steam": ["x"],
            "itch": [],
            "ts": time.time(),
        }
        entry = get_last_dispatch(app.bot_data, 42)
        assert entry is not None
        assert entry["steam"] == ["x"]

    def test_returns_none_when_missing(self, app: Application) -> None:
        assert get_last_dispatch(app.bot_data, 42) is None

    def test_returns_none_when_expired(self, app: Application) -> None:
        app.bot_data["last_dispatch"][42] = {
            "steam": [],
            "itch": [],
            "ts": time.time() - LAST_DISPATCH_TTL_SECONDS - 60,
        }
        assert get_last_dispatch(app.bot_data, 42) is None
