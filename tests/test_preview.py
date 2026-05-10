"""Tests for bot.preview — message formatting helpers."""

from __future__ import annotations

from bot.classifier import ClassifiedLink, LinkKind
from bot.preview import (
    _MESSAGE_MAX_CHARS,
    format_collect_progress,
    format_dispatch_summary,
    format_preview,
)

# ─── format_preview ─────────────────────────────────────────────


class TestFormatPreview:
    def test_basic_preview(self) -> None:
        text = format_preview(
            steam=["https://store.steampowered.com/app/440/"],
            itch=["https://x.itch.io/y"],
            invalid=[],
            mode="mixed",
        )
        assert "Steam: *1*" in text
        assert "itch:  *1*" in text
        assert "mixed" in text
        assert "/yes" in text

    def test_duplicate_count_rendered(self) -> None:
        text = format_preview(
            steam=["https://store.steampowered.com/app/440/"],
            itch=[],
            invalid=[],
            mode="steam",
            duplicate_count=3,
        )
        assert "Duplicates (skipped): *3*" in text

    def test_duplicate_count_zero_still_rendered(self) -> None:
        """Symmetric with Invalid: row always shown so the layout is stable."""
        text = format_preview(
            steam=["https://store.steampowered.com/app/440/"],
            itch=[],
            invalid=[],
            mode="steam",
        )
        assert "Duplicates (skipped): *0*" in text

    def test_shows_invalid_samples(self) -> None:
        invalid = [
            ClassifiedLink(LinkKind.INVALID, "garbage1", "garbage1"),
            ClassifiedLink(LinkKind.INVALID, "garbage2", "garbage2"),
        ]
        text = format_preview(steam=[], itch=["https://x.itch.io/y"], invalid=invalid, mode="itch")
        assert "Invalid samples" in text
        assert "garbage1" in text
        assert "garbage2" in text

    def test_caps_invalid_samples_at_5(self) -> None:
        invalid = [ClassifiedLink(LinkKind.INVALID, f"bad{i}", f"bad{i}") for i in range(10)]
        text = format_preview(steam=["x"], itch=[], invalid=invalid, mode="steam")
        # First 5 shown, rest summarized
        assert "bad0" in text
        assert "bad4" in text
        assert "bad5" not in text
        assert "and 5 more" in text

    def test_truncates_long_invalid_lines(self) -> None:
        very_long = "x" * 200
        invalid = [ClassifiedLink(LinkKind.INVALID, very_long, very_long)]
        text = format_preview(steam=["x"], itch=[], invalid=invalid, mode="steam")
        assert "…" in text
        # The full 200-char line should not appear verbatim
        assert very_long not in text

    def test_warns_when_nothing_valid(self) -> None:
        text = format_preview(steam=[], itch=[], invalid=[], mode="mixed")
        assert "Nothing valid" in text
        assert "/yes" not in text  # no point offering /yes

    def test_escapes_backticks_in_invalid_samples(self) -> None:
        # Backticks would break Markdown code spans; must be escaped/replaced
        invalid = [ClassifiedLink(LinkKind.INVALID, "evil`bad", "evil`bad")]
        text = format_preview(steam=["x"], itch=[], invalid=invalid, mode="steam")
        # Original backtick should not appear as-is inside a code span
        assert "evil`bad" not in text or text.count("`") % 2 == 0

    def test_message_within_telegram_limit(self) -> None:
        # Even with worst-case input, message must not exceed cap
        invalid = [ClassifiedLink(LinkKind.INVALID, "x" * 100, "x" * 100) for _ in range(20)]
        text = format_preview(steam=["a"] * 50, itch=["b"] * 50, invalid=invalid, mode="mixed")
        assert len(text) <= _MESSAGE_MAX_CHARS


# ─── format_dispatch_summary ────────────────────────────────────


class TestFormatDispatchSummary:
    def test_steam_only_success(self) -> None:
        text = format_dispatch_summary(steam_count=5, itch_count=0, steam_ok=True, itch_ok=None)
        assert "✅ Steam" in text
        assert "5 link" in text
        assert "itch" not in text.lower() or "itch:" not in text  # itch not mentioned when count=0

    def test_itch_only_success(self) -> None:
        text = format_dispatch_summary(steam_count=0, itch_count=3, steam_ok=None, itch_ok=True)
        assert "✅ itch" in text
        assert "3 link" in text

    def test_both_success(self) -> None:
        text = format_dispatch_summary(steam_count=2, itch_count=3, steam_ok=True, itch_ok=True)
        assert "✅ Steam" in text
        assert "✅ itch" in text

    def test_steam_failure_with_error(self) -> None:
        text = format_dispatch_summary(
            steam_count=2,
            itch_count=0,
            steam_ok=False,
            itch_ok=None,
            steam_error="401 unauthorized",
        )
        assert "❌ Steam" in text
        assert "401 unauthorized" in text

    def test_partial_success(self) -> None:
        text = format_dispatch_summary(
            steam_count=2,
            itch_count=3,
            steam_ok=True,
            itch_ok=False,
            itch_error="rate limited",
        )
        assert "✅ Steam" in text
        assert "❌ itch" in text
        assert "rate limited" in text

    def test_failure_without_error_text(self) -> None:
        text = format_dispatch_summary(
            steam_count=1, itch_count=0, steam_ok=False, itch_ok=None, steam_error=None
        )
        assert "❌ Steam" in text
        assert "unknown error" in text

    def test_eta_message_present(self) -> None:
        text = format_dispatch_summary(steam_count=1, itch_count=0, steam_ok=True, itch_ok=None)
        assert "1–8 min" in text or "1-8 min" in text


# ─── format_collect_progress ────────────────────────────────────


class TestFormatCollectProgress:
    def test_under_limit(self) -> None:
        text = format_collect_progress(buffer_size=5, max_links=100)
        assert "5" in text
        assert "/done" in text
        assert "limit reached" not in text

    def test_at_limit(self) -> None:
        text = format_collect_progress(buffer_size=100, max_links=100)
        assert "100/100" in text
        assert "limit reached" in text

    def test_over_limit(self) -> None:
        # Edge case — shouldn't happen in practice but handler must be safe
        text = format_collect_progress(buffer_size=105, max_links=100)
        assert "limit reached" in text
