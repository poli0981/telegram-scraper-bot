"""Tests for bot.gates — concurrency lock + rate limit."""

from __future__ import annotations

import pytest

from bot.gates import (
    ConcurrencyLock,
    RateLimit,
    format_retry_after,
)

# ─── ConcurrencyLock ────────────────────────────────────────────


class TestConcurrencyLock:
    def test_first_acquire_succeeds(self) -> None:
        lock = ConcurrencyLock()
        assert lock.try_acquire(42, now=100.0) is True

    def test_second_acquire_blocked(self) -> None:
        lock = ConcurrencyLock()
        lock.try_acquire(42, now=100.0)
        assert lock.try_acquire(42, now=101.0) is False

    def test_release_allows_reacquire(self) -> None:
        lock = ConcurrencyLock()
        lock.try_acquire(42, now=100.0)
        lock.release(42)
        assert lock.try_acquire(42, now=101.0) is True

    def test_release_idempotent(self) -> None:
        lock = ConcurrencyLock()
        lock.release(42)  # never held — should not raise
        lock.release(42)  # second release — still no-op

    def test_different_users_independent(self) -> None:
        lock = ConcurrencyLock()
        assert lock.try_acquire(1, now=100.0) is True
        assert lock.try_acquire(2, now=100.0) is True  # different user, allowed
        assert lock.try_acquire(1, now=101.0) is False  # user 1 still locked

    def test_stale_lock_expires(self) -> None:
        lock = ConcurrencyLock(stale_after=60.0)
        lock.try_acquire(42, now=100.0)
        # Still held within window
        assert lock.is_held(42, now=159.0)
        # Expired after stale_after
        assert lock.is_held(42, now=161.0) is False
        # And can be re-acquired
        assert lock.try_acquire(42, now=162.0) is True

    def test_is_held_for_unknown_user(self) -> None:
        lock = ConcurrencyLock()
        assert lock.is_held(999) is False


# ─── RateLimit ──────────────────────────────────────────────────


class TestRateLimitUserWindow:
    @pytest.fixture
    def rl(self) -> RateLimit:
        # 3 dispatches per 60s per user; very high global cap so it doesn't interfere
        return RateLimit(user_max=3, user_window=60.0, global_max=1000, global_window=3600.0)

    def test_initial_allowed(self, rl: RateLimit) -> None:
        decision = rl.check(42, now=100.0)
        assert decision.allowed is True

    def test_under_limit(self, rl: RateLimit) -> None:
        for i in range(2):
            assert rl.check(42, now=100.0 + i).allowed is True
            rl.record(42, now=100.0 + i)
        # Third should still be allowed (max=3)
        assert rl.check(42, now=102.0).allowed is True

    def test_at_limit_blocks(self, rl: RateLimit) -> None:
        for i in range(3):
            rl.record(42, now=100.0 + i)
        decision = rl.check(42, now=103.0)
        assert decision.allowed is False
        assert decision.reason == "user"
        # Retry hint is when the oldest entry leaves the window
        # First record at 100.0, window=60 → leaves at 160.0; check at 103.0 → ~57s
        assert 56 <= decision.retry_after <= 58

    def test_window_slides(self, rl: RateLimit) -> None:
        rl.record(42, now=100.0)
        rl.record(42, now=101.0)
        rl.record(42, now=102.0)
        # At 161 the first entry has slid out of the 60s window
        decision = rl.check(42, now=161.0)
        assert decision.allowed is True

    def test_different_users_independent(self, rl: RateLimit) -> None:
        for i in range(3):
            rl.record(1, now=100.0 + i)
        # User 1 locked out
        assert rl.check(1, now=103.0).allowed is False
        # User 2 unaffected
        assert rl.check(2, now=103.0).allowed is True


class TestRateLimitGlobalWindow:
    @pytest.fixture
    def rl(self) -> RateLimit:
        # High per-user cap, low global cap — global is the bottleneck
        return RateLimit(user_max=100, user_window=3600.0, global_max=2, global_window=60.0)

    def test_global_blocks_across_users(self, rl: RateLimit) -> None:
        rl.record(1, now=100.0)
        rl.record(2, now=101.0)
        # User 3 is blocked even though they've never dispatched, because global cap hit
        decision = rl.check(3, now=102.0)
        assert decision.allowed is False
        assert decision.reason == "global"

    def test_global_window_slides(self, rl: RateLimit) -> None:
        rl.record(1, now=100.0)
        rl.record(2, now=101.0)
        # At 161, both records have slid out
        assert rl.check(3, now=161.0).allowed is True


class TestRateLimitDecisionShape:
    def test_allowed_decision_has_no_reason(self) -> None:
        rl = RateLimit(user_max=10, user_window=60, global_max=100, global_window=60)
        d = rl.check(1)
        assert d.allowed is True
        assert d.reason is None
        assert d.retry_after == 0.0

    def test_denied_decision_has_retry_after(self) -> None:
        rl = RateLimit(user_max=1, user_window=60, global_max=100, global_window=60)
        rl.record(1, now=100.0)
        d = rl.check(1, now=101.0)
        assert d.allowed is False
        assert d.retry_after > 0


# ─── format_retry_after ─────────────────────────────────────────


class TestFormatRetryAfter:
    @pytest.mark.parametrize(
        "seconds,expected",
        [
            (0, "0s"),
            (30, "30s"),
            (59, "59s"),
            (60, "1 min"),
            (61, "2 min"),  # round up partial minutes
            (120, "2 min"),
            (1800, "30 min"),
        ],
    )
    def test_format(self, seconds: int, expected: str) -> None:
        assert format_retry_after(seconds) == expected


# ─── Smoke: combined gate behavior ──────────────────────────────


class TestGatesCombined:
    """Sanity check that lock + rate limit work together as expected."""

    def test_lock_blocks_even_when_under_rate_limit(self) -> None:
        lock = ConcurrencyLock()
        rl = RateLimit(user_max=10, user_window=60, global_max=100, global_window=60)

        # First dispatch: lock + rate check both pass
        assert rl.check(42).allowed
        assert lock.try_acquire(42, now=100.0)
        rl.record(42, now=100.0)

        # Second attempt while still locked (workflow not done yet):
        # rate limit would allow it (only 1 of 10 used), but lock blocks
        assert rl.check(42, now=101.0).allowed
        assert lock.try_acquire(42, now=101.0) is False
