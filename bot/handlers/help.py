"""/help — list all available commands.

Registered as a global handler so it works inside or outside the wizard.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from bot.auth import auth

log = logging.getLogger(__name__)


_HELP_TEXT = (
    "*telegram-scraper-bot — commands*\n"
    "\n"
    "*Wizard*\n"
    "• /start — pick mode → paste links → /done → /yes\n"
    "• /scrape — alias for /start\n"
    "• /done — finish collecting links (in COLLECT)\n"
    "• /yes — confirm and dispatch (in CONFIRM)\n"
    "• /reset — clear buffer, stay in COLLECT\n"
    "• /show — preview current buffer\n"
    "• /cancel — abort the wizard at any time\n"
    "\n"
    "*Quick*\n"
    "• /q `<url1> <url2> …` — one-shot dispatch, bypass wizard\n"
    "• /retry — replay your last dispatch (within 30 min)\n"
    "\n"
    "*Diagnostics*\n"
    "• /status — quota + lock state\n"
    "• /version — bot metadata (git SHA, Python, workflow ref)\n"
    "• /whoami — show your Telegram user ID + auth status\n"
    "• /help — this message\n"
    "\n"
    "Flow: `/start → /steam|/itch|/mixed → paste links → /done → /yes`"
)


@auth
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reply with the command list. Does not affect conversation state."""
    if update.message:
        await update.message.reply_text(_HELP_TEXT, parse_mode=ParseMode.MARKDOWN)
