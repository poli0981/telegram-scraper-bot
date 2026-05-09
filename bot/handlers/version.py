"""/version — bot metadata for diagnostics."""

from __future__ import annotations

import logging
import sys

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from bot import __version__
from bot.auth import auth
from bot.config import Config

log = logging.getLogger(__name__)


@auth
async def version_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reply with package version, git SHA, Python version, workflow target."""
    if not update.message:
        return

    config: Config = context.bot_data["config"]
    py_ver = sys.version.split()[0]

    text = (
        "*Bot version*\n"
        "\n"
        f"Package: `{__version__}`\n"
        f"Git SHA: `{config.git_sha}`\n"
        f"Python: `{py_ver}`\n"
        f"Workflow: `{config.workflow_file}@{config.workflow_ref}`"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
