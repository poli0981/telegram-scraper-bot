# telegram-scraper-bot

Personal Telegram bot that dispatches Steam and itch.io scraping jobs to GitHub
Actions. Paste links → bot validates and previews → GitHub Actions runs the
ingestion → bot edits its own message with the result.

Companion to:

- [`steam-f2p-tracker`](https://github.com/poli0981/steam-f2p-tracker)
- [`itchio-f2p-tracker`](https://github.com/poli0981/itchio-f2p-tracker)

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
/start → mode picker (Steam | itch | mixed)
        ↓
        Paste links (multiple messages OK, or upload .txt / .json)
        ↓
        /done → preview: "Steam: 12, itch: 3, invalid: 2 — confirm?"
        ↓
        /yes → workflow dispatched, bot replies "Dispatching..."
        ↓
        ~1–8 min later: bot edits message with result summary
```

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
| `STEAM_REPO` | e.g. `poli0981/steam-f2p-tracker` |
| `ITCH_REPO` | e.g. `poli0981/itchio-f2p-tracker` |

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
- [ ] **Phase 1** — Steam end-to-end (dispatcher + conversation handler + workflow)
- [ ] **Phase 2** — itch + `/mixed` mode
- [ ] **Phase 3** — Hardening (concurrency, file upload, persistence, rate limit, error boundary)
- [ ] **Phase 4** — Deployment (Docker + systemd)
- [ ] **Phase 5** — Quick-add shortcut (deferred until v1 dogfood)

## License

MIT
