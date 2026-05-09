"""Conversation handler — main wizard flow.

States:
    CHOOSE  — user picks /steam, /itch, or /mixed
    COLLECT — user pastes links; /done to advance
    CONFIRM — preview shown; /yes to dispatch, /cancel to abort

The handler reads `context.bot_data["dispatcher"]` and `["config"]`, set in
main.py at boot. user_data tracks per-conversation state (mode, buffer).
"""

from __future__ import annotations

import logging
from enum import IntEnum
from typing import TYPE_CHECKING

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.constants import ParseMode
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.auth import auth
from bot.classifier import (
    LinkKind,
    classify_batch,
    dedupe_preserve_order,
    split_by_kind,
)
from bot.file_parser import (
    FileTooLargeError,
    UnsupportedFileError,
    parse_uploaded_file,
)
from bot.gates import ConcurrencyLock, RateLimit, format_retry_after
from bot.preview import (
    format_collect_progress,
    format_preview,
)

if TYPE_CHECKING:
    from bot.dispatcher import Dispatcher


log = logging.getLogger(__name__)


class State(IntEnum):
    CHOOSE = 0
    COLLECT = 1
    CONFIRM = 2


# Keyboards
_MODE_KEYBOARD = ReplyKeyboardMarkup(
    [["/steam", "/itch"], ["/mixed", "/cancel"]],
    resize_keyboard=True,
    one_time_keyboard=True,
)


# ─── /start, /scrape entry ──────────────────────────────────────


@auth
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point. Show mode picker."""
    context.user_data.clear()
    if update.message:
        await update.message.reply_text(
            "Pick scraper mode:\n"
            "• /steam — Steam links only\n"
            "• /itch — itch.io links only\n"
            "• /mixed — auto-route by URL\n"
            "• /cancel — abort",
            reply_markup=_MODE_KEYBOARD,
        )
    return State.CHOOSE


# ─── CHOOSE state ───────────────────────────────────────────────


@auth
async def choose_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User picked a mode. Save it, advance to COLLECT."""
    if not update.message or not update.message.text:
        return State.CHOOSE

    cmd = update.message.text.lstrip("/").lower().strip()
    if cmd not in ("steam", "itch", "mixed"):
        await update.message.reply_text("Pick /steam, /itch, or /mixed.")
        return State.CHOOSE

    context.user_data["mode"] = cmd
    context.user_data["buffer"] = []

    config = context.bot_data["config"]
    await update.message.reply_text(
        f"Mode: *{cmd}*\n\n"
        f"Paste links (1 per line, max *{config.max_links_per_dispatch}*).\n"
        f"You can send multiple messages, or upload a `.txt` / `.json` file.\n"
        f"When done, send /done.\n\n"
        f"Or /cancel to abort.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardRemove(),
    )
    return State.COLLECT


# ─── COLLECT state ──────────────────────────────────────────────


