"""/whoami — print the caller's Telegram user_id and authorization status.

Intentionally **not** wrapped in ``@auth``: a brand-new user who isn't yet on
the allow-list needs a way to discover their own numeric ID without resorting
to @userinfobot. /whoami is read-only, leaks nothing sensitive (the caller
already knows their own ID), and is the lowest-friction path from "I joined
the chat" to "operator added me to ALLOWED_USER_IDS".
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

log = logging.getLogger(__name__)


async def whoami_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reply with user_id, name, and authorization status. Skips @auth on purpose."""
    if not update.message or not update.effective_user:
        return

    user = update.effective_user
    config = context.bot_data.get("config")
    is_authorized = config is not None and user.id in config.allowed_user_ids

    lines = [
        "*whoami*",
        "",
        f"User ID: `{user.id}`",
        f"Name: {user.first_name}",
    ]
    if user.username:
        lines.append(f"Username: @{user.username}")
    lines.append(f"Authorized: {'✅ yes' if is_authorized else '❌ no'}")
    if not is_authorized:
        lines.append("")
        lines.append("Add this ID to `ALLOWED_USER_IDS` in your `.env` to use the bot.")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
