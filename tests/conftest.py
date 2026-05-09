"""Shared pytest fixtures.

Phase 0: env isolation fixture so config tests don't leak into each other.
Phase 1+: will add httpx mocks, fake Update/Context builders, etc.
"""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Strip every BOT_*/GH_*/etc env var so tests start from a clean slate.

    Tests that need specific values must set them via monkeypatch.setenv().
    Autouse=True so individual tests don't have to opt in.
    """
    for key in list(os.environ.keys()):
        if key.startswith(
            (
                "BOT_",
                "GH_",
                "ALLOWED_",
                "STEAM_",
                "ITCH_",
                "WORKFLOW_",
                "PERSISTENCE_",
                "RATE_LIMIT_",
                "MAX_LINKS_",
                "LOG_LEVEL",
            )
        ):
            monkeypatch.delenv(key, raising=False)
    yield
