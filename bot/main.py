"""Bot entry point. Run with: `python -m bot.main`"""

from __future__ import annotations

import logging
import sys

from bot.config import Config, ConfigError

log = logging.getLogger(__name__)


def main() -> int:
    """Boot the bot. Returns process exit code."""
    try:
        config = Config.load()
    except ConfigError as e:
        # Logging not yet configured — write to stderr directly
        print(f"FATAL: {e}", file=sys.stderr)
        return 2

    config.setup_logging()
    log.info("Booting telegram-scraper-bot (allowed users: %d)", len(config.allowed_user_ids))

    # TODO(phase-1): build Application, attach ConversationHandler, run_polling()
    log.warning("Phase 0 skeleton — handlers not yet wired. Exiting.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
