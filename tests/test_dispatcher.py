"""Tests for bot.dispatcher — GitHub Actions workflow_dispatch client."""

from __future__ import annotations

import httpx
import pytest
import respx

from bot.dispatcher import _LINKS_INPUT_MAX_CHARS, Dispatcher, DispatchResult

# ─── fixtures ───────────────────────────────────────────────────


@pytest.fixture
async def client():
    async with httpx.AsyncClient() as c:
        yield c


@pytest.fixture
def dispatcher(client: httpx.AsyncClient) -> Dispatcher:
    return Dispatcher(
        client=client,
        gh_pat="fake-pat",
        workflow_file="bot-ingest.yml",
        ref="main",
    )


# ─── DispatchResult ─────────────────────────────────────────────


class TestDispatchResultSummary:
    def test_ok_summary(self) -> None:
        r = DispatchResult(ok=True, repo="x/y", status_code=204)
        assert "✅" in r.summary
        assert "x/y" in r.summary
        assert "204" in r.summary

    def test_failure_summary_with_error(self) -> None:
        r = DispatchResult(ok=False, repo="x/y", status_code=403, error="forbidden")
        assert "❌" in r.summary
        assert "403" in r.summary
        assert "forbidden" in r.summary

    def test_failure_summary_without_error(self) -> None:
        r = DispatchResult(ok=False, repo="x/y", status_code=500, error=None)
        assert "❌" in r.summary
        assert "unknown error" in r.summary


# ─── Dispatcher.dispatch() ──────────────────────────────────────


class TestDispatchSuccess:
    @respx.mock
    async def test_returns_ok_on_204(self, dispatcher: Dispatcher) -> None:
        route = respx.post(
            "https://api.github.com/repos/user/repo/actions/workflows/bot-ingest.yml/dispatches"
        ).mock(return_value=httpx.Response(204))

        result = await dispatcher.dispatch(
            repo="user/repo",
            links=["https://store.steampowered.com/app/440/"],
            chat_id=123,
            message_id=456,
        )

        assert result.ok is True
        assert result.status_code == 204
        assert result.error is None
        assert route.called

    @respx.mock
    async def test_sends_correct_payload(self, dispatcher: Dispatcher) -> None:
        route = respx.post(
            "https://api.github.com/repos/user/repo/actions/workflows/bot-ingest.yml/dispatches"
        ).mock(return_value=httpx.Response(204))

        await dispatcher.dispatch(
            repo="user/repo",
            links=[
                "https://store.steampowered.com/app/440/",
                "https://store.steampowered.com/app/730/",
            ],
            chat_id=12345,
            message_id=67890,
        )

        request = route.calls.last.request
        body = request.read().decode()
        assert "12345" in body
        assert "67890" in body
        assert "440" in body
        assert "730" in body
        # Links joined with newline
        assert "\\n" in body  # JSON-encoded newline

    @respx.mock
    async def test_sends_correct_headers(self, dispatcher: Dispatcher) -> None:
        route = respx.post(
            "https://api.github.com/repos/user/repo/actions/workflows/bot-ingest.yml/dispatches"
        ).mock(return_value=httpx.Response(204))

        await dispatcher.dispatch(
            repo="user/repo",
            links=["https://store.steampowered.com/app/440/"],
            chat_id=1,
            message_id=1,
        )

        headers = route.calls.last.request.headers
        assert headers["authorization"] == "Bearer fake-pat"
        assert headers["accept"] == "application/vnd.github+json"
        assert headers["x-github-api-version"] == "2022-11-28"
        assert "telegram-scraper-bot" in headers["user-agent"]

    @respx.mock
    async def test_uses_configured_workflow_file_and_ref(self, client: httpx.AsyncClient) -> None:
        d = Dispatcher(client, "fake-pat", workflow_file="custom.yml", ref="develop")
        route = respx.post(
            "https://api.github.com/repos/user/repo/actions/workflows/custom.yml/dispatches"
        ).mock(return_value=httpx.Response(204))

        await d.dispatch("user/repo", ["http://x.itch.io/y"], 1, 1)

        body = route.calls.last.request.read().decode()
        assert '"ref": "develop"' in body or '"ref":"develop"' in body


# ─── Validation ─────────────────────────────────────────────────


class TestDispatchValidation:
    async def test_empty_links_returns_error(self, dispatcher: Dispatcher) -> None:
        result = await dispatcher.dispatch("user/repo", [], 1, 1)
        assert result.ok is False
        assert "no links" in result.error.lower()

    async def test_oversized_payload_rejected(self, dispatcher: Dispatcher) -> None:
        # Build links that exceed the cap when joined
        oversized = ["x" * 1000] * 100  # ~100k chars after join
        assert sum(len(s) for s in oversized) + len(oversized) > _LINKS_INPUT_MAX_CHARS

        result = await dispatcher.dispatch("user/repo", oversized, 1, 1)
        assert result.ok is False
        assert "too large" in result.error.lower()


