"""GitHub Actions workflow_dispatch client.

Phase 0: skeleton + signatures.
Phase 1: full implementation with httpx, error handling, retries.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx


log = logging.getLogger(__name__)


@dataclass(slots=True)
class DispatchResult:
    """Outcome of a single workflow_dispatch call."""

    ok: bool
    repo: str
    status_code: int
    error: str | None = None


class Dispatcher:
    """Triggers `workflow_dispatch` runs on the configured repos.

    Stateless aside from the injected httpx client; safe to share across handlers.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        gh_pat: str,
        workflow_file: str = "bot-ingest.yml",
        ref: str = "main",
    ) -> None:
        self._client = client
        self._gh_pat = gh_pat
        self._workflow_file = workflow_file
        self._ref = ref

    async def dispatch(
        self,
        repo: str,
        links: list[str],
        chat_id: int,
        message_id: int,
    ) -> DispatchResult:
        """Trigger one workflow run.

        TODO(phase-1): POST to /actions/workflows/{file}/dispatches with inputs:
            - links: newline-joined
            - chat_id: str(chat_id)
            - message_id: str(message_id)
        Returns 204 on success, anything else is an error.
        """
        raise NotImplementedError("Implemented in Phase 1")
