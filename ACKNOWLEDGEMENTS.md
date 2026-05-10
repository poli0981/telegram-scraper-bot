# Acknowledgements

Thanks to the projects, services, and tools this bot stands on top of.

## Runtime dependencies

| Package | License | Purpose |
|---|---|---|
| [`python-telegram-bot`](https://python-telegram-bot.org/) | LGPL-3.0 | Telegram Bot API framework. The whole conversation/inline-keyboard pattern comes from PTB v21. |
| [`httpx`](https://www.python-httpx.org/) | BSD-3-Clause | Async HTTP client used by the dispatcher to call GitHub Actions. |
| [`python-dotenv`](https://github.com/theskumar/python-dotenv) | BSD-3-Clause | `.env` loader for local development. |
| [`python-json-logger`](https://github.com/madzak/python-json-logger) | BSD-2-Clause | Optional JSON log formatter (`LOG_FORMAT=json`). |

## Development dependencies

| Package | License | Purpose |
|---|---|---|
| [`pytest`](https://pytest.org/) | MIT | Test runner. |
| [`pytest-asyncio`](https://pytest-asyncio.readthedocs.io/) | Apache-2.0 | Async test support. |
| [`pytest-cov`](https://pytest-cov.readthedocs.io/) | MIT | Coverage reporting. |
| [`respx`](https://lundberg.github.io/respx/) | BSD-3-Clause | Mocks `httpx` requests in dispatcher tests. |
| [`ruff`](https://docs.astral.sh/ruff/) | MIT | Linting and formatting. |

## Services

- **[Telegram](https://telegram.org)** — Bot API, where the bot lives.
- **[GitHub Actions](https://docs.github.com/en/actions)** — where the heavy
  scraping work happens, dispatched by this bot.
- **[Steam](https://store.steampowered.com)** — source of free-to-play
  game data. URLs you submit point here; this bot is not affiliated with
  Valve. See [`DISCLAIMER.md`](DISCLAIMER.md).
- **[itch.io](https://itch.io)** — source of indie game data. URLs you
  submit point here; this bot is not affiliated with itch corp. See
  [`DISCLAIMER.md`](DISCLAIMER.md).

## AI tooling

Substantial portions of this codebase were authored or refactored with the
assistance of large language models, primarily:

- **[Claude](https://claude.ai)** (Anthropic) — used via Claude Code CLI
  for code generation, refactoring, test scaffolding, and documentation
  drafting.
- Other LLMs may have contributed via casual editor integrations; their
  output is small and not separately attributed.

All AI-generated output was reviewed by the human maintainer before being
merged. Commits where AI made substantive contributions include a
`Co-Authored-By: Claude` trailer, per the
[Anthropic guidance](https://www.anthropic.com/) and the project's
practical convention.

The license terms (MIT) and the warranty disclaimer (no warranty; see
[`DISCLAIMER.md`](DISCLAIMER.md)) apply equally to AI-generated
contributions.

## Companion repositories

- [`poli0981/free-steam-games-list`](https://github.com/poli0981/free-steam-games-list)
  — Steam free-to-play tracker, target of the bot's Steam dispatches.
- [`poli0981/free-games-itchio-list`](https://github.com/poli0981/free-games-itchio-list)
  — itch.io free game tracker, target of the bot's itch dispatches.
- [`poli0981/.github`](https://github.com/poli0981/.github) — shared
  reusable workflows (Discord notifications, etc.).

## Inspiration / prior art

- The "wizard → preview → confirm → workflow_dispatch" pattern was
  inspired by countless Telegram bots that use ConversationHandler, plus
  the GitHub-bot pattern of editing your own message with delayed results.
- The token-redaction regex in `bot/dispatcher.py` is a defensive copy of
  the patterns used by GitHub's own tools (`@actions/core`'s `setSecret`).

## Personal thanks

To everyone who let me drop links into chat without asking what I was
building, and to the maintainers of `python-telegram-bot` for the
mature 21.x line — both of those things made this project a weekend
instead of a month.
