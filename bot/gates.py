"""Gates that protect dispatch from abuse.

Two independent gates, both backed by in-memory state:

1. **Concurrency lock** — a user can have at most one in-flight dispatch at a
   time. Blocks new /yes attempts while a previous one is still running.
   Auto-expires after ``stale_after`` seconds so a crashed handler doesn't
   permanently lock the user out.

2. **Rate limit** — sliding window. Each user has a per-window cap, and the
   bot has a global per-window cap. Both are checked; either can reject.

State is intentionally non-persistent — survives only as long as the process
runs. After a restart, all locks/counters reset. That's fine: the worst case
is a user gets one extra dispatch right after a restart.

Thread safety: PTB v21 runs handlers serially in a single asyncio task, so
no locking is needed. If that ever changes, add an asyncio.Lock.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


# ─── Concurrency lock ───────────────────────────────────────────


@dataclass(slots=True)
class ConcurrencyLock:
    """Tracks one in-flight dispatch per user.

    A "dispatch" here is the whole /yes handler — from when the lock is acquired
    to when ``release`` is called (typically in a try/finally). Stale entries
    are auto-cleared after ``stale_after`` seconds so a crashed handler doesn't
    leave a user permanently locked.
    """

    stale_after: float = 600.0  # 10 minutes
    _holders: dict[int, float] = field(default_factory=dict)

    def try_acquire(self, user_id: int, *, now: float | None = None) -> bool:
        """Acquire the lock. Returns False if already held (and not stale)."""
        t = now if now is not None else time.monotonic()
        held_at = self._holders.get(user_id)
        if held_at is not None and (t - held_at) < self.stale_after:
            return False
        self._holders[user_id] = t
        return True

    def release(self, user_id: int) -> None:
        """Release the lock. Idempotent — safe to call even if not held."""
        self._holders.pop(user_id, None)

    def is_held(self, user_id: int, *, now: float | None = None) -> bool:
        """Read-only check, primarily for tests."""
        t = now if now is not None else time.monotonic()
        held_at = self._holders.get(user_id)
        return held_at is not None and (t - held_at) < self.stale_after


# ─── Rate limit ─────────────────────────────────────────────────


@dataclass(slots=True)
class RateLimitDecision:
    """Result of a rate-limit check."""

    allowed: bool
    reason: str | None = None  # "user" or "global" if denied
    retry_after: float = 0.0  # seconds until next allowed dispatch


@dataclass(slots=True)
class RateLimit:
    """Sliding-window rate limit, per-user and global.

    Two independent windows. Both must pass for a dispatch to proceed.
    Counters use deques pruned on every check, so memory stays bounded
    even with many users.
    """

    user_max: int
    user_window: float
    global_max: int
    global_window: float

    _per_user: dict[int, deque[float]] = field(default_factory=dict)
    _global: deque[float] = field(default_factory=deque)

    def check(self, user_id: int, *, now: float | None = None) -> RateLimitDecision:
        """Check whether a dispatch is currently allowed for this user.

        Does NOT record the dispatch — caller must call ``record()`` after
        a successful dispatch. Separating check from record lets us reject
        cleanly without polluting counters on a denial.
        """
        t = now if now is not None else time.monotonic()

        # User window
        user_dq = self._per_user.get(user_id)
        if user_dq is not None:
            self._prune(user_dq, t - self.user_window)
            if len(user_dq) >= self.user_max:
                retry_after = max(0.0, user_dq[0] + self.user_window - t)
                return RateLimitDecision(
                    allowed=False, reason="user", retry_after=retry_after
                )

        # Global window
        self._prune(self._global, t - self.global_window)
        if len(self._global) >= self.global_max:
            retry_after = max(0.0, self._global[0] + self.global_window - t)
            return RateLimitDecision(
                allowed=False, reason="global", retry_after=retry_after
            )

        return RateLimitDecision(allowed=True)

    def record(self, user_id: int, *, now: float | None = None) -> None:
        """Record a dispatch against both windows. Call after successful dispatch."""
        t = now if now is not None else time.monotonic()
        user_dq = self._per_user.setdefault(user_id, deque())
        user_dq.append(t)
        self._global.append(t)

    @staticmethod
    def _prune(dq: deque[float], cutoff: float) -> None:
        """Drop entries older than cutoff. In-place."""
        while dq and dq[0] < cutoff:
            dq.popleft()


# ─── Helpers ────────────────────────────────────────────────────


def format_retry_after(seconds: float) -> str:
    """Human-readable retry hint (e.g. '12 min', '45s')."""
    if seconds < 60:
        return f"{int(seconds)}s"
    minutes = int(seconds / 60) + (1 if seconds % 60 else 0)
    return f"{minutes} min"
