"""Tests for bot.file_parser."""

from __future__ import annotations

import json

import pytest

from bot.file_parser import (
    MAX_FILE_SIZE,
    FileTooLargeError,
    UnsupportedFileError,
    parse_uploaded_file,
)


class TestParseText:
    def test_simple_lines(self) -> None:
        data = b"https://store.steampowered.com/app/440/\nhttps://x.itch.io/y\n"
        assert parse_uploaded_file("links.txt", data) == [
            "https://store.steampowered.com/app/440/",
            "https://x.itch.io/y",
        ]

    def test_strips_blank_lines(self) -> None:
        data = b"\n\nurl1\n\n  \nurl2\n"
        assert parse_uploaded_file("links.txt", data) == ["url1", "url2"]

    def test_strips_whitespace_per_line(self) -> None:
        data = b"  url1  \n\turl2\t\n"
        assert parse_uploaded_file("links.txt", data) == ["url1", "url2"]

    def test_empty_file(self) -> None:
        assert parse_uploaded_file("links.txt", b"") == []

    def test_unknown_extension_treated_as_text(self) -> None:
        # .csv, .md, no extension — all fall through to text parser
        data = b"url1\nurl2\n"
        assert parse_uploaded_file("links.csv", data) == ["url1", "url2"]
        assert parse_uploaded_file("noext", data) == ["url1", "url2"]

    def test_handles_invalid_utf8(self) -> None:
        # Bytes that aren't valid UTF-8 should be replaced, not raise
        data = b"url1\n\xff\xfeurl2\n"
        result = parse_uploaded_file("links.txt", data)
        assert "url1" in result


class TestParseJsonStrings:
    def test_array_of_strings(self) -> None:
        data = json.dumps(["url1", "url2", "url3"]).encode()
        assert parse_uploaded_file("links.json", data) == ["url1", "url2", "url3"]

    def test_strips_whitespace(self) -> None:
        data = json.dumps(["  url1  ", "\turl2\n"]).encode()
        assert parse_uploaded_file("links.json", data) == ["url1", "url2"]

    def test_skips_empty_strings(self) -> None:
        data = json.dumps(["url1", "", "  ", "url2"]).encode()
        assert parse_uploaded_file("links.json", data) == ["url1", "url2"]

    def test_empty_array(self) -> None:
        assert parse_uploaded_file("links.json", b"[]") == []


class TestParseJsonObjects:
    def test_array_of_objects_with_link_key(self) -> None:
        data = json.dumps([{"link": "url1"}, {"link": "url2"}]).encode()
        assert parse_uploaded_file("links.json", data) == ["url1", "url2"]

    def test_array_of_objects_with_url_key(self) -> None:
        # Some users may use "url" instead of "link"
        data = json.dumps([{"url": "url1"}, {"url": "url2"}]).encode()
        assert parse_uploaded_file("links.json", data) == ["url1", "url2"]

    def test_object_with_neither_key_skipped(self) -> None:
        data = json.dumps([{"link": "url1"}, {"name": "no link here"}, {"link": "url2"}]).encode()
        assert parse_uploaded_file("links.json", data) == ["url1", "url2"]

    def test_object_with_non_string_link_skipped(self) -> None:
        data = json.dumps([{"link": "url1"}, {"link": 123}, {"link": None}, {"link": "url2"}]).encode()
        assert parse_uploaded_file("links.json", data) == ["url1", "url2"]

    def test_mixed_strings_and_objects(self) -> None:
        # JSON spec doesn't forbid heterogeneous arrays — handle gracefully
        data = json.dumps(["url1", {"link": "url2"}, "url3"]).encode()
        assert parse_uploaded_file("links.json", data) == ["url1", "url2", "url3"]


class TestParseJsonErrors:
    def test_malformed_json(self) -> None:
        with pytest.raises(UnsupportedFileError, match="Malformed JSON"):
            parse_uploaded_file("links.json", b"{not valid json")

    def test_root_must_be_array(self) -> None:
        data = json.dumps({"link": "url1"}).encode()  # object at root
        with pytest.raises(UnsupportedFileError, match="must be an array"):
            parse_uploaded_file("links.json", data)

    def test_unsupported_item_type_raises(self) -> None:
        data = json.dumps(["url1", 42, "url3"]).encode()  # number is neither str nor dict
        with pytest.raises(UnsupportedFileError, match="neither a string nor an object"):
            parse_uploaded_file("links.json", data)


class TestSizeLimit:
    def test_accepts_file_just_under_limit(self) -> None:
        data = b"x\n" * (MAX_FILE_SIZE // 2)  # exactly MAX_FILE_SIZE bytes
        # Should not raise
        result = parse_uploaded_file("links.txt", data)
        assert len(result) == MAX_FILE_SIZE // 2

    def test_rejects_file_over_limit(self) -> None:
        data = b"x" * (MAX_FILE_SIZE + 1)
        with pytest.raises(FileTooLargeError):
            parse_uploaded_file("links.txt", data)
