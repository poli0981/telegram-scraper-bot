"""Global error handler for unhandled exceptions in handlers.

Registered via ``Application.add_error_handler``. Logs full traceback then
sends the user a brief, non-leaky error message.
"""

from __future__ import annotations

import logging
import traceback
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telegram.ext import ContextTypes


log = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Catch-all for unhandled exceptions raised inside handlers.

    PTB passes the original update (which may be None for non-update errors)
    and a context whose ``error`` attribute holds the exception. We log the
    full traceback for ourselves and send the user a generic notice.

    Never raises — must be a true sink.
    """
    err = context.error
    if err is None:  # pragma: no cover — defensive
        return

    # Log full traceback for ourselves
    tb = "".join(traceback.format_exception(type(err), err, err.__traceback__))
    log.error("Unhandled exception in handler:\n%s", tb)

    # Tell the user something brief — never leak the exception text or stack
    try:
        # update may be a Telegram Update or any other object; only handle
        # the case where we have a chat to reply to
        from telegram import Update as TGUpdate

        if isinstance(update, TGUpdate) and update.effective_message is not None:
            await update.effective_message.reply_text(
                "⚠ Internal error. The team has been notified. /cancel and try again."
            )
    except Exception as e:  # noqa: BLE001 — error handler must never raise
        log.error("error_handler failed to notify user: %s", e)