@auth
async def collect(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Accumulate text into the buffer until /done."""
    if not update.message or not update.message.text:
        return State.COLLECT

    new_lines = [line for line in update.message.text.splitlines() if line.strip()]
    await _extend_buffer(update, context, new_lines)
    return State.COLLECT


@auth
async def collect_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Accept .txt or .json file uploads as a batch of links.

    The file is downloaded into memory (capped at MAX_FILE_SIZE), parsed, then
    appended to the buffer just like a text paste.
    """
    if not update.message or not update.message.document:
        return State.COLLECT

    doc = update.message.document
    filename = doc.file_name or "upload"

    # Quick reject: anything that's not text/json
    name_lower = filename.lower()
    if not (name_lower.endswith(".txt") or name_lower.endswith(".json")):
        await update.message.reply_text(
            f"❌ Unsupported file type: `{filename}`. Use .txt or .json.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return State.COLLECT

    # Download bytes
    try:
        tg_file = await doc.get_file()
        data = await tg_file.download_as_bytearray()
    except Exception as e:  # noqa: BLE001 — Telegram errors are varied
        log.warning("collect_file: download failed: %s", e)
        await update.message.reply_text(f"❌ Failed to download `{filename}`.",
                                         parse_mode=ParseMode.MARKDOWN)
        return State.COLLECT

    # Parse
    try:
        new_lines = parse_uploaded_file(filename, bytes(data))
    except FileTooLargeError as e:
        await update.message.reply_text(f"❌ {e}")
        return State.COLLECT
    except UnsupportedFileError as e:
        await update.message.reply_text(f"❌ Failed to parse `{filename}`: {e}",
                                         parse_mode=ParseMode.MARKDOWN)
        return State.COLLECT

    if not new_lines:
        await update.message.reply_text(f"⚠ `{filename}` is empty.",
                                         parse_mode=ParseMode.MARKDOWN)
        return State.COLLECT

    await _extend_buffer(update, context, new_lines)
    return State.COLLECT


async def _extend_buffer(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    new_lines: list[str],
) -> None:
    """Append new_lines to the buffer, respecting max-link cap, and reply.

    Shared by both text-paste and file-upload paths.
    """
    buffer: list[str] = context.user_data.setdefault("buffer", [])
    config = context.bot_data["config"]
    available = config.max_links_per_dispatch - len(buffer)

    if available <= 0:
        await update.message.reply_text(
            f"Already at limit ({config.max_links_per_dispatch}). Send /done or /cancel."
        )
        return

    accepted = new_lines[:available]
    overflow = len(new_lines) - len(accepted)
    buffer.extend(accepted)

    msg = format_collect_progress(len(buffer), config.max_links_per_dispatch)
    if overflow > 0:
        msg += f"\n\n⚠ {overflow} line(s) dropped (over limit)."

    await update.message.reply_text(msg)


@auth
async def done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User finished collecting. Classify, dedupe, show preview."""
    if not update.message:
        return State.COLLECT

    buffer: list[str] = context.user_data.get("buffer", [])
    mode: str = context.user_data.get("mode", "mixed")

    if not buffer:
        await update.message.reply_text("Nothing buffered yet. Paste links or /cancel.")
        return State.COLLECT

    raw_text = "\n".join(buffer)
    classified = classify_batch(raw_text)
    deduped = dedupe_preserve_order(classified)
    steam, itch, invalid = split_by_kind(deduped)

    # Filter by mode
    if mode == "steam":
        # itch URLs in steam mode become invalid
        for link in deduped:
            if link.kind == LinkKind.ITCH:
                invalid.append(link)
        itch = []
    elif mode == "itch":
        for link in deduped:
            if link.kind == LinkKind.STEAM:
                invalid.append(link)
        steam = []
    # mixed: keep both

    # Persist for /yes
    context.user_data["preview"] = {
        "mode": mode,
        "steam": steam,
        "itch": itch,
        "invalid_count": len(invalid),
    }

    preview_text = format_preview(steam, itch, invalid, mode)
    await update.message.reply_text(preview_text, parse_mode=ParseMode.MARKDOWN)

    if not steam and not itch:
        # No valid links — return to CHOOSE so user can retry without /start
        context.user_data.clear()
        return ConversationHandler.END

    return State.CONFIRM


# ─── CONFIRM state ──────────────────────────────────────────────


async def _dispatch_one_platform(
    *,
    platform: str,
    repo: str,
    links: list[str],
    chat_id: int,
    bot,
    dispatcher: Dispatcher,
) -> None:
    """Send a placeholder message and dispatch one platform's workflow.

    Posts `⏳ {platform}: dispatching N links...` first, then calls the
    dispatcher with that message's ID. On dispatch failure, edits the
    placeholder with the error so the user sees it immediately rather than
    waiting for a workflow that never started.

    On success, leaves the placeholder alone — the running workflow will
    `editMessageText` it with the final result in 1–8 minutes.
    """
    placeholder = await bot.send_message(
        chat_id=chat_id,
        text=f"⏳ *{platform}*: dispatching {len(links)} link(s)...",
        parse_mode=ParseMode.MARKDOWN,
    )

    result = await dispatcher.dispatch(
        repo=repo,
        links=links,
        chat_id=chat_id,
        message_id=placeholder.message_id,
    )

    if result.ok:
        log.info("dispatch %s ok: repo=%s links=%d msg=%d",
                 platform, repo, len(links), placeholder.message_id)
        return

    log.warning("dispatch %s failed: repo=%s status=%d err=%s",
                platform, repo, result.status_code, result.error)
    error_text = (
        f"❌ *{platform}*: dispatch failed\n"
        f"`HTTP {result.status_code}`\n"
        f"`{result.error or 'unknown error'}`"
    )
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=placeholder.message_id,
            text=error_text,
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:  # pragma: no cover — defensive
        log.warning("edit_message_text after dispatch failure failed: %s", e)


@auth
async def confirm_yes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Dispatch to GitHub Actions — separate placeholder per platform.

    Protected by two gates:
      1. ConcurrencyLock: at most one in-flight dispatch per user.
      2. RateLimit: sliding window per-user + global cap.
    """
    if not update.message:
        return State.CONFIRM

    preview = context.user_data.get("preview")
    if not preview:
        await update.message.reply_text("No preview to confirm. /start to retry.")
        return ConversationHandler.END

    config = context.bot_data["config"]
    dispatcher: Dispatcher = context.bot_data["dispatcher"]
    lock: ConcurrencyLock = context.bot_data["lock"]
    rate_limit: RateLimit = context.bot_data["rate_limit"]

    user_id = update.effective_user.id

    # Gate 1: rate limit (cheap check, fail fast)
    decision = rate_limit.check(user_id)
    if not decision.allowed:
        scope = "your" if decision.reason == "user" else "global"
        await update.message.reply_text(
            f"⏳ Rate limit reached ({scope}). Try again in {format_retry_after(decision.retry_after)}."
        )
        context.user_data.clear()
        return ConversationHandler.END

    # Gate 2: concurrency lock
    if not lock.try_acquire(user_id):
        await update.message.reply_text(
            "⏳ You already have a dispatch in flight. Wait for it to finish "
            "(or up to 10 min for stale locks)."
        )
        context.user_data.clear()
        return ConversationHandler.END

    # Both gates passed — dispatch under try/finally so lock is always released
    try:
        steam: list[str] = preview["steam"]
        itch: list[str] = preview["itch"]
        chat_id = update.effective_chat.id

        if steam:
            await _dispatch_one_platform(
                platform="Steam",
                repo=config.steam_repo,
                links=steam,
                chat_id=chat_id,
                bot=context.bot,
                dispatcher=dispatcher,
            )

        if itch:
            await _dispatch_one_platform(
                platform="itch",
                repo=config.itch_repo,
                links=itch,
                chat_id=chat_id,
                bot=context.bot,
                dispatcher=dispatcher,
            )

        # Record against rate limit only after dispatch completes (success or
        # transport-level failure both count — they consumed an Actions slot).
        rate_limit.record(user_id)
    finally:
        lock.release(user_id)

    context.user_data.clear()
    return ConversationHandler.END


# ─── /cancel fallback ───────────────────────────────────────────


@auth
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Abort the current conversation."""
    context.user_data.clear()
    if update.message:
        await update.message.reply_text(
            "Cancelled.", reply_markup=ReplyKeyboardRemove()
        )
    return ConversationHandler.END


# ─── Builder ────────────────────────────────────────────────────


def build_conversation_handler() -> ConversationHandler:
    """Construct the ConversationHandler with all entry/state/fallback handlers."""
    return ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("scrape", start),
        ],
        states={
            State.CHOOSE: [
                CommandHandler(["steam", "itch", "mixed"], choose_mode),
                CommandHandler("cancel", cancel),
            ],
            State.COLLECT: [
                CommandHandler("done", done),
                CommandHandler("cancel", cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, collect),
                MessageHandler(filters.Document.ALL, collect_file),
            ],
            State.CONFIRM: [
                CommandHandler("yes", confirm_yes),
                CommandHandler("cancel", cancel),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="scraper_conversation",
        persistent=True,
    )
