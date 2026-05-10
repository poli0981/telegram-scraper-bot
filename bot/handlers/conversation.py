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

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.auth import auth
from bot.classifier import (
    LinkKind,
    classify,
    classify_batch,
    dedupe_preserve_order,
    split_by_kind,
    split_inline_urls,
)
from bot.file_parser import (
    FileTooLargeError,
    UnsupportedFileError,
    parse_uploaded_file,
)
from bot.gates import ConcurrencyLock
from bot.handlers.dispatch_flow import gated_dispatch
from bot.preview import (
    format_collect_progress,
    format_preview,
)

log = logging.getLogger(__name__)


class State(IntEnum):
    CHOOSE = 0
    COLLECT = 1
    CONFIRM = 2


# How many lines /show prints before truncating with "and N more"
_BUFFER_SHOW_LIMIT = 10


def _escape_buffer_line(line: str) -> str:
    """Escape backslash and backticks for safe inclusion in a Markdown code span."""
    return line.replace("\\", "\\\\").replace("`", "'")


# Inline keyboard for the mode picker. callback_data routes to bot.handlers.callbacks.mode_callback.
_MODE_KEYBOARD = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton("Steam", callback_data="mode:steam"),
            InlineKeyboardButton("itch", callback_data="mode:itch"),
        ],
        [
            InlineKeyboardButton("Mixed", callback_data="mode:mixed"),
            InlineKeyboardButton("Cancel", callback_data="mode:cancel"),
        ],
    ]
)


