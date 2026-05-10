"""Tests for bot.classifier — pure-function module, easy to cover fully."""

from __future__ import annotations

import pytest

from bot.classifier import (
    ClassifiedLink,
    LinkKind,
    classify,
    classify_batch,
    dedupe_preserve_order,
    split_by_kind,
    split_inline_urls,
)

# ─── classify() ─────────────────────────────────────────────────


class TestClassifySteam:
    """Steam URL recognition + normalization."""

    @pytest.mark.parametrize(
        "raw,expected_url",
        [
            (
                "https://store.steampowered.com/app/440/",
                "https://store.steampowered.com/app/440/",
            ),
            (
                "https://store.steampowered.com/app/440",
                "https://store.steampowered.com/app/440/",
            ),
            (
                "https://store.steampowered.com/app/440/Team_Fortress_2/",
                "https://store.steampowered.com/app/440/",
            ),
            (
                "http://store.steampowered.com/app/730/",  # http, not https
                "https://store.steampowered.com/app/730/",
            ),
            (
                "HTTPS://STORE.STEAMPOWERED.COM/app/440/",  # mixed case
                "https://store.steampowered.com/app/440/",
            ),
        ],
    )
    def test_normalizes_to_canonical_form(self, raw: str, expected_url: str) -> None:
        result = classify(raw)
        assert result.kind == LinkKind.STEAM
        assert result.url == expected_url
        assert result.raw == raw

    def test_strips_surrounding_quotes_and_brackets(self) -> None:
        result = classify('"https://store.steampowered.com/app/440/"')
        assert result.kind == LinkKind.STEAM
        assert result.url == "https://store.steampowered.com/app/440/"

    def test_bare_appid_treated_as_steam(self) -> None:
        result = classify("440")
        assert result.kind == LinkKind.STEAM
        assert result.url == "https://store.steampowered.com/app/440/"

    def test_bare_appid_max_8_digits(self) -> None:
        # 9-digit number isn't a real appid — reject
        result = classify("123456789")
        assert result.kind == LinkKind.INVALID


class TestClassifyItch:
    """itch.io URL recognition."""

    @pytest.mark.parametrize(
        "raw,expected_url",
        [
            ("https://orb-star.itch.io/in-his-gaze", "https://orb-star.itch.io/in-his-gaze"),
            ("https://orb-star.itch.io/in-his-gaze/", "https://orb-star.itch.io/in-his-gaze"),
            (
                "https://Some-User.itch.io/My-Game",  # mixed case
                "https://some-user.itch.io/my-game",
            ),
            ("http://test.itch.io/game", "https://test.itch.io/game"),  # forced https
        ],
    )
    def test_recognizes_and_normalizes(self, raw: str, expected_url: str) -> None:
        result = classify(raw)
        assert result.kind == LinkKind.ITCH
        assert result.url == expected_url

    def test_rejects_itch_homepage(self) -> None:
        # No game slug → not a game URL
        assert classify("https://itch.io/").kind == LinkKind.INVALID

    def test_rejects_itch_browse_page(self) -> None:
        # Browse pages aren't game URLs
        assert classify("https://itch.io/games/free").kind == LinkKind.INVALID


class TestClassifyInvalid:
    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "   ",
            "not a url",
            "https://example.com/",
            "https://store.steampowered.com/",  # no /app/<id>
            "https://store.steampowered.com/app/",  # missing appid
            "https://store.steampowered.com/app/abc/",  # non-numeric appid
            "ftp://store.steampowered.com/app/440/",  # wrong scheme
        ],
    )
    def test_invalid_inputs(self, raw: str) -> None:
        result = classify(raw)
        assert result.kind == LinkKind.INVALID
        # Raw input preserved (with original whitespace) for echoing back
        assert result.raw == raw


# ─── classify_batch() ───────────────────────────────────────────


