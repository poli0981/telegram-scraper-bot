"""Tests for bot.handlers.conversation — full async wizard flow.

Uses PTB's Application + AsyncMock dispatcher to exercise handlers without
hitting any network. Each test simulates one user → one full conversation.

Common fixtures (`app`, `config`, `mock_dispatcher`) and helpers (`make_update`,
`make_context`) live in conftest.py and are shared with the other handler tests.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Chat, InlineKeyboardMarkup, Message, Update, User
from telegram.ext import Application, ConversationHandler

from bot.dispatcher import DispatchResult
from bot.gates import ConcurrencyLock, RateLimit
from bot.handlers.conversation import (
    State,
    cancel,
    choose_mode,
    collect,
    collect_file,
    confirm_yes,
    done,
    reset_buffer,
    show_buffer,
    start,
)
from tests.conftest import make_context, make_update

# Compatibility aliases — keeps the body of legacy tests in this file unchanged.
_make_update = make_update
_make_context = make_context


# ─── /start ─────────────────────────────────────────────────────


class TestStart:
    async def test_authorized_user_sees_keyboard(self, app: Application) -> None:
        update = _make_update("/start")
        ctx = _make_context(app)
        next_state = await start(update, ctx)
        assert next_state == State.CHOOSE
        update.message.reply_text.assert_called_once()
        # /start now ships an inline keyboard with mode buttons
        kwargs = update.message.reply_text.call_args.kwargs
        assert isinstance(kwargs["reply_markup"], InlineKeyboardMarkup)

    async def test_unauthorized_user_rejected(self, app: Application) -> None:
        update = _make_update("/start", user_id=999)  # not in allow-list
        ctx = _make_context(app)
        result = await start(update, ctx)
        assert result is None  # auth decorator early-exits
        update.message.reply_text.assert_called_once()
        assert "Not authorized" in update.message.reply_text.call_args.args[0]

    async def test_clears_previous_user_data(self, app: Application) -> None:
        update = _make_update("/start")
        ctx = _make_context(app)
        ctx.user_data["stale"] = "data"
        await start(update, ctx)
        assert "stale" not in ctx.user_data


# ─── CHOOSE state ───────────────────────────────────────────────


class TestChooseMode:
    @pytest.mark.parametrize("cmd", ["/steam", "/itch", "/mixed"])
    async def test_valid_modes_advance_to_collect(self, app: Application, cmd: str) -> None:
        update = _make_update(cmd)
        ctx = _make_context(app)
        next_state = await choose_mode(update, ctx)
        assert next_state == State.COLLECT
        assert ctx.user_data["mode"] == cmd.lstrip("/")
        assert ctx.user_data["buffer"] == []

    async def test_invalid_mode_stays_in_choose(self, app: Application) -> None:
        update = _make_update("/garbage")
        ctx = _make_context(app)
        next_state = await choose_mode(update, ctx)
        assert next_state == State.CHOOSE
        assert "mode" not in ctx.user_data


# ─── COLLECT state ──────────────────────────────────────────────


class TestCollect:
    async def test_appends_lines_to_buffer(self, app: Application) -> None:
        update = _make_update(
            "https://store.steampowered.com/app/440/\nhttps://store.steampowered.com/app/730/"
        )
        ctx = _make_context(app)
        ctx.user_data["mode"] = "steam"
        ctx.user_data["buffer"] = []

        next_state = await collect(update, ctx)

        assert next_state == State.COLLECT
        assert len(ctx.user_data["buffer"]) == 2

    async def test_skips_blank_lines(self, app: Application) -> None:
        update = _make_update("\n\nhttps://x.itch.io/y\n  \n")
        ctx = _make_context(app)
        ctx.user_data["mode"] = "itch"
        ctx.user_data["buffer"] = []

        await collect(update, ctx)

        assert len(ctx.user_data["buffer"]) == 1

    async def test_enforces_max_links_per_dispatch(self, app: Application) -> None:
        update = _make_update("\n".join(f"line{i}" for i in range(10)))
        ctx = _make_context(app)
        ctx.user_data["mode"] = "mixed"
        ctx.user_data["buffer"] = []

        await collect(update, ctx)

        # Config.max_links_per_dispatch=5 in fixture
        assert len(ctx.user_data["buffer"]) == 5
        # Reply should mention the overflow
        reply = update.message.reply_text.call_args.args[0]
        assert "dropped" in reply

    async def test_rejects_when_buffer_already_full(self, app: Application) -> None:
        update = _make_update("more\nlines")
        ctx = _make_context(app)
        ctx.user_data["mode"] = "mixed"
        ctx.user_data["buffer"] = ["x"] * 5  # already at limit

        await collect(update, ctx)

        assert len(ctx.user_data["buffer"]) == 5  # unchanged
        reply = update.message.reply_text.call_args.args[0]
        assert "limit" in reply.lower()

    async def test_live_dedupe_warns_on_duplicate_paste(self, app: Application) -> None:
        """Pasting a URL already in the buffer should be skipped + reported."""
        update = _make_update(
            "https://store.steampowered.com/app/440/\n"
            "https://store.steampowered.com/app/440/"  # second is a dup
        )
        ctx = _make_context(app)
        ctx.user_data["mode"] = "mixed"
        ctx.user_data["buffer"] = []

        await collect(update, ctx)

        # Only one copy in buffer
        assert len(ctx.user_data["buffer"]) == 1
        # seen_urls tracks the canonical URL
        assert "https://store.steampowered.com/app/440/" in ctx.user_data["seen_urls"]
        # User got a warning about the duplicate
        reply = update.message.reply_text.call_args.args[0]
        assert "duplicate" in reply.lower()

    async def test_live_dedupe_across_separate_messages(self, app: Application) -> None:
        """Duplicate detection survives between paste messages within one wizard."""
        ctx = _make_context(app)
        ctx.user_data["mode"] = "mixed"
        ctx.user_data["buffer"] = []

        # First paste
        u1 = _make_update("https://store.steampowered.com/app/440/")
        await collect(u1, ctx)
        # Second paste — same URL
        u2 = _make_update("https://store.steampowered.com/app/440/")
        await collect(u2, ctx)

        assert len(ctx.user_data["buffer"]) == 1
        reply = u2.message.reply_text.call_args.args[0]
        assert "duplicate" in reply.lower()

    async def test_concatenated_urls_split_into_buffer(self, app: Application) -> None:
        """Concat URLs (no separator) become two buffer entries via split_inline_urls."""
        update = _make_update(
            "https://store.steampowered.com/app/4343200/Pets/"
            "https://store.steampowered.com/app/1170880/Hollow/"
        )
        ctx = _make_context(app)
        ctx.user_data["mode"] = "mixed"
        ctx.user_data["buffer"] = []

        await collect(update, ctx)

        # Buffer holds 2 entries (one per URL), not one concat
        assert len(ctx.user_data["buffer"]) == 2


# ─── COLLECT state — file upload ────────────────────────────────


class TestCollectFile:
    async def test_txt_file_appends_lines(self, app: Application) -> None:
        update = _make_document_update(
            file_name="links.txt",
            file_bytes=b"https://store.steampowered.com/app/440/\nhttps://x.itch.io/y\n",
        )
        ctx = _make_context(app)
        ctx.user_data["mode"] = "mixed"
        ctx.user_data["buffer"] = []

        next_state = await collect_file(update, ctx)

        assert next_state == State.COLLECT
        assert len(ctx.user_data["buffer"]) == 2

    async def test_json_array_of_strings(self, app: Application) -> None:
        update = _make_document_update(
            file_name="links.json",
            file_bytes=b'["https://x.itch.io/a", "https://x.itch.io/b"]',
        )
        ctx = _make_context(app)
        ctx.user_data["mode"] = "itch"
        ctx.user_data["buffer"] = []

        await collect_file(update, ctx)

        assert ctx.user_data["buffer"] == [
            "https://x.itch.io/a",
            "https://x.itch.io/b",
        ]

    async def test_json_array_of_objects(self, app: Application) -> None:
        update = _make_document_update(
            file_name="links.json",
            file_bytes=b'[{"link": "https://x.itch.io/a"}, {"link": "https://x.itch.io/b"}]',
        )
        ctx = _make_context(app)
        ctx.user_data["mode"] = "itch"
        ctx.user_data["buffer"] = []

        await collect_file(update, ctx)

        assert len(ctx.user_data["buffer"]) == 2

    async def test_unsupported_extension_rejected(self, app: Application) -> None:
        update = _make_document_update(
            file_name="links.csv",
            file_bytes=b"url1,url2",
        )
        ctx = _make_context(app)
        ctx.user_data["mode"] = "mixed"
        ctx.user_data["buffer"] = []

        next_state = await collect_file(update, ctx)

        assert next_state == State.COLLECT
        assert ctx.user_data["buffer"] == []
        reply = update.message.reply_text.call_args.args[0]
        assert "Unsupported file type" in reply

    async def test_malformed_json_cancels_wizard(self, app: Application) -> None:
        """Malformed JSON is treated as a copy-paste mistake — cancel the wizard.

        Rationale: the user almost certainly needs to fix the file and re-upload
        from scratch. Letting them stay in COLLECT with a half-populated buffer
        is more confusing than starting fresh.
        """
        update = _make_document_update(
            file_name="links.json",
            file_bytes=b"{not valid json",
        )
        ctx = _make_context(app)
        ctx.user_data["mode"] = "itch"
        ctx.user_data["buffer"] = ["https://x.itch.io/y"]  # had stuff before upload

        next_state = await collect_file(update, ctx)

        # Wizard ended; user_data wiped
        assert next_state == ConversationHandler.END
        assert ctx.user_data == {}
        reply = update.message.reply_text.call_args.args[0]
        assert "JSON error" in reply
        assert "/start" in reply  # tell user how to recover

    async def test_empty_file_warned(self, app: Application) -> None:
        update = _make_document_update(file_name="links.txt", file_bytes=b"")
        ctx = _make_context(app)
        ctx.user_data["mode"] = "mixed"
        ctx.user_data["buffer"] = []

        await collect_file(update, ctx)

        reply = update.message.reply_text.call_args.args[0]
        assert "empty" in reply.lower()

    async def test_oversized_file_rejected(self, app: Application) -> None:
        # Exceed MAX_FILE_SIZE (256 KiB)
        update = _make_document_update(
            file_name="huge.txt",
            file_bytes=b"x" * (256 * 1024 + 1),
        )
        ctx = _make_context(app)
        ctx.user_data["mode"] = "mixed"
        ctx.user_data["buffer"] = []

        await collect_file(update, ctx)

        assert ctx.user_data["buffer"] == []
        reply = update.message.reply_text.call_args.args[0]
        assert "max allowed" in reply.lower()

    async def test_file_respects_buffer_limit(self, app: Application) -> None:
        # Config.max_links_per_dispatch=5 in fixture; file has 10 lines
        update = _make_document_update(
            file_name="links.txt",
            file_bytes=b"\n".join(f"line{i}".encode() for i in range(10)),
        )
        ctx = _make_context(app)
        ctx.user_data["mode"] = "mixed"
        ctx.user_data["buffer"] = []

        await collect_file(update, ctx)

        assert len(ctx.user_data["buffer"]) == 5
        reply = update.message.reply_text.call_args.args[0]
        assert "dropped" in reply

    async def test_download_failure_handled(self, app: Application) -> None:
        update = _make_document_update(file_name="links.txt", file_bytes=b"url1\n")
        # Make get_file raise
        update.message.document.get_file.side_effect = RuntimeError("network error")

        ctx = _make_context(app)
        ctx.user_data["mode"] = "mixed"
        ctx.user_data["buffer"] = []

        await collect_file(update, ctx)

        assert ctx.user_data["buffer"] == []
        reply = update.message.reply_text.call_args.args[0]
        assert "Failed to download" in reply


# ─── /done ──────────────────────────────────────────────────────


class TestDone:
    async def test_empty_buffer_stays_in_collect(self, app: Application) -> None:
        update = _make_update("/done")
        ctx = _make_context(app)
        ctx.user_data["mode"] = "mixed"
        ctx.user_data["buffer"] = []

        next_state = await done(update, ctx)

        assert next_state == State.COLLECT
        reply = update.message.reply_text.call_args.args[0]
        assert "Nothing buffered" in reply

    async def test_valid_links_advance_to_confirm(self, app: Application) -> None:
        update = _make_update("/done")
        ctx = _make_context(app)
        ctx.user_data["mode"] = "mixed"
        ctx.user_data["buffer"] = [
            "https://store.steampowered.com/app/440/",
            "https://x.itch.io/y",
        ]

        next_state = await done(update, ctx)

        assert next_state == State.CONFIRM
        assert ctx.user_data["preview"]["mode"] == "mixed"
        assert len(ctx.user_data["preview"]["steam"]) == 1
        assert len(ctx.user_data["preview"]["itch"]) == 1

    async def test_only_invalid_links_ends_conversation(self, app: Application) -> None:
        update = _make_update("/done")
        ctx = _make_context(app)
        ctx.user_data["mode"] = "mixed"
        ctx.user_data["buffer"] = ["garbage", "more garbage"]

        next_state = await done(update, ctx)

        assert next_state == ConversationHandler.END
        # user_data cleared
        assert ctx.user_data == {}

    async def test_steam_mode_filters_itch_to_invalid(self, app: Application) -> None:
        update = _make_update("/done")
        ctx = _make_context(app)
        ctx.user_data["mode"] = "steam"
        ctx.user_data["buffer"] = [
            "https://store.steampowered.com/app/440/",
            "https://x.itch.io/y",  # should be filtered out
        ]

        await done(update, ctx)

        preview = ctx.user_data["preview"]
        assert len(preview["steam"]) == 1
        assert len(preview["itch"]) == 0
        assert preview["invalid_count"] == 1

    async def test_itch_mode_filters_steam_to_invalid(self, app: Application) -> None:
        update = _make_update("/done")
        ctx = _make_context(app)
        ctx.user_data["mode"] = "itch"
        ctx.user_data["buffer"] = [
            "https://x.itch.io/y",
            "https://store.steampowered.com/app/440/",
        ]

        await done(update, ctx)

        preview = ctx.user_data["preview"]
        assert len(preview["itch"]) == 1
        assert len(preview["steam"]) == 0
        assert preview["invalid_count"] == 1

    async def test_dedupes_buffer(self, app: Application) -> None:
        update = _make_update("/done")
        ctx = _make_context(app)
        ctx.user_data["mode"] = "mixed"
        ctx.user_data["buffer"] = [
            "https://store.steampowered.com/app/440/",
            "https://store.steampowered.com/app/440/",  # dup
            "440",  # also normalizes to same URL
        ]

        await done(update, ctx)

        assert len(ctx.user_data["preview"]["steam"]) == 1


def _make_document_update(
    *,
    file_name: str,
    file_bytes: bytes,
    user_id: int = 42,
    chat_id: int = 1000,
) -> Update:
    """Build an Update simulating a document upload.

    Mocks doc.get_file() so it returns a fake File whose download_as_bytearray()
    returns our injected bytes. No real Telegram API calls.
    """
    user = User(id=user_id, first_name="Test", is_bot=False, username="testuser")
    chat = Chat(id=chat_id, type="private")

    # Mock the File returned by doc.get_file()
    fake_file = MagicMock()
    fake_file.download_as_bytearray = AsyncMock(return_value=bytearray(file_bytes))

    # Mock the Document
    fake_doc = MagicMock()
    fake_doc.file_name = file_name
    fake_doc.get_file = AsyncMock(return_value=fake_file)

    message = MagicMock(spec=Message)
    message.text = None  # document upload, not text
    message.document = fake_doc
    message.message_id = 1
    message.chat = chat
    message.from_user = user
    message.reply_text = AsyncMock()

    update = Update(update_id=1, message=message)
    update._effective_user = user
    update._effective_chat = chat
    update._effective_message = message
    return update


# ─── /yes ───────────────────────────────────────────────────────


class TestConfirmYes:
    """Each platform gets its own placeholder message + independent dispatch."""

    async def test_steam_only_sends_one_placeholder(
        self, app: Application, mock_dispatcher: AsyncMock
    ) -> None:
        update = _make_update("/yes")
        ctx = _make_context(app)
        ctx.user_data["preview"] = {
            "mode": "steam",
            "steam": ["https://store.steampowered.com/app/440/"],
            "itch": [],
            "invalid_count": 0,
        }

        next_state = await confirm_yes(update, ctx)

        assert next_state == ConversationHandler.END
        # Exactly one placeholder sent
        assert app.bot.send_message.call_count == 1
        # Placeholder text mentions Steam, not itch
        kwargs = app.bot.send_message.call_args.kwargs
        assert "Steam" in kwargs["text"]
        # Dispatcher called once with steam_repo
        assert mock_dispatcher.dispatch.call_count == 1
        assert mock_dispatcher.dispatch.call_args.kwargs["repo"] == "user/steam"

    async def test_itch_only_sends_one_placeholder(
        self, app: Application, mock_dispatcher: AsyncMock
    ) -> None:
        update = _make_update("/yes")
        ctx = _make_context(app)
        ctx.user_data["preview"] = {
            "mode": "itch",
            "steam": [],
            "itch": ["https://x.itch.io/y"],
            "invalid_count": 0,
        }

        await confirm_yes(update, ctx)

        assert app.bot.send_message.call_count == 1
        kwargs = app.bot.send_message.call_args.kwargs
        assert "itch" in kwargs["text"]
        assert mock_dispatcher.dispatch.call_count == 1
        assert mock_dispatcher.dispatch.call_args.kwargs["repo"] == "user/itch"

    async def test_mixed_sends_two_placeholders(
        self, app: Application, mock_dispatcher: AsyncMock
    ) -> None:
        """The key Phase 2 requirement: 2 separate messages, 2 separate dispatches."""
        update = _make_update("/yes")
        ctx = _make_context(app)
        ctx.user_data["preview"] = {
            "mode": "mixed",
            "steam": ["https://store.steampowered.com/app/440/"],
            "itch": ["https://x.itch.io/y"],
            "invalid_count": 0,
        }

        await confirm_yes(update, ctx)

        # Two placeholder messages
        assert app.bot.send_message.call_count == 2
        texts = [c.kwargs["text"] for c in app.bot.send_message.call_args_list]
        assert any("Steam" in t for t in texts)
        assert any("itch" in t for t in texts)

        # Two dispatches, one per repo
        assert mock_dispatcher.dispatch.call_count == 2
        repos = {c.kwargs["repo"] for c in mock_dispatcher.dispatch.call_args_list}
        assert repos == {"user/steam", "user/itch"}

    async def test_each_dispatch_uses_its_own_message_id(
        self, app: Application, mock_dispatcher: AsyncMock
    ) -> None:
        """Steam dispatch + itch dispatch must reference *different* message IDs."""
        # Make send_message return a different message_id each call
        msg1 = MagicMock(spec=Message)
        msg1.message_id = 100
        msg2 = MagicMock(spec=Message)
        msg2.message_id = 200
        app.bot.send_message.side_effect = [msg1, msg2]

        update = _make_update("/yes")
        ctx = _make_context(app)
        ctx.user_data["preview"] = {
            "mode": "mixed",
            "steam": ["https://store.steampowered.com/app/440/"],
            "itch": ["https://x.itch.io/y"],
            "invalid_count": 0,
        }

        await confirm_yes(update, ctx)

        # Each dispatcher call references the corresponding placeholder's id
        message_ids = {c.kwargs["message_id"] for c in mock_dispatcher.dispatch.call_args_list}
        assert message_ids == {100, 200}

    async def test_dispatch_failure_edits_only_that_placeholder(
        self, app: Application, mock_dispatcher: AsyncMock
    ) -> None:
        """If Steam dispatch fails, only the Steam placeholder gets edited with the error."""
        msg_steam = MagicMock(spec=Message)
        msg_steam.message_id = 100
        msg_itch = MagicMock(spec=Message)
        msg_itch.message_id = 200
        app.bot.send_message.side_effect = [msg_steam, msg_itch]

        # Steam fails, itch succeeds
        mock_dispatcher.dispatch.side_effect = [
            DispatchResult(ok=False, repo="user/steam", status_code=403, error="forbidden"),
            DispatchResult(ok=True, repo="user/itch", status_code=204),
        ]

        update = _make_update("/yes")
        ctx = _make_context(app)
        ctx.user_data["preview"] = {
            "mode": "mixed",
            "steam": ["https://store.steampowered.com/app/440/"],
            "itch": ["https://x.itch.io/y"],
            "invalid_count": 0,
        }

        await confirm_yes(update, ctx)

        # Only one edit_message_text call (for Steam's failed placeholder)
        assert app.bot.edit_message_text.call_count == 1
        edit_kwargs = app.bot.edit_message_text.call_args.kwargs
        assert edit_kwargs["message_id"] == 100  # Steam's id
        assert "❌" in edit_kwargs["text"]
        assert "forbidden" in edit_kwargs["text"]
        assert "403" in edit_kwargs["text"]

    async def test_successful_dispatch_does_not_edit_placeholder(
        self, app: Application, mock_dispatcher: AsyncMock
    ) -> None:
        """On success the workflow itself edits the message — bot doesn't touch it."""
        update = _make_update("/yes")
        ctx = _make_context(app)
        ctx.user_data["preview"] = {
            "mode": "steam",
            "steam": ["https://store.steampowered.com/app/440/"],
            "itch": [],
            "invalid_count": 0,
        }

        await confirm_yes(update, ctx)

        # Placeholder sent, but no immediate edit (workflow will do it later)
        assert app.bot.send_message.call_count == 1
        assert app.bot.edit_message_text.call_count == 0

    async def test_no_preview_ends_conversation(self, app: Application) -> None:
        update = _make_update("/yes")
        ctx = _make_context(app)
        # No preview in user_data

        next_state = await confirm_yes(update, ctx)

        assert next_state == ConversationHandler.END

    async def test_clears_user_data_after_dispatch(
        self, app: Application, mock_dispatcher: AsyncMock
    ) -> None:
        update = _make_update("/yes")
        ctx = _make_context(app)
        ctx.user_data["preview"] = {
            "mode": "steam",
            "steam": ["https://store.steampowered.com/app/440/"],
            "itch": [],
            "invalid_count": 0,
        }

        await confirm_yes(update, ctx)

        assert ctx.user_data == {}


