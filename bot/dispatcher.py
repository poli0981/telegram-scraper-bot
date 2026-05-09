"""GitHub Actions workflow_dispatch client.

Wraps `POST /repos/{owner}/{repo}/actions/workflows/{file}/dispatches`.
Stateless aside from the injected httpx client; safe to share across handlers.

Reference:
    https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import httpx

# Redact patterns for tokens that might appear in error bodies. Belt-and-braces:
# GitHub never echoes the auth header back, but a misconfigured proxy could.
_TOKEN_PATTERNS = [
    re.compile(r"gh[ops]_[A-Za-z0-9_]{20,}"),  # GitHub PAT (classic + fine-grained)
    re.compile(r"github_pat_[A-Za-z0-9_]{40,}"),  # fine-grained PAT explicit prefix
    re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{30,}\b"),  # Telegram bot token shape
]


def _redact(text: str) -> str:
    """Strip anything that looks like a token before logging."""
    for pat in _TOKEN_PATTERNS:
        text = pat.sub("***REDACTED***", text)
    return text


log = logging.getLogger(__name__)

# GitHub returns 204 No Content on successful dispatch
_DISPATCH_OK_STATUS = 204

# Workflow inputs are limited to 65535 chars per value. We cap the joined links
# string conservatively at 60000 to leave headroom for control chars + JSON encoding.
_LINKS_INPUT_MAX_CHARS = 60_000


class DispatchError(Exception):
    """Raised on transport failures or non-2xx GitHub responses."""


@dataclass(slots=True)
class DispatchResult:
    """Outcome of a single workflow_dispatch call."""

    ok: bool
    repo: str
    status_code: int
    error: str | None = None

    @property
    def summary(self) -> str:
        if self.ok:
            return f"✅ {self.repo} dispatched (HTTP {self.status_code})"
        return f"❌ {self.repo} failed (HTTP {self.status_code}): {self.error or 'unknown error'}"


class Dispatcher:
    """Triggers `workflow_dispatch` runs on configured repos."""

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

        Args:
            repo: "owner/name" form.
            links: Normalized URLs. Joined with newlines for the workflow input.
            chat_id: Telegram chat ID for the callback.
            message_id: Telegram message ID the workflow will edit.

        Returns:
            DispatchResult with ok=True iff GitHub returned 204.
            On transport failure, ok=False and error is populated.
        """
        if not links:
            return DispatchResult(ok=False, repo=repo, status_code=0, error="no links to dispatch")

        joined = "\n".join(links)
        if len(joined) > _LINKS_INPUT_MAX_CHARS:
            return DispatchResult(
                ok=False,
                repo=repo,
                status_code=0,
                error=f"links payload too large ({len(joined)} > {_LINKS_INPUT_MAX_CHARS} chars)",
            )

        url = (
            f"https://api.github.com/repos/{repo}"
            f"/actions/workflows/{self._workflow_file}/dispatches"
        )
        payload = {
            "ref": self._ref,
            "inputs": {
                "links": joined,
                "chat_id": str(chat_id),
                "message_id": str(message_id),
            },
        }
        headers = {
            "Authorization": f"Bearer {self._gh_pat}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "telegram-scraper-bot/0.1",
        }

        log.info("dispatch: repo=%s links=%d chat_id=%d", repo, len(links), chat_id)

        try:
            resp = await self._client.post(url, json=payload, headers=headers, timeout=30.0)
        except httpx.TimeoutException:
            log.warning("dispatch: timeout repo=%s", repo)
            return DispatchResult(ok=False, repo=repo, status_code=0, error="timeout")
        except httpx.HTTPError as e:
            log.warning("dispatch: transport error repo=%s err=%s", repo, e)
            return DispatchResult(ok=False, repo=repo, status_code=0, error=f"transport: {e}")

        if resp.status_code == _DISPATCH_OK_STATUS:
            log.info("dispatch: ok repo=%s", repo)
            return DispatchResult(ok=True, repo=repo, status_code=resp.status_code)

        # Truncate response body for log/error message; redact token-shaped strings
        body = _redact(resp.text[:300]) if resp.text else "<empty>"
        log.warning("dispatch: failed repo=%s status=%d body=%s", repo, resp.status_code, body)
        return DispatchResult(
            ok=False,
            repo=repo,
            status_code=resp.status_code,
            error=body,
        )