# Inline keyboard for the CONFIRM-state preview message.
_CONFIRM_KEYBOARD = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton("✅ Confirm", callback_data="confirm:yes"),
            InlineKeyboardButton("✏️ Edit", callback_data="confirm:edit"),
            InlineKeyboardButton("❌ Cancel", callback_data="confirm:cancel"),
        ]
    ]
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
    """Slash-command mode picker (parallel to the inline button mode_callback).

    Kept so power users can type ``/steam`` directly without tapping a button.
    """
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
        f"/show — peek at buffer · /reset — clear buffer · /cancel — abort.",
        parse_mode=ParseMode.MARKDOWN,
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
        await update.message.reply_text(
            f"❌ Failed to download `{filename}`.", parse_mode=ParseMode.MARKDOWN
        )
        return State.COLLECT

    # Parse
    try:
        new_lines = parse_uploaded_file(filename, bytes(data))
    except FileTooLargeError as e:
        # File-too-large is recoverable: keep the wizard open so the user
        # can split the file and re-upload.
        await update.message.reply_text(f"❌ {e}")
        return State.COLLECT
    except UnsupportedFileError as e:
        # JSON syntax / shape errors are usually a copy-paste mistake on the
        # user's side; cancel the wizard so they don't accumulate stale buffer
        # state and have to re-/start anyway. Releases the lock too just in
        # case it was held (defensive — should not be at this point).
        lock = context.bot_data.get("lock")
        if lock is not None and update.effective_user is not None:
            lock.release(update.effective_user.id)
        context.user_data.clear()
        await update.message.reply_text(
            f"❌ JSON error in `{filename}`: {e}\n\n"
            f"Wizard cancelled. Fix the file and /start again.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return ConversationHandler.END

    if not new_lines:
        await update.message.reply_text(f"⚠ `{filename}` is empty.", parse_mode=ParseMode.MARKDOWN)
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

    Lines are first split on inline URL boundaries (so concatenated-without-
    separator pastes like ``a/440/https://...570/`` become two entries), then
    each piece is classified. Valid URLs are deduplicated against
    ``user_data["seen_urls"]`` so duplicate paste attempts get a live warning
    instead of silently bloating the buffer until /done.

    Invalid lines are appended as-is — no dedupe — so the user can still see
    them at preview time and learn what was wrong.
    """
    buffer: list[str] = context.user_data.setdefault("buffer", [])
    seen_urls: set[str] = context.user_data.setdefault("seen_urls", set())
    config = context.bot_data["config"]

    fresh: list[str] = []
    duplicates = 0
    for line in new_lines:
        for piece in split_inline_urls(line):
            link = classify(piece)
            if link.kind == LinkKind.INVALID:
                fresh.append(piece)
                continue
            if link.url in seen_urls:
                duplicates += 1
                continue
            seen_urls.add(link.url)
            fresh.append(piece)

    available = config.max_links_per_dispatch - len(buffer)
    if available <= 0:
        await update.message.reply_text(
            f"Already at limit ({config.max_links_per_dispatch}). Send /done or /cancel."
        )
        return

    accepted = fresh[:available]
    overflow = len(fresh) - len(accepted)
    buffer.extend(accepted)

    msg_parts = [format_collect_progress(len(buffer), config.max_links_per_dispatch)]
    if duplicates > 0:
        msg_parts.append(f"⚠ {duplicates} duplicate link(s) skipped (already in buffer).")
    if overflow > 0:
        msg_parts.append(f"⚠ {overflow} line(s) dropped (over limit).")

    await update.message.reply_text("\n\n".join(msg_parts))


@auth
async def reset_buffer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Clear the buffer mid-COLLECT without ending the conversation."""
    if not update.message:
        return State.COLLECT
    context.user_data["buffer"] = []
    # Drop the seen-URL set too so previously pasted URLs can be re-added
    # after a reset (otherwise live dedupe would silently swallow them).
    context.user_data["seen_urls"] = set()
    await update.message.reply_text("📥 Buffer cleared. Paste new links or /cancel to abort.")
    return State.COLLECT


@auth
async def show_buffer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Echo the current buffer content for inspection."""
    if not update.message:
        return State.COLLECT

    buffer: list[str] = context.user_data.get("buffer", [])
    config = context.bot_data["config"]

    if not buffer:
        await update.message.reply_text("📥 Buffer is empty. Paste links or /cancel.")
        return State.COLLECT

    sample = buffer[:_BUFFER_SHOW_LIMIT]
    sample_lines = []
    for line in sample:
        truncated = line if len(line) <= 60 else line[:59] + "…"
        sample_lines.append(f"  • `{_escape_buffer_line(truncated)}`")

    overflow = len(buffer) - len(sample)
    msg_lines = [
        f"📥 *{len(buffer)}*/{config.max_links_per_dispatch} buffered:",
        *sample_lines,
    ]
    if overflow > 0:
        msg_lines.append(f"  … and {overflow} more")
    msg_lines.append("")
    msg_lines.append("Send more, /reset to clear, /done to preview.")

    await update.message.reply_text("\n".join(msg_lines), parse_mode=ParseMode.MARKDOWN)
    return State.COLLECT


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
    # Live-dedupe in _extend_buffer should already prevent duplicates from
    # entering the buffer; this count covers the /q quick-add path and any
    # dupes introduced by manual buffer manipulation.
    duplicate_count = len(classified) - len(deduped)
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

    has_valid = bool(steam or itch)
    preview_text = format_preview(
        steam,
        itch,
        invalid,
        mode,
        duplicate_count=duplicate_count,
        inline=has_valid,
    )

    if not has_valid:
        await update.message.reply_text(preview_text, parse_mode=ParseMode.MARKDOWN)
        # No valid links — return to CHOOSE so user can retry without /start
        context.user_data.clear()
        return ConversationHandler.END

    await update.message.reply_text(
        preview_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_CONFIRM_KEYBOARD,
    )
    return State.CONFIRM


# ─── CONFIRM state ──────────────────────────────────────────────


@auth
async def confirm_yes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Dispatch to GitHub Actions via the shared gated_dispatch helper.

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

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    ok, err = await gated_dispatch(
        user_id=user_id,
        chat_id=chat_id,
        steam=preview["steam"],
        itch=preview["itch"],
        bot_data=context.bot_data,
        bot=context.bot,
    )
    if not ok:
        await update.message.reply_text(err or "Dispatch refused.")

    context.user_data.clear()
    return ConversationHandler.END


# ─── /cancel fallback ───────────────────────────────────────────


@auth
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Abort the current conversation. Releases the concurrency lock if held.

    Without this lock release, a user who ran /yes (which acquires the lock) and
    then hit /cancel would still appear "in flight" to gates for up to 10 min.
    """
    lock: ConcurrencyLock | None = context.bot_data.get("lock")
    if lock is not None and update.effective_user is not None:
        lock.release(update.effective_user.id)

    context.user_data.clear()
    if update.message:
        await update.message.reply_text("Cancelled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# ─── Builder ────────────────────────────────────────────────────


def build_conversation_handler() -> ConversationHandler:
    """Construct the ConversationHandler with all entry/state/fallback handlers."""
    # Imported here to avoid a circular import at module load (callbacks.py
    # imports State from this module to map back to the ConversationHandler).
    from bot.handlers.callbacks import confirm_callback, mode_callback

    return ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("scrape", start),
        ],
        states={
            State.CHOOSE: [
                CommandHandler(["steam", "itch", "mixed"], choose_mode),
                CommandHandler("cancel", cancel),
                CallbackQueryHandler(mode_callback, pattern=r"^mode:"),
            ],
            State.COLLECT: [
                CommandHandler("done", done),
                CommandHandler("reset", reset_buffer),
                CommandHandler("show", show_buffer),
                CommandHandler("cancel", cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, collect),
                MessageHandler(filters.Document.ALL, collect_file),
            ],
            State.CONFIRM: [
                CommandHandler("yes", confirm_yes),
                CommandHandler("cancel", cancel),
                CallbackQueryHandler(confirm_callback, pattern=r"^confirm:"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="scraper_conversation",
        persistent=True,
    )