# ─── Gates: concurrency lock + rate limit ───────────────────────


class TestConfirmYesGates:
    """Verify that confirm_yes respects the concurrency lock and rate limit."""

    async def test_rate_limit_blocks_dispatch(
        self, app: Application, mock_dispatcher: AsyncMock
    ) -> None:
        # Tighten rate limit so it's already exceeded
        rl = RateLimit(user_max=1, user_window=60.0, global_max=10, global_window=60.0)
        rl.record(42)  # one prior dispatch in window
        app.bot_data["rate_limit"] = rl

        update = _make_update("/yes")
        ctx = _make_context(app)
        ctx.user_data["preview"] = {
            "mode": "steam",
            "steam": ["https://store.steampowered.com/app/440/"],
            "itch": [],
            "invalid_count": 0,
        }

        next_state = await confirm_yes(update, ctx)

        assert next_state == ConversationHandler.END
        # Dispatcher should not be called
        mock_dispatcher.dispatch.assert_not_called()
        # User got a rate-limit message
        reply = update.message.reply_text.call_args.args[0]
        assert "Rate limit" in reply
        # State cleared
        assert ctx.user_data == {}

    async def test_global_rate_limit_blocks_with_correct_scope(
        self, app: Application, mock_dispatcher: AsyncMock
    ) -> None:
        rl = RateLimit(user_max=100, user_window=60.0, global_max=1, global_window=60.0)
        rl.record(99)  # different user filled the global cap
        app.bot_data["rate_limit"] = rl

        update = _make_update("/yes")
        ctx = _make_context(app)
        ctx.user_data["preview"] = {
            "mode": "steam",
            "steam": ["https://store.steampowered.com/app/440/"],
            "itch": [],
            "invalid_count": 0,
        }

        await confirm_yes(update, ctx)

        mock_dispatcher.dispatch.assert_not_called()
        reply = update.message.reply_text.call_args.args[0]
        assert "global" in reply

    async def test_concurrency_lock_blocks_second_dispatch(
        self, app: Application, mock_dispatcher: AsyncMock
    ) -> None:
        # User already has a dispatch in flight
        lock: ConcurrencyLock = app.bot_data["lock"]
        lock.try_acquire(42)

        update = _make_update("/yes")
        ctx = _make_context(app)
        ctx.user_data["preview"] = {
            "mode": "steam",
            "steam": ["https://store.steampowered.com/app/440/"],
            "itch": [],
            "invalid_count": 0,
        }

        await confirm_yes(update, ctx)

        mock_dispatcher.dispatch.assert_not_called()
        reply = update.message.reply_text.call_args.args[0]
        assert "in flight" in reply

    async def test_lock_released_after_successful_dispatch(
        self, app: Application, mock_dispatcher: AsyncMock
    ) -> None:
        lock: ConcurrencyLock = app.bot_data["lock"]
        update = _make_update("/yes")
        ctx = _make_context(app)
        ctx.user_data["preview"] = {
            "mode": "steam",
            "steam": ["https://store.steampowered.com/app/440/"],
            "itch": [],
            "invalid_count": 0,
        }

        await confirm_yes(update, ctx)

        # Lock released — user can dispatch again
        assert lock.is_held(42) is False

    async def test_lock_released_even_when_dispatch_raises(
        self, app: Application, mock_dispatcher: AsyncMock
    ) -> None:
        """If the platform dispatch helper raises, the lock must still release."""
        # Make the bot's send_message raise — _dispatch_one_platform fails fast
        app.bot.send_message.side_effect = RuntimeError("boom")

        lock: ConcurrencyLock = app.bot_data["lock"]
        update = _make_update("/yes")
        ctx = _make_context(app)
        ctx.user_data["preview"] = {
            "mode": "steam",
            "steam": ["https://store.steampowered.com/app/440/"],
            "itch": [],
            "invalid_count": 0,
        }

        with pytest.raises(RuntimeError):
            await confirm_yes(update, ctx)

        # Despite exception, lock is released (try/finally)
        assert lock.is_held(42) is False

    async def test_rate_limit_recorded_only_after_dispatch(
        self, app: Application, mock_dispatcher: AsyncMock
    ) -> None:
        rl: RateLimit = app.bot_data["rate_limit"]
        update = _make_update("/yes")
        ctx = _make_context(app)
        ctx.user_data["preview"] = {
            "mode": "steam",
            "steam": ["https://store.steampowered.com/app/440/"],
            "itch": [],
            "invalid_count": 0,
        }

        # Before dispatch: counter is empty
        assert len(rl._global) == 0

        await confirm_yes(update, ctx)

        # After: one record
        assert len(rl._global) == 1


