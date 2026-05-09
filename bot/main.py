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

import logging
import sys
from collections.abc import Awaitable, Callable

import httpx
from telegram.ext import Application, ApplicationBuilder, PicklePersistence

from bot.config import Config, ConfigError
from bot.dispatcher import Dispatcher
from bot.gates import ConcurrencyLock, RateLimit
from bot.handlers.conversation import build_conversation_handler
from bot.handlers.error import error_handler

log = logging.getLogger(__name__)


# Bot data keys — also referenced by handlers in conversation.py
_KEY_CONFIG = "config"
_KEY_HTTP_CLIENT = "http_client"
_KEY_DISPATCHER = "dispatcher"
_KEY_LOCK = "lock"
_KEY_RATE_LIMIT = "rate_limit"


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
        log.info(
            "post_init: config + dispatcher + gates attached "
            "(rate=%d/%ds user, %d/%ds global)",
            config.rate_limit_user_max,
            config.rate_limit_user_window,
            config.rate_limit_global_max,
            config.rate_limit_global_window,
        )

    return _post_init


async def _post_shutdown(application: Application) -> None:
    """Clean up the httpx client on shutdown."""
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
    app.add_handler(build_conversation_handler())
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
    app.run_polling(allowed_updates=["message"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
