"""Shared gate-protected dispatch flow.

Used by:
    - confirm_yes (the /yes wizard handler)
    - /q one-shot quick dispatch
    - /retry replay handler
    - "🔁 Retry" inline button after a dispatch failure

Centralizes gate-checking (rate limit + concurrency lock), per-platform dispatch,
and last-dispatch bookkeeping so all entry points behave identically.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from bot.gates import ConcurrencyLock, RateLimit, format_retry_after

if TYPE_CHECKING:
    from bot.dispatcher import Dispatcher

log = logging.getLogger(__name__)


# How long a saved last_dispatch payload remains usable for /retry. Wall clock,
# so it survives bot restarts (PicklePersistence persists bot_data).
LAST_DISPATCH_TTL_SECONDS = 1800  # 30 minutes


@dataclass(slots=True, frozen=True)
class GateDecision:
    """Outcome of the gate check before a dispatch is attempted."""

    ok: bool
    user_message: str | None = None  # Set when ok=False, ready to send to user.


def check_gates(
    *,
    user_id: int,
    bot_data: dict[str, Any],
) -> GateDecision:
    """Run rate-limit + concurrency-lock checks. Does NOT acquire the lock.

    Caller must call ``lock.try_acquire(user_id)`` separately if proceeding.
    Splitting check from acquire lets us reject without polluting state.
    """
    rate_limit: RateLimit = bot_data["rate_limit"]
    lock: ConcurrencyLock = bot_data["lock"]

    decision = rate_limit.check(user_id)
    if not decision.allowed:
        scope = "your" if decision.reason == "user" else "global"
        msg = (
            f"⏳ Rate limit reached ({scope}). "
            f"Try again in {format_retry_after(decision.retry_after)}."
        )
        return GateDecision(ok=False, user_message=msg)

    if lock.is_held(user_id):
        return GateDecision(
            ok=False,
            user_message=(
                "⏳ You already have a dispatch in flight. Wait for it to finish "
                "(or up to 10 min for stale locks)."
            ),
        )

    return GateDecision(ok=True)


async def dispatch_one_platform(
    *,
    platform: str,
    repo: str,
    links: list[str],
    chat_id: int,
    bot: Any,
    dispatcher: Dispatcher,
) -> bool:
    """Send a placeholder message and dispatch one platform's workflow.

    Posts ``⏳ {platform}: dispatching N links...`` first, then calls the
    dispatcher with that message's ID. On dispatch failure, edits the
    placeholder with the error and an inline "🔁 Retry" button.

    Returns True on successful dispatch (HTTP 204 from GitHub), False otherwise.
    """
    placeholder = await bot.send_message(
        chat_id=chat_id,
        text=f"⏳ *{platform}*: dispatching {len(links)} link(s)...",
        parse_mode=ParseMode.MARKDOWN,
    )

    result = await dispatcher.dispatch(
        repo=repo,
        links=links,
        chat_id=chat_id,
        message_id=placeholder.message_id,
    )

    if result.ok:
        log.info(
            "dispatch %s ok: repo=%s links=%d msg=%d",
            platform,
            repo,
            len(links),
            placeholder.message_id,
        )
        return True

    log.warning(
        "dispatch %s failed: repo=%s status=%d err=%s",
        platform,
        repo,
        result.status_code,
        result.error,
    )
    error_text = (
        f"❌ *{platform}*: dispatch failed\n"
        f"`HTTP {result.status_code}`\n"
        f"`{result.error or 'unknown error'}`"
    )
    retry_kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔁 Retry", callback_data=f"retry:platform:{platform.lower()}")]]
    )
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=placeholder.message_id,
            text=error_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=retry_kb,
        )
    except Exception as e:  # pragma: no cover — defensive
        log.warning("edit_message_text after dispatch failure failed: %s", e)
    return False


async def gated_dispatch(
    *,
    user_id: int,
    chat_id: int,
    steam: list[str],
    itch: list[str],
    bot_data: dict[str, Any],
    bot: Any,
) -> tuple[bool, str | None]:
    """Run the full gate-protected dispatch flow for one user.

    Saves the payload to ``bot_data["last_dispatch"][user_id]`` so /retry can
    replay it. Records a successful gate-passed dispatch against the rate
    limit (regardless of per-platform success — both consumed an Actions slot).

    Returns:
        (True, None) on success (gates passed; dispatch attempted).
        (False, error_message) when a gate rejected.
    """
    config = bot_data["config"]
    dispatcher: Dispatcher = bot_data["dispatcher"]
    rate_limit: RateLimit = bot_data["rate_limit"]
    lock: ConcurrencyLock = bot_data["lock"]

    decision = check_gates(user_id=user_id, bot_data=bot_data)
    if not decision.ok:
        return False, decision.user_message

    if not lock.try_acquire(user_id):
        # Race between check_gates and try_acquire — extremely rare given PTB
        # serializes handlers, but check anyway.
        return False, "⏳ You already have a dispatch in flight."

    try:
        if steam:
            await dispatch_one_platform(
                platform="Steam",
                repo=config.steam_repo,
                links=steam,
                chat_id=chat_id,
                bot=bot,
                dispatcher=dispatcher,
            )
        if itch:
            await dispatch_one_platform(
                platform="itch",
                repo=config.itch_repo,
                links=itch,
                chat_id=chat_id,
                bot=bot,
                dispatcher=dispatcher,
            )
        rate_limit.record(user_id)

        last = bot_data.setdefault("last_dispatch", {})
        last[user_id] = {
            "steam": list(steam),
            "itch": list(itch),
            "ts": time.time(),
        }
    finally:
        lock.release(user_id)

    return True, None


def get_last_dispatch(bot_data: dict[str, Any], user_id: int) -> dict[str, Any] | None:
    """Return last_dispatch entry for user if still within TTL, else None."""
    last = bot_data.get("last_dispatch") or {}
    entry = last.get(user_id)
    if entry is None:
        return None
    if time.time() - entry.get("ts", 0) > LAST_DISPATCH_TTL_SECONDS:
        return None
    return entry