# ─── /cancel ────────────────────────────────────────────────────


class TestCancel:
    async def test_cancel_clears_state_and_ends(self, app: Application) -> None:
        update = _make_update("/cancel")
        ctx = _make_context(app)
        ctx.user_data["mode"] = "steam"
        ctx.user_data["buffer"] = ["x", "y"]

        next_state = await cancel(update, ctx)

        assert next_state == ConversationHandler.END
        assert ctx.user_data == {}

    async def test_cancel_releases_concurrency_lock(self, app: Application) -> None:
        """If /cancel runs while a lock is held, the lock must be released.

        Otherwise a user who got stuck mid-dispatch would be locked out for up
        to 10 minutes (until stale_after expires).
        """
        lock: ConcurrencyLock = app.bot_data["lock"]
        lock.try_acquire(42)
        assert lock.is_held(42)

        update = _make_update("/cancel")
        ctx = _make_context(app)
        await cancel(update, ctx)

        assert lock.is_held(42) is False


# ─── /reset and /show (COLLECT helpers) ────────────────────────


class TestResetBuffer:
    async def test_reset_clears_buffer(self, app: Application) -> None:
        update = _make_update("/reset")
        ctx = _make_context(app)
        ctx.user_data["mode"] = "mixed"
        ctx.user_data["buffer"] = ["url1", "url2"]

        next_state = await reset_buffer(update, ctx)

        assert next_state == State.COLLECT
        assert ctx.user_data["buffer"] == []
        # Mode preserved — only the buffer is cleared
        assert ctx.user_data["mode"] == "mixed"

    async def test_reset_clears_seen_urls_too(self, app: Application) -> None:
        """Without this, post-reset the user couldn't re-paste the same URL."""
        update = _make_update("/reset")
        ctx = _make_context(app)
        ctx.user_data["mode"] = "mixed"
        ctx.user_data["buffer"] = ["https://store.steampowered.com/app/440/"]
        ctx.user_data["seen_urls"] = {"https://store.steampowered.com/app/440/"}

        await reset_buffer(update, ctx)

        assert ctx.user_data["seen_urls"] == set()


