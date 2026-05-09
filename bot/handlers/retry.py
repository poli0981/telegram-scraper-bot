"""/retry — replay the user's most recent dispatch.

Looks up ``bot_data["last_dispatch"][user_id]``; if the entry is fresh enough
(< 30 min old), shows a preview with ✅/❌ inline buttons. Confirming runs
through the same gated_dispatch helper as /yes and /q.
"""

from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from bot.auth import auth
from bot.classifier import ClassifiedLink
from bot.handlers.dispatch_flow import LAST_DISPATCH_TTL_SECONDS, get_last_dispatch
from bot.preview import format_preview

log = logging.getLogger(__name__)


@auth
async def retry_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the last-dispatch preview with confirm buttons."""
    if not update.message or not update.effective_user:
        return

    user_id = update.effective_user.id
    entry = get_last_dispatch(context.bot_data, user_id)
    if entry is None:
        ttl_min = LAST_DISPATCH_TTL_SECONDS // 60
        await update.message.reply_text(
            f"No dispatch to retry in the last {ttl_min} min. Use /start or /q first."
        )
        return

    steam: list[str] = entry["steam"]
    itch: list[str] = entry["itch"]
    invalid: list[ClassifiedLink] = []  # everything in last_dispatch was already valid

    preview_text = format_preview(steam, itch, invalid, "mixed", inline=True)
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Confirm retry", callback_data="retry:last"),
                InlineKeyboardButton("❌ Cancel", callback_data="retry:cancel"),
            ]
        ]
    )
    await update.message.reply_text(
        f"🔁 Replaying last dispatch:\n\n{preview_text}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard,
    )
