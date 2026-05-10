"""/q — one-shot quick dispatch.

Bypasses the wizard. User types ``/q url1 url2 …``; bot classifies, shows a
preview with inline ✅/❌ buttons, and dispatches on confirm.

Mode is implicit "mixed" — the classifier figures out per-URL routing.
"""

from __future__ import annotations

import logging
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from bot.auth import auth
from bot.classifier import (
    classify_batch,
    dedupe_preserve_order,
    split_by_kind,
)
from bot.preview import format_preview

log = logging.getLogger(__name__)


_USAGE = (
    "Usage: `/q <url1> <url2> …`\n"
    "Example: `/q https://store.steampowered.com/app/440/`\n"
    "Bypasses the wizard. Mode = mixed."
)


@auth
async def quick_dispatch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Parse args, classify, and prompt for confirmation with inline buttons."""
    if not update.message or not update.effective_user:
        return

    args = context.args or []
    if not args:
        await update.message.reply_text(_USAGE, parse_mode=ParseMode.MARKDOWN)
        return

    config = context.bot_data["config"]
    user_id = update.effective_user.id

    classified = classify_batch("\n".join(args))
    deduped = dedupe_preserve_order(classified)
    duplicate_count = len(classified) - len(deduped)
    steam, itch, invalid = split_by_kind(deduped)

    if not steam and not itch:
        await update.message.reply_text(
            f"⚠ No valid links in {len(args)} arg(s). "
            "Steam URLs, itch.io URLs, or bare appids only."
        )
        return

    total = len(steam) + len(itch)
    if total > config.max_links_per_dispatch:
        await update.message.reply_text(
            f"⚠ Too many links ({total} > {config.max_links_per_dispatch}). "
            "Use the wizard /start for batched uploads."
        )
        return

    # Stash payload by user_id; clobbers any prior pending /q.
    pending = context.bot_data.setdefault("pending_quick", {})
    pending[user_id] = {
        "steam": list(steam),
        "itch": list(itch),
        "ts": time.time(),
    }

    preview_text = format_preview(
        steam,
        itch,
        invalid,
        "mixed",
        duplicate_count=duplicate_count,
        inline=True,
    )
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Send", callback_data="quick:yes"),
                InlineKeyboardButton("❌ Cancel", callback_data="quick:cancel"),
            ]
        ]
    )
    await update.message.reply_text(
        preview_text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard
    )
