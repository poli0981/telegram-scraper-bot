"""Tests for /version command."""

from __future__ import annotations

from telegram.ext import Application

from bot import __version__
from bot.handlers.version import version_command
from tests.conftest import make_context, make_update


class TestVersion:
    async def test_version_includes_metadata(self, app: Application) -> None:
        update = make_update("/version")
        ctx = make_context(app)
        await version_command(update, ctx)

        text = update.message.reply_text.call_args.args[0]
        assert __version__ in text
        # Test config sets git_sha to "testsha"
        assert "testsha" in text
        # Workflow ref + file from default Config (workflow_ref="main", workflow_file="bot-ingest.yml")
        assert "main" in text
        assert "bot-ingest.yml" in text

    async def test_version_includes_python_version(self, app: Application) -> None:
        import sys

        update = make_update("/version")
        ctx = make_context(app)
        await version_command(update, ctx)
        text = update.message.reply_text.call_args.args[0]
        assert sys.version.split()[0] in text

    async def test_unauthorized_rejected(self, app: Application) -> None:
        update = make_update("/version", user_id=999)
        ctx = make_context(app)
        result = await version_command(update, ctx)
        assert result is None