class TestShowBuffer:
    async def test_show_empty_buffer(self, app: Application) -> None:
        update = _make_update("/show")
        ctx = _make_context(app)
        ctx.user_data["mode"] = "mixed"
        ctx.user_data["buffer"] = []

        next_state = await show_buffer(update, ctx)

        assert next_state == State.COLLECT
        reply = update.message.reply_text.call_args.args[0]
        assert "empty" in reply.lower()

    async def test_show_buffer_lists_lines(self, app: Application) -> None:
        update = _make_update("/show")
        ctx = _make_context(app)
        ctx.user_data["mode"] = "mixed"
        ctx.user_data["buffer"] = [
            "https://store.steampowered.com/app/440/",
            "https://x.itch.io/y",
        ]

        await show_buffer(update, ctx)

        reply = update.message.reply_text.call_args.args[0]
        # Count is rendered, plus a sample of each line (truncated)
        assert "2" in reply
        assert "440" in reply

    async def test_show_buffer_truncates_long_lists(self, app: Application) -> None:
        """A buffer larger than _BUFFER_SHOW_LIMIT should yield an 'and N more'."""
        update = _make_update("/show")
        ctx = _make_context(app)
        ctx.user_data["mode"] = "mixed"
        # Way more than the show limit (10)
        ctx.user_data["buffer"] = [f"url{i}" for i in range(15)]

        await show_buffer(update, ctx)

        reply = update.message.reply_text.call_args.args[0]
        assert "and" in reply.lower() and "more" in reply.lower()


