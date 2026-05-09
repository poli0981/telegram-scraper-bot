"""Preview / message formatting helpers — pure, easy to unit test.

Builds the human-readable summary shown to the user before /yes confirmation,
and the confirmation message after dispatch.
"""

from __future__ import annotations

from bot.classifier import ClassifiedLink

# Maximum number of invalid line samples to echo back in preview
_MAX_INVALID_SAMPLES = 5

# Truncate each invalid line at this length so a pasted blob doesn't blow up the message
_INVALID_SAMPLE_MAX_LEN = 60

# Telegram message hard limit is 4096 chars; we cap below to leave headroom
_MESSAGE_MAX_CHARS = 3800


def format_preview(
    steam: list[str],
    itch: list[str],
    invalid: list[ClassifiedLink],
    mode: str,
    *,
    inline: bool = False,
) -> str:
    """Build the preview message shown before user confirms /yes.

    Args:
        steam: Normalized Steam URLs.
        itch: Normalized itch URLs.
        invalid: ClassifiedLink entries with kind=INVALID.
        mode: One of "steam", "itch", "mixed".
        inline: If True, omit the "Confirm? /yes or /cancel" footer because
            the caller is attaching inline buttons instead.
    """
    lines = [
        "📋 *Preview*",
        "",
        f"Mode: `{mode}`",
        f"Steam: *{len(steam)}*",
        f"itch:  *{len(itch)}*",
        f"Invalid (will skip): *{len(invalid)}*",
    ]

    if invalid:
        sample = invalid[:_MAX_INVALID_SAMPLES]
        lines.append("")
        lines.append("Invalid samples:")
        for entry in sample:
            raw = entry.raw.strip() or "<blank>"
            if len(raw) > _INVALID_SAMPLE_MAX_LEN:
                raw = raw[: _INVALID_SAMPLE_MAX_LEN - 1] + "…"
            lines.append(f"  • `{_escape_markdown(raw)}`")
        if len(invalid) > _MAX_INVALID_SAMPLES:
            lines.append(f"  … and {len(invalid) - _MAX_INVALID_SAMPLES} more")

    if not inline:
        lines.append("")
        if steam or itch:
            lines.append("Confirm? /yes or /cancel")
        else:
            lines.append("⚠ Nothing valid to dispatch. /cancel and try again.")
    elif not (steam or itch):
        lines.append("")
        lines.append("⚠ Nothing valid to dispatch.")

    return _truncate("\n".join(lines))


def format_dispatch_summary(
    steam_count: int,
    itch_count: int,
    steam_ok: bool | None,
    itch_ok: bool | None,
    steam_error: str | None = None,
    itch_error: str | None = None,
) -> str:
    """Build the message shown after dispatch attempts complete.

    Args:
        steam_count, itch_count: How many links each platform got.
        steam_ok, itch_ok: True/False/None (None = not attempted).
        steam_error, itch_error: Error text if ok is False.
    """
    lines = ["🚀 *Dispatched*", ""]

    if steam_count > 0:
        if steam_ok:
            lines.append(f"✅ Steam: {steam_count} link(s) queued")
        else:
            lines.append(f"❌ Steam: dispatch failed — {steam_error or 'unknown error'}")

    if itch_count > 0:
        if itch_ok:
            lines.append(f"✅ itch:  {itch_count} link(s) queued")
        else:
            lines.append(f"❌ itch:  dispatch failed — {itch_error or 'unknown error'}")

    lines.append("")
    lines.append("Workflow will edit this message with results in ~1–8 min.")
    return _truncate("\n".join(lines))


def format_collect_progress(buffer_size: int, max_links: int) -> str:
    """Status line shown after each collect message."""
    if buffer_size >= max_links:
        return (
            f"📥 {buffer_size}/{max_links} lines (limit reached). "
            f"Send /done to preview, or /cancel."
        )
    return f"📥 {buffer_size} line(s) buffered. Send more, or /done to preview."


# ─── helpers ────────────────────────────────────────────────────


def _escape_markdown(text: str) -> str:
    """Escape Telegram MarkdownV1 special chars inside a code span.

    Inside backtick code spans only `\\` and `` ` `` need escaping.
    Everything else is rendered verbatim, so this is minimal.
    """
    return text.replace("\\", "\\\\").replace("`", "'")


def _truncate(text: str) -> str:
    """Hard-cap message length to fit Telegram's 4096-char limit."""
    if len(text) <= _MESSAGE_MAX_CHARS:
        return text
    return text[: _MESSAGE_MAX_CHARS - 20] + "\n…(truncated)"
