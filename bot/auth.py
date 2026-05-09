"""Authorization decorator for Telegram handlers.

Wraps async handlers to early-exit when the caller isn't on the allow-list.
Pulls the allow-list from `context.bot_data["config"]` so handlers stay testable.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes


log = logging.getLogger(__name__)

Handler = Callable[["Update", "ContextTypes.DEFAULT_TYPE"], Awaitable[Any]]


def auth(handler: Handler) -> Handler:
    """Decorator: only run handler if user_id is in the configured allow-list.

    Reads `context.bot_data["config"]` (set in main.py) to find allowed IDs.
    Unauthorized users get a single short reply and the handler is skipped.
    """

    @wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
        user = update.effective_user
        config = context.bot_data.get("config")

        if config is None:
            # Fail closed — never run a handler if config is missing
            log.error("auth: config not loaded into bot_data; rejecting all requests")
            return None

        if user is None or user.id not in config.allowed_user_ids:
            log.warning(
                "auth: rejected user_id=%s username=%s",
                user.id if user else None,
                user.username if user else None,
            )
            if update.message:
                await update.message.reply_text("⛔ Not authorized.")
            return None

        return await handler(update, context)

    return wrapper
