"""/status — show quota and lock state for the calling user."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from bot.auth import auth
from bot.gates import ConcurrencyLock, RateLimit, format_retry_after

log = logging.getLogger(__name__)


@auth
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Render the user's current dispatch state, rate-limit quota, and buffer size."""
    if not update.message or not update.effective_user:
        return

    user_id = update.effective_user.id
    lock: ConcurrencyLock = context.bot_data["lock"]
    rate_limit: RateLimit = context.bot_data["rate_limit"]

    held = lock.is_held(user_id)
    rem = rate_limit.remaining(user_id)

    user_left = max(0, rem.user_max - rem.user_used)
    global_left = max(0, rem.global_max - rem.global_used)

    lines = [
        "*Status*",
        "",
        f"Dispatch: {'⏳ in flight' if held else '🟢 idle'}",
        f"Your quota: *{user_left}*/{rem.user_max} left "
        f"(window {format_retry_after(rem.user_window)})",
    ]
    if rem.user_used > 0:
        lines.append(f"  Resets in: {format_retry_after(rem.user_reset_in)}")
    lines.append(
        f"Global quota: *{global_left}*/{rem.global_max} left "
        f"(window {format_retry_after(rem.global_window)})"
    )

    buffer = context.user_data.get("buffer") if context.user_data else None
    if buffer:
        lines.append("")
        lines.append(f"Buffer: *{len(buffer)}* line(s) (in wizard)")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
