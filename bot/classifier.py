"""Link classifier — parse user input into (kind, normalized_url) tuples.

Pure functions, no side effects. Easy to unit test.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import NamedTuple


class LinkKind(str, Enum):
    """Classification result for a single line of user input."""

    STEAM = "steam"
    ITCH = "itch"
    INVALID = "invalid"


class ClassifiedLink(NamedTuple):
    """Result of classifying one input line."""

    kind: LinkKind
    url: str  # normalized URL (or original raw line if INVALID)
    raw: str  # original input as-is, for echoing back to user


# ─── Patterns ───────────────────────────────────────────────────

# Steam: https://store.steampowered.com/app/<appid>[/<slug>][/]
_STEAM_RE = re.compile(
    r"https?://store\.steampowered\.com/app/(\d+)(?:/[^?\s]*)?",
    re.IGNORECASE,
)

# itch.io: https://<user>.itch.io/<game-slug> — strict (no query, no path beyond slug)
_ITCH_RE = re.compile(
    r"^https?://([\w-]+)\.itch\.io/([\w-]+)(?:/)?$",
    re.IGNORECASE,
)

# Bare appid (e.g. "440" → Team Fortress 2)
_BARE_APPID_RE = re.compile(r"^\d{1,8}$")

# Lookahead to split a single line on URL boundaries. Handles the common
# paste-without-separator case:
#   "https://store.../app/440/https://store.../app/570/"
#       → ["https://store.../app/440/", "https://store.../app/570/"]
# Non-URL prefixes (e.g. "see: https://...") are kept as their own piece and
# typically classified as INVALID — preserving them surfaces the prefix to the
# user instead of silently dropping it.
_URL_SPLIT_RE = re.compile(r"(?=https?://)", re.IGNORECASE)


def classify(line: str) -> ClassifiedLink:
    """Classify one line of user input.

    Recognizes:
        - Steam store URL with appid
        - Bare numeric appid (treated as Steam)
        - itch.io game URL (user.itch.io/game-slug)

    Returns ClassifiedLink with normalized URL on success, or INVALID
    with the raw line preserved for echoing.
    """
    raw = line.strip()
    if not raw:
        return ClassifiedLink(LinkKind.INVALID, "", line)

    # Strip surrounding quotes/brackets that paste sometimes adds
    cleaned = raw.strip("\"'<>[](){}")

    # Steam URL
    m = _STEAM_RE.search(cleaned)
    if m:
        appid = m.group(1)
        return ClassifiedLink(
            LinkKind.STEAM,
            f"https://store.steampowered.com/app/{appid}/",
            raw,
        )

    # Bare appid
    if _BARE_APPID_RE.match(cleaned):
        return ClassifiedLink(
            LinkKind.STEAM,
            f"https://store.steampowered.com/app/{cleaned}/",
            raw,
        )

    # itch.io URL
    m = _ITCH_RE.match(cleaned)
    if m:
        user, slug = m.group(1).lower(), m.group(2).lower()
        return ClassifiedLink(
            LinkKind.ITCH,
            f"https://{user}.itch.io/{slug}",
            raw,
        )

    return ClassifiedLink(LinkKind.INVALID, raw, line)


def split_inline_urls(line: str) -> list[str]:
    """Split a single line on URL boundaries.

    Users sometimes paste multiple URLs concatenated without a separator, e.g.
    ``https://a.com/x/https://b.com/y``. The Steam URL regex's greedy path
    component would otherwise swallow the second URL. Splitting on a lookahead
    for ``https?://`` recovers each URL individually.

    Lines without an embedded ``http(s)://`` pass through unchanged (single-
    element list). Empty pieces are dropped.
    """
    parts = [p for p in _URL_SPLIT_RE.split(line) if p.strip()]
    return parts if parts else [line]


def classify_batch(text: str) -> list[ClassifiedLink]:
    """Classify multi-line input. Empty lines and inline-concatenated URLs split."""
    out: list[ClassifiedLink] = []
    for raw_line in text.splitlines():
        if not raw_line.strip():
            continue
        for piece in split_inline_urls(raw_line):
            out.append(classify(piece))
    return out


def dedupe_preserve_order(links: list[ClassifiedLink]) -> list[ClassifiedLink]:
    """Remove duplicates by normalized URL, keeping first occurrence.

    INVALID entries are kept as-is (not deduped) since their `url` field is the
    raw line and may legitimately repeat.
    """
    seen: set[str] = set()
    out: list[ClassifiedLink] = []
    for link in links:
        if link.kind == LinkKind.INVALID:
            out.append(link)
            continue
        if link.url in seen:
            continue
        seen.add(link.url)
        out.append(link)
    return out


def split_by_kind(
    links: list[ClassifiedLink],
) -> tuple[list[str], list[str], list[ClassifiedLink]]:
    """Partition into (steam_urls, itch_urls, invalid_links).

    URLs are returned as plain strings (already normalized).
    Invalid entries keep their full ClassifiedLink for error reporting.
    """
    steam: list[str] = []
    itch: list[str] = []
    invalid: list[ClassifiedLink] = []
    for link in links:
        if link.kind == LinkKind.STEAM:
            steam.append(link.url)
        elif link.kind == LinkKind.ITCH:
            itch.append(link.url)
        else:
            invalid.append(link)
    return steam, itch, invalid
