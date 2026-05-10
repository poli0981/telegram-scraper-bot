# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
once it reaches `1.0.0` — until then, breaking changes may occur in any
minor version bump.

## [Unreleased]

_No unreleased changes._

## [0.2.0] — 2026-05-10

### Added
- **Slash commands** (global, work outside the wizard):
  - `/help` — list all commands by category.
  - `/status` — show in-flight lock state, rate-limit quota remaining for
    user and global windows, and current buffer size.
  - `/version` — bot package version, injected git SHA, Python version,
    workflow ref/file.
  - `/q <urls...>` — one-shot quick dispatch, bypasses the wizard.
  - `/retry` — replay last dispatch within a 30-minute TTL.
  - `/reset` — clear the COLLECT-state buffer without ending the wizard.
  - `/show` — peek at the current buffer.
  - `/whoami` — print your Telegram user ID and authorization status
    (intentionally **not** auth-gated so new users can self-discover).
- **Inline keyboards**:
  - Mode picker (Steam / itch / Mixed / Cancel) at `/start`.
  - Confirm / Edit / Cancel buttons on the preview at `/done`.
  - 🔁 Retry button on per-platform dispatch failures.
- **Telegram client integration**:
  - `setMyCommands` registers all global commands at boot so `/`
    autocompletes in the client.
  - `setMyShortDescription` / `setMyDescription` published.
  - `getMe` sanity check at boot — bad `BOT_TOKEN` now aborts startup
    loudly instead of running a zombie process.
- **Live duplicate detection** in COLLECT — pasted URLs already in the
  buffer are skipped immediately and surfaced to the user, instead of
  being silently deduped at preview time.
- **Concatenated-URL split** — pastes like
  `.../app/440/.../app/570/` now resolve to two separate URLs (previously
  the second was swallowed by the greedy regex path component).
- **Duplicate row in preview** — `Duplicates (skipped): N` row mirrors
  the existing `Invalid` row.
- **Production hardening**:
  - Pinned Python to 3.12 (was `>= 3.11`).
  - Docker `HEALTHCHECK` (process-based, via `pgrep`).
  - `ARG GIT_SHA` Docker build argument propagated to `/version`.
  - Graceful SIGTERM — `_post_shutdown` waits up to 30 s for in-flight
    dispatches before closing the httpx client.
  - Optional `LOG_FORMAT=json` for structured logs.
  - Dispatcher log redacts GitHub PAT and Telegram bot-token shapes
    before printing response bodies.
  - JSON syntax error in uploaded files now auto-cancels the wizard with
    a clear "fix and `/start` again" message.
  - `/cancel` now releases the concurrency lock so a stuck user is no
    longer blocked for the 10 min stale window.
- **Documentation**:
  - `PRIVACY.md`, `TERMS.md`, `DISCLAIMER.md`.
  - `SECURITY.md` — vulnerability reporting policy.
  - `CODE_OF_CONDUCT.md` — Contributor Covenant 2.1, with a
    project-specific note on Telegram User ID handling.
  - `CONTRIBUTING.md`, `AUTHORS.md`, `ACKNOWLEDGEMENTS.md`.
  - `docs/USER_GUIDE.md` — end-to-end guide covering bot setup, tracker
    repo setup, dispatch flow, and troubleshooting.
  - `docs/DEV_ENV.md`, `docs/RELEASING.md`.
- **GitHub templates**:
  - PR template.
  - Issue templates (bug report, feature request, feedback) as `.yml`
    forms with structured input.
  - `.github/ISSUE_TEMPLATE/config.yml` — disables blank issues, links
    out to Discussions, Discord, and the security advisory form.
- **Workflows**:
  - `.github/workflows/release.yml` — auto-creates a GitHub Release with
    auto-generated notes when a `v*` tag is pushed; opens a Discussion
    in the "Announcements" category.
  - `.github/workflows/bump-version.yml` — `workflow_dispatch` helper to
    bump `bot/__init__.py` and `pyproject.toml`, commit, tag, and push.
  - Existing CI workflow (`ci.yml`) continues to run `pytest` + `ruff`.
  - Existing wrapper workflows (`announce-release.yml`,
    `notify-ci-failure.yml`) kept as-is — they correctly call the
    organisation's reusable workflows; "skip" status in the Actions tab
    is the expected idle behavior, not a bug.

### Changed
- Mode picker switched from `ReplyKeyboardMarkup` to `InlineKeyboardMarkup`
  so it doesn't pollute the user's keyboard. Text commands (`/steam`,
  `/itch`, `/mixed`) remain available as a fallback.
- `confirm_yes` refactored to share `gated_dispatch` with `/q` and
  `/retry`; per-platform dispatch helper exported as
  `dispatch_one_platform`.
- README rewritten to reflect the v0.2.0 surface area, link the new
  documentation, and point at the actual tracker repos
  (`free-steam-games-list` and `free-games-itchio-list`).

### Removed
- Legacy single-file `bot.py` prototype at the repo root (superseded by
  the `bot/` package since v0.1.0; kept around accidentally).

### Security
- Token-shaped strings (`gh[ops]_...`, `github_pat_...`,
  `<digits>:<base64>` Telegram bot-token shape) are redacted from
  dispatcher log output and from error messages surfaced to users.

## [0.1.0] — initial

Initial repo skeleton, Steam end-to-end, itch + `/mixed` mode, hardening
(concurrency lock, rate limit, file upload, persistence, error boundary).

---

[Unreleased]: https://github.com/poli0981/telegram-scraper-bot/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/poli0981/telegram-scraper-bot/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/poli0981/telegram-scraper-bot/releases/tag/v0.1.0
