# telegram-scraper-bot

Personal Telegram bot that dispatches Steam and itch.io scraping jobs to GitHub
Actions. Paste links → bot validates and previews → GitHub Actions runs the
ingestion → bot edits its own message with the result.

Companion to:

- [`free-steam-games-list`](https://github.com/poli0981/free-steam-games-list)
- [`free-games-itchio-list`](https://github.com/poli0981/free-games-itchio-list)

> **First time here?** Read [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) for the
> end-to-end walkthrough. The README below is a quick reference.

## Architecture

```
┌────────────┐       ┌──────────────┐       ┌────────────────┐
│  Telegram  │──msg─▶│   Bot (PTB)  │       │ GitHub Actions │
│   Client   │◀─edit─│   polling    │       │   bot-ingest   │
└────────────┘       └───────┬──────┘       └────────┬───────┘
                             │ workflow_dispatch     │
                             │  inputs:              │
                             │   • links             │
                             │   • chat_id           │
                             │   • message_id        │
                             ├──────────────────────▶│
                             │                       │
                             │                       ▼
                             │           1. Append temp_*.jsonl
                             │           2. Run ingest_new.py
                             │           3. Commit data/
                             │◀── editMessageText ───┘
                             ▼
                          User sees final report
```

Bot is stateless aside from in-memory rate-limit counters and an optional
`PicklePersistence` file for crash recovery. All heavy work happens inside
GitHub Actions, so bot uptime is non-critical.

## User flow

```
/start → mode picker (inline buttons: Steam | itch | mixed | cancel)
        ↓
        Paste links (multiple messages OK, or upload .txt / .json)
        /show — peek at buffer · /reset — clear buffer
        ↓
        /done → preview with inline buttons (✅ Confirm | ✏️ Edit | ❌ Cancel)
        ↓
        Confirm → workflow dispatched, bot posts placeholder per platform
        ↓
        ~1–8 min later: workflow edits placeholder(s) with result summary

Shortcuts:
        /q <url1> <url2> ...   one-shot, bypass wizard
        /retry                 replay last dispatch (within 30 min)
```

## Commands

| Command | Purpose |
|---|---|
| `/start`, `/scrape` | Open the wizard |
| `/steam`, `/itch`, `/mixed` | Pick mode (slash, in CHOOSE state) |
| `/done` | Finish collecting → preview |
| `/yes` | Confirm and dispatch (or use ✅ button) |
| `/reset` | Clear buffer mid-COLLECT |
| `/show` | Peek at the current buffer |
| `/cancel` | Abort wizard (releases lock) |
| `/q <urls...>` | One-shot dispatch, bypass wizard |
| `/retry` | Replay last dispatch (TTL 30 min) |
| `/status` | Quota + lock state |
| `/version` | Bot metadata (git SHA, Python, workflow ref) |
| `/help` | List commands |

## Features

- **Three modes**: `/steam`, `/itch`, `/mixed` (auto-routes by URL)
- **Inline keyboards**: mode picker + confirm/edit/cancel buttons; works alongside slash commands
- **Telegram command menu**: bot calls `setMyCommands` at boot so `/` autocompletes
- **Text or file input**: paste links inline or upload `.txt` / `.json` (max 256 KB)
- **Preview before dispatch**: shows count breakdown, dedupes, samples invalid lines
- **Per-platform callbacks**: each platform gets its own placeholder that the workflow edits independently
- **🔁 Retry button**: failed dispatches surface a one-tap retry
- **`/q` quick dispatch**: skip the wizard entirely for ad-hoc URL drops
- **`/retry` replay**: resend your last dispatch within 30 min
- **Concurrency lock**: one in-flight dispatch per user; `/cancel` releases it; auto-stale at 10 min
- **Rate limiting**: sliding window per-user (3/30min default) and global (10/hour default)
- **`/status` introspection**: see remaining quota and whether a dispatch is in flight
- **Crash recovery**: conversation + last_dispatch state persists in a pickle file
- **Graceful shutdown**: SIGTERM waits up to 30s for in-flight dispatches before closing
- **Error boundary**: unhandled exceptions are logged with full traceback; user sees a non-leaky generic notice
- **Token redaction**: dispatcher log output strips anything resembling a GitHub PAT or Telegram bot token
- **Structured logs**: set `LOG_FORMAT=json` for line-delimited JSON
- **Docker HEALTHCHECK**: process-based liveness probe

## Quickstart (development)

```bash
git clone https://github.com/poli0981/telegram-scraper-bot.git
cd telegram-scraper-bot

python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

cp .env.example .env
$EDITOR .env

# Run tests
pytest

# Run bot (Phase 0: skeleton — exits without polling)
python -m bot.main
```

## Deployment

See [`deploy/README.md`](deploy/README.md) for Docker and systemd paths.

## Configuration

All config via env vars (or `.env` file). See [`.env.example`](.env.example) for
the full list. Required:

| Var | Purpose |
|---|---|
| `BOT_TOKEN` | From [@BotFather](https://t.me/BotFather) |
| `GH_PAT` | Fine-grained PAT, `Actions:write + Contents:read` on tracker repos |
| `ALLOWED_USER_IDS` | Comma-separated Telegram user IDs |
| `STEAM_REPO` | e.g. `poli0981/free-steam-games-list` |
| `ITCH_REPO` | e.g. `poli0981/free-games-itchio-list` |

## Development

### Run tests

```bash
pytest                                  # all tests
pytest --cov=bot --cov-report=html      # with coverage HTML
pytest tests/test_classifier.py -v      # single file
pytest -k "test_steam"                  # filter by name
```

### Lint

```bash
ruff check bot/ tests/
ruff check --fix bot/ tests/            # auto-fix
ruff format bot/ tests/                 # format
```

### Roadmap

- [x] **Phase 0** — Repo skeleton, classifier (full impl), config, test setup
- [x] **Phase 1** — Steam end-to-end (dispatcher + conversation handler + workflow)
- [x] **Phase 2** — itch + `/mixed` mode (separate placeholder per platform)
- [x] **Phase 3** — Hardening (concurrency, file upload, persistence, rate limit, error boundary)
- [x] **Phase 4** — Deployment polish (Docker HEALTHCHECK, graceful SIGTERM, JSON logs, CI)
- [x] **Phase 5** — Quick-add `/q`, `/retry`, inline keyboards, command menu, status/version
- [x] **Phase 6** — Workflow-side run URL surfacing (drop-in templates in [`docs/tracker-workflows/`](docs/tracker-workflows/); per-tracker-repo config in [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md))
- [x] **Phase 7** — Concat URL split, live duplicate warning, JSON auto-cancel, `/whoami`, `getMe` boot check
- [x] **Phase 8** — Legal/policy docs, GitHub templates, release + bump-version workflows, full user guide

## Documentation

| Document | Audience |
|---|---|
| [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) | Operators + end users — full setup + daily flow + troubleshooting |
| [`docs/DEV_ENV.md`](docs/DEV_ENV.md) | Contributors — reference dev machine spec |
| [`docs/RELEASING.md`](docs/RELEASING.md) | Maintainer — release checklist |
| [`docs/tracker-workflows/`](docs/tracker-workflows/) | Drop-in `bot-ingest.yml` for the two tracker repos |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Contributors |
| [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) | Everyone |
| [`SECURITY.md`](SECURITY.md) | Security researchers |
| [`PRIVACY.md`](PRIVACY.md) | End users |
| [`TERMS.md`](TERMS.md) | End users + operators |
| [`DISCLAIMER.md`](DISCLAIMER.md) | End users |
| [`CHANGELOG.md`](CHANGELOG.md) | Everyone — what changed when |
| [`ACKNOWLEDGEMENTS.md`](ACKNOWLEDGEMENTS.md) | Credits |
| [`AUTHORS.md`](AUTHORS.md) | Maintainer contact channels |

## License

MIT — see [`LICENSE`](LICENSE).
