"""Parser for uploaded .txt / .json files.

Pure function — no I/O. Takes raw bytes, returns list of lines.
The actual download happens in the conversation handler; we keep parsing
separate so it's trivially testable.
"""

from __future__ import annotations

import json

# Maximum file size we'll parse (256 KiB). Anything larger is rejected;
# users can split into multiple files. Telegram's API allows up to 20 MB but
# we don't want to OOM on a malicious upload, and 256 KiB ≈ thousands of URLs.
MAX_FILE_SIZE = 256 * 1024


class FileTooLargeError(Exception):
    """Raised when uploaded file exceeds MAX_FILE_SIZE."""


class UnsupportedFileError(Exception):
    """Raised when the file isn't .txt or .json (or content is unparseable)."""


def parse_uploaded_file(filename: str, data: bytes) -> list[str]:
    """Parse an uploaded file into a list of link strings.

    Supported formats:
        - .txt (or any non-.json): one link per line, blank lines skipped
        - .json: array of strings  ["url1", "url2"]
                 or array of objects with "link" key  [{"link": "url1"}, ...]

    Args:
        filename: Original filename (used to pick parser by extension).
        data: Raw file bytes.

    Raises:
        FileTooLargeError: If data exceeds MAX_FILE_SIZE.
        UnsupportedFileError: If JSON is malformed or has unexpected shape.
    """
    if len(data) > MAX_FILE_SIZE:
        raise FileTooLargeError(
            f"File is {len(data)} bytes; max allowed is {MAX_FILE_SIZE}."
        )

    text = data.decode("utf-8", errors="replace")
    name_lower = filename.lower()

    if name_lower.endswith(".json"):
        return _parse_json(text)

    # Default: treat as plain text (one link per line)
    return _parse_text(text)


def _parse_text(text: str) -> list[str]:
    """Newline-separated; blank lines and pure whitespace lines are dropped."""
    return [line.strip() for line in text.splitlines() if line.strip()]


def _parse_json(text: str) -> list[str]:
    """Accept either ['url1', 'url2'] or [{'link': 'url1'}, {'link': 'url2'}]."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise UnsupportedFileError(f"Malformed JSON: {e.msg}") from e

    if not isinstance(data, list):
        raise UnsupportedFileError(
            "JSON root must be an array of strings or objects with a 'link' key."
        )

    out: list[str] = []
    for i, item in enumerate(data):
        if isinstance(item, str):
            s = item.strip()
            if s:
                out.append(s)
        elif isinstance(item, dict):
            link = item.get("link") or item.get("url") or ""
            if not isinstance(link, str):
                continue
            s = link.strip()
            if s:
                out.append(s)
        else:
            raise UnsupportedFileError(
                f"JSON item at index {i} is neither a string nor an object."
            )
    return out