class TestClassifyBatch:
    def test_empty_input(self) -> None:
        assert classify_batch("") == []

    def test_skips_blank_lines(self) -> None:
        text = "\n\nhttps://store.steampowered.com/app/440/\n\n  \n"
        result = classify_batch(text)
        assert len(result) == 1
        assert result[0].kind == LinkKind.STEAM

    def test_mixed_input(self) -> None:
        text = (
            "https://store.steampowered.com/app/440/\n"
            "https://orb-star.itch.io/in-his-gaze\n"
            "garbage line\n"
            "730\n"
        )
        result = classify_batch(text)
        kinds = [r.kind for r in result]
        assert kinds == [LinkKind.STEAM, LinkKind.ITCH, LinkKind.INVALID, LinkKind.STEAM]

    def test_concatenated_urls_split_into_separate_entries(self) -> None:
        """Two Steam URLs pasted without a separator should yield two STEAMs.

        Without the inline-URL splitter the greedy ``[^?\\s]*`` path component
        in _STEAM_RE would swallow the second URL, leaving the user with only
        the first appid.
        """
        text = (
            "https://store.steampowered.com/app/4343200/Little_Petsville_Desktop/"
            "https://store.steampowered.com/app/1170880/Grimms_Hollow/"
        )
        result = classify_batch(text)
        assert len(result) == 2
        assert all(r.kind == LinkKind.STEAM for r in result)
        urls = {r.url for r in result}
        assert urls == {
            "https://store.steampowered.com/app/4343200/",
            "https://store.steampowered.com/app/1170880/",
        }

    def test_concatenated_itch_urls_also_split(self) -> None:
        text = "https://a.itch.io/game-ahttps://b.itch.io/game-b"
        result = classify_batch(text)
        assert len(result) == 2
        assert all(r.kind == LinkKind.ITCH for r in result)


class TestSplitInlineUrls:
    def test_no_url_returns_line_unchanged(self) -> None:
        assert split_inline_urls("plain text") == ["plain text"]

    def test_single_url_unchanged(self) -> None:
        url = "https://store.steampowered.com/app/440/"
        assert split_inline_urls(url) == [url]

    def test_two_concatenated_urls(self) -> None:
        line = "https://a.com/xhttps://b.com/y"
        assert split_inline_urls(line) == ["https://a.com/x", "https://b.com/y"]

    def test_prefix_text_kept_as_first_piece(self) -> None:
        # Non-URL prefix becomes its own piece; classify() will mark INVALID.
        line = "see this:https://a.com/x"
        assert split_inline_urls(line) == ["see this:", "https://a.com/x"]

    def test_http_and_https_both_recognized(self) -> None:
        line = "http://a.com/xhttps://b.com/y"
        assert split_inline_urls(line) == ["http://a.com/x", "https://b.com/y"]

    def test_empty_pieces_filtered(self) -> None:
        line = "https://a.com/x   https://b.com/y"  # whitespace between
        # Lookahead split keeps both URLs; whitespace-only piece is dropped.
        result = split_inline_urls(line)
        assert "https://a.com/x   " in result
        assert "https://b.com/y" in result


# ─── dedupe_preserve_order() ────────────────────────────────────


class TestDedupe:
    def test_empty(self) -> None:
        assert dedupe_preserve_order([]) == []

    def test_no_duplicates(self) -> None:
        items = [
            ClassifiedLink(LinkKind.STEAM, "https://store.steampowered.com/app/440/", "440"),
            ClassifiedLink(LinkKind.STEAM, "https://store.steampowered.com/app/730/", "730"),
        ]
        assert dedupe_preserve_order(items) == items

    def test_removes_dup_urls(self) -> None:
        a = ClassifiedLink(LinkKind.STEAM, "https://store.steampowered.com/app/440/", "440")
        b = ClassifiedLink(LinkKind.STEAM, "https://store.steampowered.com/app/440/", "440 again")
        c = ClassifiedLink(LinkKind.STEAM, "https://store.steampowered.com/app/730/", "730")
        result = dedupe_preserve_order([a, b, c])
        assert len(result) == 2
        assert result[0] is a  # first wins
        assert result[1] is c

    def test_invalid_entries_not_deduped(self) -> None:
        # Two invalid lines with same content should both pass through —
        # they may legitimately repeat as user error feedback
        a = ClassifiedLink(LinkKind.INVALID, "garbage", "garbage")
        b = ClassifiedLink(LinkKind.INVALID, "garbage", "garbage")
        result = dedupe_preserve_order([a, b])
        assert result == [a, b]


# ─── split_by_kind() ────────────────────────────────────────────


class TestSplitByKind:
    def test_empty(self) -> None:
        steam, itch, invalid = split_by_kind([])
        assert steam == []
        assert itch == []
        assert invalid == []

    def test_partitions_correctly(self) -> None:
        items = [
            ClassifiedLink(LinkKind.STEAM, "https://store.steampowered.com/app/440/", "440"),
            ClassifiedLink(LinkKind.ITCH, "https://x.itch.io/y", "x.itch.io/y"),
            ClassifiedLink(LinkKind.INVALID, "junk", "junk"),
            ClassifiedLink(LinkKind.STEAM, "https://store.steampowered.com/app/730/", "730"),
        ]
        steam, itch, invalid = split_by_kind(items)
        assert steam == [
            "https://store.steampowered.com/app/440/",
            "https://store.steampowered.com/app/730/",
        ]
        assert itch == ["https://x.itch.io/y"]
        assert len(invalid) == 1
        assert invalid[0].raw == "junk"
