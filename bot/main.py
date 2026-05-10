"""Bot entry point. Run with: `python -m bot.main`

PERSISTENCE GOTCHA — read this before refactoring:

    PicklePersistence loads `bot_data` from disk during post_init, REPLACING
    whatever we set via `app.bot_data[...] = ...` in build_application.
    Anything that must survive that reload (config, http client, gates) MUST
    be either:
      • captured via closure in the post_init hook (preferred for static
        config), or
      • set INSIDE post_init AFTER persistence has loaded (for runtime
        resources like the httpx client).
    Setting at build_application time and reading in post_init = KeyError.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from collections.abc import Awaitable, Callable

import httpx
from telegram import BotCommand
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    PicklePersistence,
)

from bot.config import Config, ConfigError
from bot.dispatcher import Dispatcher
from bot.gates import ConcurrencyLock, RateLimit
from bot.handlers.callbacks import quick_callback, retry_callback
from bot.handlers.conversation import build_conversation_handler
from bot.handlers.error import error_handler
from bot.handlers.help import help_command
from bot.handlers.retry import retry_command
from bot.handlers.shortcuts import quick_dispatch
from bot.handlers.status import status_command
from bot.handlers.version import version_command
from bot.handlers.whoami import whoami_command

log = logging.getLogger(__name__)


# Bot data keys — also referenced by handlers in conversation.py
_KEY_CONFIG = "config"
_KEY_HTTP_CLIENT = "http_client"
_KEY_DISPATCHER = "dispatcher"
_KEY_LOCK = "lock"
_KEY_RATE_LIMIT = "rate_limit"

# How long _post_shutdown waits for in-flight dispatches before forcing exit
_SHUTDOWN_GRACE_SECONDS = 30.0

# Slash commands surfaced to Telegram clients via setMyCommands
_BOT_COMMANDS = [
    BotCommand("start", "Start the wizard"),
    BotCommand("q", "Quick dispatch: /q <url1> <url2> ..."),
    BotCommand("retry", "Replay last dispatch"),
    BotCommand("status", "Quota + lock state"),
    BotCommand("whoami", "Show your user ID + auth status"),
    BotCommand("help", "List commands"),
    BotCommand("version", "Bot metadata"),
    BotCommand("cancel", "Cancel wizard"),
]


def _make_post_init(config: Config) -> Callable[[Application], Awaitable[None]]:
    """Build a post_init hook that closes over `config`.

    Why closure: PicklePersistence overwrites bot_data on post_init, so we
    can't pre-stuff config there. The closure keeps it accessible without
    needing bot_data as a transport mechanism.
    """

    async def _post_init(application: Application) -> None:
        # Persistence has now loaded; safe to set runtime resources.
        client = httpx.AsyncClient()
        dispatcher = Dispatcher(
            client=client,
            gh_pat=config.gh_pat,
            workflow_file=config.workflow_file,
            ref=config.workflow_ref,
        )

        # Always overwrite — even if pickle held stale entries from an old run,
        # we want fresh runtime objects (httpx client, dispatcher, gates).
        application.bot_data[_KEY_CONFIG] = config
        application.bot_data[_KEY_HTTP_CLIENT] = client
        application.bot_data[_KEY_DISPATCHER] = dispatcher
        application.bot_data[_KEY_LOCK] = ConcurrencyLock()
        application.bot_data[_KEY_RATE_LIMIT] = RateLimit(
            user_max=config.rate_limit_user_max,
            user_window=float(config.rate_limit_user_window),
            global_max=config.rate_limit_global_max,
            global_window=float(config.rate_limit_global_window),
        )
        # Initialize the dicts that /retry and /q populate, in case this is
        # the first run and the pickle hasn't seeded them yet.
        application.bot_data.setdefault("last_dispatch", {})
        application.bot_data.setdefault("pending_quick", {})

        log.info(
            "post_init: config + dispatcher + gates attached "
            "(rate=%d/%ds user, %d/%ds global, sha=%s)",
            config.rate_limit_user_max,
            config.rate_limit_user_window,
            config.rate_limit_global_max,
            config.rate_limit_global_window,
            config.git_sha,
        )

        # Verify BOT_TOKEN by hitting getMe. Catches "you typed the wrong
        # token" failures at boot instead of waiting for the first /start.
        # Re-raises so a bad token aborts startup loudly rather than running
        # a zombie process that can't actually talk to Telegram.
        try:
            me = await application.bot.get_me()
            log.info(
                "post_init: connected as @%s (id=%d, name=%s)",
                me.username,
                me.id,
                me.first_name,
            )
        except Exception as e:
            log.error("post_init: getMe failed — BOT_TOKEN likely invalid: %s", e)
            raise

        # Surface commands to the Telegram client (idempotent — safe to retry).
        try:
            await application.bot.set_my_commands(_BOT_COMMANDS)
            await application.bot.set_my_short_description(
                "Dispatch Steam/itch.io scrapers via GitHub Actions"
            )
            await application.bot.set_my_description(
                "Paste links → preview → dispatch. Type /help for commands."
            )
            log.info("post_init: setMyCommands + descriptions registered")
        except Exception as e:  # noqa: BLE001 — don't crash startup over UI metadata
            log.warning("post_init: failed to set bot commands/description: %s", e)

    return _post_init


async def _post_shutdown(application: Application) -> None:
    """Wait briefly for in-flight dispatches, then close the httpx client.

    Without the wait, a SIGTERM mid-dispatch would race the httpx client close
    against the pending POST → likely transport error logged for no good reason.
    """
    lock: ConcurrencyLock | None = application.bot_data.get(_KEY_LOCK)
    # `_holders` is a private attribute; access is intentional because we own
    # ConcurrencyLock and prefer this over adding a public count() method that
    # only this code path needs.
    if lock is not None and lock._holders:
        log.info(
            "post_shutdown: waiting up to %.0fs for %d in-flight dispatch(es)",
            _SHUTDOWN_GRACE_SECONDS,
            len(lock._holders),
        )
        deadline = time.monotonic() + _SHUTDOWN_GRACE_SECONDS
        while lock._holders and time.monotonic() < deadline:
            await asyncio.sleep(0.5)
        if lock._holders:
            log.warning(
                "post_shutdown: %d dispatch(es) still in flight at shutdown",
                len(lock._holders),
            )

    client: httpx.AsyncClient | None = application.bot_data.get(_KEY_HTTP_CLIENT)
    if client is not None:
        await client.aclose()
        log.info("post_shutdown: httpx client closed")


def build_application(config: Config) -> Application:
    """Construct the PTB Application. Separated for testability."""
    # Ensure persistence directory exists
    config.persistence_path.parent.mkdir(parents=True, exist_ok=True)
    persistence = PicklePersistence(filepath=config.persistence_path)

    app = (
        ApplicationBuilder()
        .token(config.bot_token)
        .post_init(_make_post_init(config))
        .post_shutdown(_post_shutdown)
        .persistence(persistence)
        .build()
    )
    # NOTE: do NOT set bot_data here — see PERSISTENCE GOTCHA at top of file.
    # bot_data is populated inside the post_init closure above.

    # Conversation handler comes first so its CommandHandlers (e.g. /cancel
    # within a state) win over global ones.
    app.add_handler(build_conversation_handler())

    # Global commands available outside any conversation. Kept on the default
    # handler group, registered after the ConversationHandler so an in-progress
    # wizard's /cancel still wins.
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("version", version_command))
    app.add_handler(CommandHandler("q", quick_dispatch))
    app.add_handler(CommandHandler("retry", retry_command))
    # /whoami is intentionally registered without auth so unauthorized users
    # can self-discover their user_id for ALLOWED_USER_IDS configuration.
    app.add_handler(CommandHandler("whoami", whoami_command))

    # Global callback handlers for inline buttons that originate outside the
    # ConversationHandler (or that need to fire even when the user has no
    # active conversation — e.g., the "🔁 Retry" button on a dispatch failure).
    app.add_handler(CallbackQueryHandler(quick_callback, pattern=r"^quick:"))
    app.add_handler(CallbackQueryHandler(retry_callback, pattern=r"^retry:"))

    app.add_error_handler(error_handler)
    return app


def main() -> int:
    """Boot the bot. Returns process exit code."""
    try:
        config = Config.load()
    except ConfigError as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return 2

    config.setup_logging()
    log.info(
        "Booting telegram-scraper-bot (allowed=%d steam=%s itch=%s)",
        len(config.allowed_user_ids),
        config.steam_repo,
        config.itch_repo,
    )

    app = build_application(config)
    app.run_polling(allowed_updates=["message", "callback_query"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
