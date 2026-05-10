# Contributing

Thanks for considering a contribution. This is a one-maintainer hobby
project, so the bar is "make my life easy" — clear scope, tests, no
surprises.

## Before you start

1. Read [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md). Be kind, no PII leaks
   (especially Telegram User IDs — see below).
2. Skim [`README.md`](README.md) and `bot/handlers/__init__.py` to understand
   the architecture. The bot is a thin dispatcher; heavy work happens in
   the GitHub Actions workflows of the two tracker repositories.
3. Check existing issues and PRs to avoid duplicate work.

## Channels for contributing

| Channel | Use it for |
|---|---|
| **GitHub Issues** | Bug reports, feature requests, feedback (use the templates) |
| **GitHub PRs** | Code changes, doc fixes, workflow improvements |
| **GitHub Discussions** | Open-ended ideas, "should we even build this?" questions |
| **Direct message** ([`AUTHORS.md`](AUTHORS.md) channels) | Security issues, PII (your own user_id), or anything that should stay private |

For anything beyond the public channels — including questions about the
project that don't fit an issue, or wanting to discuss before opening a PR —
reach out via any of the channels in [`AUTHORS.md`](AUTHORS.md).

## Telegram User ID privacy (READ ME)

A user's Telegram `user_id` is sensitive. **Never** post your own or anyone
else's user_id in:

- Public GitHub issues, PRs, discussions, or comments.
- Public chat logs, screenshots, or pastes.
- Any social post.

When you need to share a user_id (e.g. asking an operator to add you to
their `ALLOWED_USER_IDS`), send it via DM to the maintainer through one of
the channels in [`AUTHORS.md`](AUTHORS.md).

The bot's `/whoami` command outputs *your own* ID. Treat its output the
same way: keep it private. Manage your own information yourself.

If you accidentally posted a user_id publicly, ping the maintainer to
redact it.

## Development setup

**Requirements:**

- Python 3.12 (pinned in `pyproject.toml` and `Dockerfile`).
- Git with GPG/SSH signing configured (commits get signed; tags must be
  signed for releases).
- Docker + Docker Compose (for the local-Docker workflow).

**One-time setup:**

```bash
git clone https://github.com/poli0981/telegram-scraper-bot.git
cd telegram-scraper-bot

py -3.12 -m venv .venv         # Windows
# or: python3.12 -m venv .venv  # Linux/macOS

.venv/Scripts/python.exe -m pip install --upgrade pip   # Windows
# or: source .venv/bin/activate && pip install --upgrade pip

.venv/Scripts/python.exe -m pip install -r requirements-dev.txt

cp .env.example .env
# fill in BOT_TOKEN, GH_PAT, ALLOWED_USER_IDS, STEAM_REPO, ITCH_REPO
```

The reference development machine spec is documented in
[`docs/DEV_ENV.md`](docs/DEV_ENV.md). Other configurations should also work
— Linux + any 3.12 will be fine — but the maintainer tests on the spec
listed there.

## Workflow

1. Open an issue first for non-trivial changes. Saves you and the
   maintainer time if the idea is out of scope.
2. Fork → branch → commit → PR. Branch naming: `claude/<short-slug>` for
   AI-assisted work (so reviews can check that lineage), or
   `feature/<slug>` / `fix/<slug>` for hand-written.
3. Keep PRs focused. One topic per PR. Doc-only and code changes can ride
   together if the doc describes the code change; otherwise split.

## Code style

- **Formatter**: `ruff format`. Run `ruff format bot/ tests/` before
  committing.
- **Linter**: `ruff check`. The CI fails on any violation.
- **Type hints**: encouraged, not enforced. Use `from __future__ import
  annotations` so forward refs resolve as strings.
- **Imports**: `ruff check` enforces I001 (sorted).
- **No emojis in code or YAML files** unless they appear in user-facing
  bot output (Telegram message strings). Keep documentation prose
  emoji-free except where it materially helps scanning (e.g. checklist
  ✅/❌ in tables).
- **Docstrings**: brief but informative. Describe the *why* if it isn't
  obvious from the code; describe the *what* if the function is non-pure
  (mutates state, does I/O).
- **Comments**: explain *why* something looks weird, not *what* the line
  does. The code already says what.

## Tests

- All new behavior gets a test. The CI requires `pytest` to pass.
- Run locally: `.venv/Scripts/python.exe -m pytest -q`.
- For coverage: `pytest --cov=bot --cov-report=term`. Aim for ≥ 90%; the
  current baseline is around 95%.
- For a single test: `pytest tests/test_classifier.py::TestClassifyBatch::test_concatenated_urls_split_into_separate_entries -v`.

Test patterns:

- Use the shared fixtures in `tests/conftest.py` (`app`, `config`,
  `mock_dispatcher`, `make_update`, `make_callback_update`,
  `make_context`).
- For inline-button handlers, use `make_callback_update("prefix:data")`.
- For `/q` and similar args-based commands, set `ctx.args = [...]` after
  building the context.
- Mock Telegram bot methods via `object.__setattr__(app.bot, "method",
  AsyncMock(...))` — `ExtBot` is frozen otherwise.

## Commits

- Imperative present tense, ≤ 72 char subject (`Add /whoami command`, not
  `Added /whoami` or `Adds /whoami`).
- Body wraps at 72 chars; explains the *why* when not obvious from the
  diff.
- `git config commit.gpgsign true` (or SSH equivalent). All commits should
  be signed; CI flags unsigned.
- AI-assisted commits should include `Co-Authored-By:` for the model that
  contributed substantively.

## Pull requests

Use [`.github/PULL_REQUEST_TEMPLATE.md`](.github/PULL_REQUEST_TEMPLATE.md).
Fill in:

- Summary (1–3 bullets, why + what).
- Test plan (concrete steps, even if "ran pytest, all pass").
- Risks / open questions (none is a fine answer).

CI runs `pytest`, `ruff check`, `ruff format --check`. PRs cannot merge
until green.

## Releases

The maintainer cuts releases via the `bump-version` workflow + `git tag
-s`. See [`docs/RELEASING.md`](docs/RELEASING.md) for the procedure.
Contributors don't tag.

## Reusing this code

The license is MIT — see [`LICENSE`](LICENSE). You may fork and run your
own. The author does not operate a hosted service; please don't direct
your users back to the upstream maintainer for support of your fork.

## Saying thanks

Star the repo, drop a tip via [Patreon](https://www.patreon.com/skullmute)
or [Ko-fi](https://ko-fi.com/skullmute), or just leave a kind comment in
Discussions. None expected; all appreciated.
