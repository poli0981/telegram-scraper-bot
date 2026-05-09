"""Callback query handlers for inline keyboards.

Routes by the prefix of ``query.data``:

    quick:yes / quick:cancel       — /q one-shot confirm/cancel
    retry:last / retry:cancel      — /retry confirm/cancel
    retry:platform:steam|itch      — "🔁 Retry" button on a per-platform failure
    confirm:yes / confirm:edit / confirm:cancel — wizard CONFIRM-state buttons
    mode:steam|itch|mixed|cancel   — wizard CHOOSE-state mode picker

All authorized through the ``@auth`` decorator. Any unknown prefix is logged
and acknowledged silently to avoid Telegram client retry loops.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from bot.auth import auth
from bot.handlers.dispatch_flow import gated_dispatch, get_last_dispatch

log = logging.getLogger(__name__)


# ─── /q (one-shot quick) ────────────────────────────────────────


@auth
async def quick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle quick:yes / quick:cancel callbacks."""
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    await query.answer()

    user_id = update.effective_user.id
    pending = context.bot_data.get("pending_quick") or {}
    entry = pending.pop(user_id, None)

    if query.data == "quick:cancel":
        if query.message:
            await query.edit_message_text("❌ Quick dispatch cancelled.")
        return

    # quick:yes
    if entry is None:
        await query.edit_message_text("⚠ Quick dispatch not found (expired). Run /q again.")
        return

    chat_id = update.effective_chat.id if update.effective_chat else None
    if chat_id is None:
        return

    ok, err = await gated_dispatch(
        user_id=user_id,
        chat_id=chat_id,
        steam=entry["steam"],
        itch=entry["itch"],
        bot_data=context.bot_data,
        bot=context.bot,
    )
    if not ok:
        await query.edit_message_text(err or "Dispatch refused.")
    else:
        await query.edit_message_text("🚀 Dispatched. Workflow will edit the placeholder(s) above.")


# ─── /retry ─────────────────────────────────────────────────────


@auth
async def retry_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle retry:* callbacks (last, cancel, platform:<name>)."""
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    await query.answer()

    user_id = update.effective_user.id
    data = query.data or ""

    if data == "retry:cancel":
        await query.edit_message_text("❌ Retry cancelled.")
        return

    chat_id = update.effective_chat.id if update.effective_chat else None
    if chat_id is None:
        return

    entry = get_last_dispatch(context.bot_data, user_id)
    if entry is None:
        await query.edit_message_text("⚠ No recent dispatch to retry (expired or never ran).")
        return

    steam: list[str] = entry["steam"]
    itch: list[str] = entry["itch"]

    if data.startswith("retry:platform:"):
        # Retry only the named platform from last_dispatch
        platform = data.removeprefix("retry:platform:")
        if platform == "steam":
            itch = []
        elif platform == "itch":
            steam = []
        else:
            log.warning("retry_callback: unknown platform=%s", platform)
            return

    if not steam and not itch:
        await query.edit_message_text("⚠ Nothing to retry for that platform.")
        return

    ok, err = await gated_dispatch(
        user_id=user_id,
        chat_id=chat_id,
        steam=steam,
        itch=itch,
        bot_data=context.bot_data,
        bot=context.bot,
    )
    if not ok:
        # The retry button lives on a placeholder — we don't want to wipe its
        # content. Reply with a new message instead.
        await context.bot.send_message(chat_id=chat_id, text=err or "Retry refused.")
        return

    if data == "retry:last":
        await query.edit_message_text("🔁 Retried.")
    # For retry:platform:<name>, leave the original placeholder alone — the
    # new dispatch creates a fresh placeholder via dispatch_one_platform.


# ─── Wizard CONFIRM state (✅ Confirm | ✏️ Edit | ❌ Cancel) ─────


@auth
async def confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    """Handle confirm:* callbacks inside the wizard CONFIRM state."""
    from bot.handlers.conversation import State  # avoid circular import at module load

    query = update.callback_query
    if query is None or update.effective_user is None:
        return None
    await query.answer()

    data = query.data or ""

    if data == "confirm:cancel":
        lock = context.bot_data.get("lock")
        if lock is not None:
            lock.release(update.effective_user.id)
        context.user_data.clear()
        await query.edit_message_text("Cancelled.")
        return ConversationHandler.END

    if data == "confirm:edit":
        await query.edit_message_text(
            "✏️ Edit mode. Buffer kept. Send more links, /reset to clear, or /done."
        )
        return State.COLLECT

    # confirm:yes
    preview = context.user_data.get("preview")
    if not preview:
        await query.edit_message_text("No preview to confirm. /start to retry.")
        return ConversationHandler.END

    chat_id = update.effective_chat.id if update.effective_chat else None
    if chat_id is None:
        return ConversationHandler.END

    user_id = update.effective_user.id
    ok, err = await gated_dispatch(
        user_id=user_id,
        chat_id=chat_id,
        steam=preview["steam"],
        itch=preview["itch"],
        bot_data=context.bot_data,
        bot=context.bot,
    )
    if not ok:
        await context.bot.send_message(chat_id=chat_id, text=err or "Dispatch refused.")

    context.user_data.clear()
    return ConversationHandler.END


# ─── Wizard CHOOSE state (mode picker) ──────────────────────────


@auth
async def mode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    """Handle mode:* callbacks inside the wizard CHOOSE state."""
    from bot.handlers.conversation import State

    query = update.callback_query
    if query is None or update.effective_user is None:
        return None
    await query.answer()

    data = query.data or ""
    cmd = data.removeprefix("mode:")

    if cmd == "cancel":
        context.user_data.clear()
        await query.edit_message_text("Cancelled.")
        return ConversationHandler.END

    if cmd not in ("steam", "itch", "mixed"):
        log.warning("mode_callback: unexpected data=%s", data)
        return None

    context.user_data["mode"] = cmd
    context.user_data["buffer"] = []

    config = context.bot_data["config"]
    await query.edit_message_text(
        f"Mode: *{cmd}*\n\n"
        f"Paste links (1 per line, max *{config.max_links_per_dispatch}*).\n"
        f"You can send multiple messages, or upload a `.txt` / `.json` file.\n"
        f"When done, send /done.\n\n"
        f"/show — peek at buffer · /reset — clear buffer · /cancel — abort.",
        parse_mode="Markdown",
    )
    return State.COLLECT