# ─── End-to-end happy path ──────────────────────────────────────


class TestEndToEnd:
    async def test_full_steam_flow(self, app: Application, mock_dispatcher: AsyncMock) -> None:
        """/start → /steam → paste → /done → /yes → dispatched."""
        ctx = _make_context(app)

        # 1. /start
        u1 = _make_update("/start")
        assert await start(u1, ctx) == State.CHOOSE

        # 2. /steam
        u2 = _make_update("/steam")
        assert await choose_mode(u2, ctx) == State.COLLECT
        assert ctx.user_data["mode"] == "steam"

        # 3. Paste links
        u3 = _make_update(
            "https://store.steampowered.com/app/440/\nhttps://store.steampowered.com/app/730/"
        )
        assert await collect(u3, ctx) == State.COLLECT
        assert len(ctx.user_data["buffer"]) == 2

        # 4. /done
        u4 = _make_update("/done")
        assert await done(u4, ctx) == State.CONFIRM
        assert len(ctx.user_data["preview"]["steam"]) == 2

        # 5. /yes
        u5 = _make_update("/yes")
        assert await confirm_yes(u5, ctx) == ConversationHandler.END

        # One placeholder sent, one dispatch with both URLs
        assert app.bot.send_message.call_count == 1
        mock_dispatcher.dispatch.assert_called_once()
        call = mock_dispatcher.dispatch.call_args
        assert call.kwargs["repo"] == "user/steam"
        assert len(call.kwargs["links"]) == 2

        # State cleaned up
        assert ctx.user_data == {}

    async def test_full_mixed_flow(self, app: Application, mock_dispatcher: AsyncMock) -> None:
        """/mixed mode dispatches both platforms with separate placeholders."""
        ctx = _make_context(app)

        await start(_make_update("/start"), ctx)
        await choose_mode(_make_update("/mixed"), ctx)
        await collect(
            _make_update(
                "https://store.steampowered.com/app/440/\n"
                "https://x.itch.io/game-a\n"
                "https://store.steampowered.com/app/730/\n"
                "https://y.itch.io/game-b"
            ),
            ctx,
        )
        assert await done(_make_update("/done"), ctx) == State.CONFIRM

        preview = ctx.user_data["preview"]
        assert len(preview["steam"]) == 2
        assert len(preview["itch"]) == 2

        await confirm_yes(_make_update("/yes"), ctx)

        # Two placeholders, two dispatches
        assert app.bot.send_message.call_count == 2
        assert mock_dispatcher.dispatch.call_count == 2

        # Verify each platform got the right URLs
        calls_by_repo = {
            c.kwargs["repo"]: c.kwargs["links"] for c in mock_dispatcher.dispatch.call_args_list
        }
        assert len(calls_by_repo["user/steam"]) == 2
        assert len(calls_by_repo["user/itch"]) == 2