# ─── Failure modes ──────────────────────────────────────────────


class TestDispatchFailures:
    @respx.mock
    async def test_handles_404_workflow_not_found(self, dispatcher: Dispatcher) -> None:
        respx.post(
            "https://api.github.com/repos/user/repo/actions/workflows/bot-ingest.yml/dispatches"
        ).mock(return_value=httpx.Response(404, text='{"message":"Not Found"}'))

        result = await dispatcher.dispatch("user/repo", ["http://x.itch.io/y"], 1, 1)

        assert result.ok is False
        assert result.status_code == 404
        assert "Not Found" in result.error

    @respx.mock
    async def test_handles_401_unauthorized(self, dispatcher: Dispatcher) -> None:
        respx.post(
            "https://api.github.com/repos/user/repo/actions/workflows/bot-ingest.yml/dispatches"
        ).mock(return_value=httpx.Response(401, text='{"message":"Bad credentials"}'))

        result = await dispatcher.dispatch("user/repo", ["http://x.itch.io/y"], 1, 1)

        assert result.ok is False
        assert result.status_code == 401
        assert "Bad credentials" in result.error

    @respx.mock
    async def test_handles_422_validation_error(self, dispatcher: Dispatcher) -> None:
        respx.post(
            "https://api.github.com/repos/user/repo/actions/workflows/bot-ingest.yml/dispatches"
        ).mock(return_value=httpx.Response(422, text='{"message":"Invalid input"}'))

        result = await dispatcher.dispatch("user/repo", ["http://x.itch.io/y"], 1, 1)

        assert result.ok is False
        assert result.status_code == 422

    @respx.mock
    async def test_handles_timeout(self, dispatcher: Dispatcher) -> None:
        respx.post(
            "https://api.github.com/repos/user/repo/actions/workflows/bot-ingest.yml/dispatches"
        ).mock(side_effect=httpx.TimeoutException("Request timed out"))

        result = await dispatcher.dispatch("user/repo", ["http://x.itch.io/y"], 1, 1)

        assert result.ok is False
        assert result.status_code == 0
        assert "timeout" in result.error.lower()

    @respx.mock
    async def test_handles_transport_error(self, dispatcher: Dispatcher) -> None:
        respx.post(
            "https://api.github.com/repos/user/repo/actions/workflows/bot-ingest.yml/dispatches"
        ).mock(side_effect=httpx.ConnectError("Connection refused"))

        result = await dispatcher.dispatch("user/repo", ["http://x.itch.io/y"], 1, 1)

        assert result.ok is False
        assert result.status_code == 0
        assert "transport" in result.error.lower()

    @respx.mock
    async def test_truncates_long_error_body(self, dispatcher: Dispatcher) -> None:
        long_body = "x" * 1000
        respx.post(
            "https://api.github.com/repos/user/repo/actions/workflows/bot-ingest.yml/dispatches"
        ).mock(return_value=httpx.Response(500, text=long_body))

        result = await dispatcher.dispatch("user/repo", ["http://x.itch.io/y"], 1, 1)

        assert result.ok is False
        # Error body truncated to 300 chars
        assert len(result.error) <= 300

    @respx.mock
    async def test_handles_empty_response_body(self, dispatcher: Dispatcher) -> None:
        respx.post(
            "https://api.github.com/repos/user/repo/actions/workflows/bot-ingest.yml/dispatches"
        ).mock(return_value=httpx.Response(500, text=""))

        result = await dispatcher.dispatch("user/repo", ["http://x.itch.io/y"], 1, 1)

        assert result.ok is False
        assert result.error == "<empty>"

    @respx.mock
    async def test_redacts_token_shaped_strings_in_error_body(self, dispatcher: Dispatcher) -> None:
        # Simulate a misbehaving proxy that echoes the auth header in its body.
        leaky_body = (
            "Authorization: Bearer ghp_abcdefghijklmnopqrstuvwxyz0123456789 " "rejected by upstream"
        )
        respx.post(
            "https://api.github.com/repos/user/repo/actions/workflows/bot-ingest.yml/dispatches"
        ).mock(return_value=httpx.Response(500, text=leaky_body))

        result = await dispatcher.dispatch("user/repo", ["http://x.itch.io/y"], 1, 1)

        assert result.ok is False
        # The token is gone; the surrounding context survives.
        assert "ghp_" not in result.error
        assert "REDACTED" in result.error
        assert "rejected by upstream" in result.error
