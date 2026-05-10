# User Guide — telegram-scraper-bot end-to-end

This guide walks you from "I just cloned the repo" to "the bot edits my
Telegram message with results from the tracker workflow", covering the
Bot, the two companion tracker repositories, and the data flow between
them.

If you only want a quick reference, jump to the
[command cheatsheet](#command-cheatsheet) at the bottom.

## Architecture in 30 seconds

```
┌────────────┐   message   ┌───────────────┐  workflow_dispatch  ┌──────────────────┐
│  Telegram  │────────────▶│ telegram-     │────────────────────▶│ GitHub Actions   │
│  client    │             │ scraper-bot   │                     │ in tracker repo  │
│            │◀────────────│ (this repo)   │                     │                  │
└────────────┘  edit msg   └───────────────┘   editMessageText   └──────────────────┘
                                                ▲
                                                │
                                                ▼
                                         data/ in tracker repo
                                         (committed by workflow)
```

The bot is a **stateless dispatcher**. It validates and previews; it
doesn't do the scraping. The two tracker repositories own the actual
ingestion logic, the data files, and the message-edit step that closes
the loop.

The two companion repos are:

- **[`poli0981/free-steam-games-list`](https://github.com/poli0981/free-steam-games-list)** —
  Steam free-to-play tracker.
- **[`poli0981/free-games-itchio-list`](https://github.com/poli0981/free-games-itchio-list)** —
  itch.io free-game tracker.

Both expose a `bot-ingest.yml` workflow that the bot calls.

---

## Part 1 — set up the bot

### 1.1 Prerequisites

- A Telegram account.
- A bot token from [`@BotFather`](https://t.me/BotFather) (`/newbot` →
  follow prompts → copy the token).
- A GitHub fine-grained PAT with `Actions: write` + `Contents: read`
  scoped to **only** the two tracker repos. (Classic PAT also works with
  the `workflow` scope.)
- Your numeric Telegram User ID (use `@userinfobot` or, after the bot is
  running, `/whoami`).
- Either Docker + Docker Compose, **or** Python 3.12 + a virtualenv.

### 1.2 Configure `.env`

```bash
cp .env.example .env
```

Edit `.env` and fill in:

```
BOT_TOKEN=123456789:AAAAAAAA...               # from @BotFather
GH_PAT=github_pat_...                         # fine-grained PAT
ALLOWED_USER_IDS=123456789                    # comma-separated IDs
STEAM_REPO=poli0981/free-steam-games-list     # or your fork
ITCH_REPO=poli0981/free-games-itchio-list     # or your fork
```

The remaining variables are optional and documented inline in
`.env.example`. Defaults are sensible for a single-user local deployment.

### 1.3 Run with Docker (recommended)

```bash
GIT_SHA=$(git rev-parse --short HEAD) docker compose up -d --build
docker compose logs -f bot
```

You should see in the logs:

```
post_init: connected as @your_bot_username (id=..., name=...)
post_init: setMyCommands + descriptions registered
```

That confirms `BOT_TOKEN` is valid (the `getMe` sanity check ran) and
that the slash-command menu is now visible to your Telegram client.

If `getMe` fails, the bot exits with a clear error — fix the token
before continuing.

### 1.4 Run without Docker (development)

```bash
py -3.12 -m venv .venv                       # Windows
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe -m bot.main
```

(Linux / macOS: `python3.12 -m venv .venv && source .venv/bin/activate && pip install -r requirements-dev.txt && python -m bot.main`.)

### 1.5 First contact

Open the bot in Telegram, send `/start`. If your user_id isn't in
`ALLOWED_USER_IDS` you'll see "⛔ Not authorized" — but `/whoami` still
works and gives you the ID to send to the operator (DM only — see
[`PRIVACY.md`](../PRIVACY.md)).

---

## Part 2 — set up the tracker repos

You need to do this **once per tracker repo**. The example below is for
the Steam repo; the itch one is identical except for filenames.

### 2.1 Configure secrets

In each tracker repo: **Settings → Secrets and variables → Actions →
New repository secret**.

| Name | Value | Why |
|---|---|---|
| `BOT_TOKEN` | Same `BOT_TOKEN` the bot uses | The workflow calls `editMessageText` to close the loop. |

That's it for secrets. The PAT used to *trigger* the workflow lives on
the bot side; the tracker repo doesn't need its own PAT.

### 2.2 Add `bot-ingest.yml`

In each tracker repo, add `.github/workflows/bot-ingest.yml`. The file
is large; the canonical template lives in
[`docs/tracker-workflows/`](tracker-workflows/) of this repo:

- [`docs/tracker-workflows/steam-bot-ingest.yml`](tracker-workflows/steam-bot-ingest.yml)
- [`docs/tracker-workflows/itch-bot-ingest.yml`](tracker-workflows/itch-bot-ingest.yml)

Copy the file, then **adjust the `Run ingest` step** to call your repo's
actual ingest entry point. The default placeholder is
`python -m steam_tracker.ingest_new ...` — replace with whatever your
repo provides.

### 2.3 Verify the dispatch loop

From the bot, send:

```
/q https://store.steampowered.com/app/440/
```

then tap **✅ Send**. You should observe:

1. The bot posts `⏳ Steam: dispatching 1 link(s)...`.
2. ~1–8 minutes later (depending on the tracker workflow's runtime),
   the message gets edited to:
   ```
   ✅ Steam: ingest complete
   <result summary>
   🔗 https://github.com/poli0981/free-steam-games-list/actions/runs/<id>
   ```

If the message stays as "dispatching" for >10 minutes, check the tracker
repo's Actions tab — the workflow may have errored before the
`editMessageText` step.

---

## Part 3 — daily flow

### 3.1 The full wizard

```
/start
  └─▶ tap Steam | itch | Mixed
       └─▶ paste links (multiple messages OK; .txt / .json upload OK)
            ├─ /show — peek at buffer
            ├─ /reset — clear buffer (stays in COLLECT)
            └─ /done
                 └─▶ Preview: Steam: N, itch: N, Duplicates: N, Invalid: N
                      ├─ tap ✅ Confirm  →  dispatch
                      ├─ tap ✏️ Edit     →  back to COLLECT (buffer kept)
                      └─ tap ❌ Cancel   →  abort
```

### 3.2 Quick dispatch

When you only have a couple of URLs and no need for a buffer, skip the
wizard:

```
/q https://store.steampowered.com/app/440/ https://store.steampowered.com/app/570/
```

The bot replies with a preview and inline ✅ Send / ❌ Cancel. Tapping
✅ Send dispatches immediately.

### 3.3 Retry

If a dispatch fails (workflow errored, GitHub Actions 5xx, etc.), you
get a 🔁 Retry button on the placeholder message. Tap it to re-dispatch
the **whole** last payload (or use `/retry` for the same effect).

`/retry` works for up to 30 minutes after the original dispatch.

### 3.4 Mode behavior

| Mode | Steam URLs | itch URLs |
|---|---|---|
| `Steam` | dispatched | counted as Invalid (filtered out) |
| `itch` | counted as Invalid | dispatched |
| `Mixed` | dispatched to Steam repo | dispatched to itch repo |

In `Mixed`, the bot creates **two separate placeholders** (one per
platform), each edited independently by its own workflow run.

### 3.5 Limits

| Limit | Default | Override |
|---|---|---|
| Per-user dispatches per window | 3 / 30 min | `RATE_LIMIT_USER_MAX`, `RATE_LIMIT_USER_WINDOW` |
| Global dispatches per window | 10 / 60 min | `RATE_LIMIT_GLOBAL_MAX`, `RATE_LIMIT_GLOBAL_WINDOW` |
| Concurrent dispatches per user | 1 (10 min stale) | (not user-configurable) |
| URLs per dispatch | 100 | `MAX_LINKS_PER_DISPATCH` |
| Upload file size | 256 KiB | (not user-configurable) |

`/status` shows your remaining quota and whether a dispatch is in flight.

### 3.6 Diagnostics

| When you want to know... | Run |
|---|---|
| Your Telegram user_id | `/whoami` |
| Bot version, git SHA, Python version | `/version` |
| Quota left + lock state | `/status` |
| All commands | `/help` |

---

## Part 4 — Troubleshooting

### Bot says "Not authorized"

Your user_id isn't in `ALLOWED_USER_IDS`. Run `/whoami`, DM the
operator your ID privately (do NOT post it in public), wait for them
to add you.

### `/start` works but `/done` says "Nothing buffered"

You're not in the COLLECT state. Run `/start` and pick a mode again.

### Pasted URLs are all marked Invalid

- Check the URL form. Steam: `https://store.steampowered.com/app/<appid>/...`,
  or a bare appid like `440`. itch: `https://<user>.itch.io/<game-slug>`.
- If you pasted multiple URLs concatenated without a separator (a common
  copy-paste artifact), the bot now splits them automatically; if you
  still see invalids, the URLs may have unusual characters — try one per
  line.

### Dispatch fails immediately

Check the bot logs for the HTTP status:

- `401 Bad credentials` — `GH_PAT` is invalid or revoked.
- `404 Not Found` — `STEAM_REPO` / `ITCH_REPO` is wrong, or
  `bot-ingest.yml` doesn't exist in that repo, or the PAT doesn't have
  access to the repo.
- `403 Forbidden` — PAT scopes are wrong; you need `Actions: write` on
  the target repo.
- `422 Unprocessable Entity` — usually the workflow rejected the inputs;
  check the workflow file's `inputs:` block.

### Dispatch succeeds but the message never gets edited

The workflow ran but didn't edit. Common causes:

1. `BOT_TOKEN` secret missing in the tracker repo — `Edit Telegram
   placeholder` step prints `::error::BOT_TOKEN secret is not configured`.
2. The workflow errored before reaching the edit step. Open the run from
   the link you saw in the placeholder (or the tracker repo's Actions
   tab) and read the failed step's logs.
3. The workflow was cancelled (replaced by a newer dispatch with the
   same `concurrency` group).

### Lock stuck in "in flight"

Send `/cancel`. As of v0.2.0, `/cancel` releases the lock. If that
doesn't help, the lock self-expires after 10 minutes regardless.

### Rate limit reached unexpectedly

`/status` shows the windows. If you restarted the bot mid-window, the
windows reset (in-memory state). If you're hitting the global cap,
another user dispatched recently — wait or raise
`RATE_LIMIT_GLOBAL_MAX` in `.env`.

### Bot crashed and lost my buffer

PicklePersistence saves `user_data` (including the buffer) to
`state/bot.pickle` after every handler. On restart the bot reloads it.
If the file got corrupted, delete it and `/start` over — you'll lose
the buffer but the bot will boot.

---

## Part 5 — operating notes

### Upgrading

```bash
git fetch origin main
git checkout main
git pull
GIT_SHA=$(git rev-parse --short HEAD) docker compose up -d --build
```

`docker compose` will SIGTERM the running container; the bot's
`_post_shutdown` waits up to 30 seconds for any in-flight dispatch to
complete before closing the httpx client. The shipped
`docker-compose.yml` sets `stop_grace_period: 35s` to honor that.

### Backups

`state/bot.pickle` is the only stateful file. Snapshot the `state/`
volume (or the bind-mounted directory) periodically if losing your
last_dispatch / pending_quick state would inconvenience you. Conversation
state survives one process restart already; a backup covers disk loss.

### Rotating tokens

- `BOT_TOKEN`: revoke and re-issue via `@BotFather → /revoke`. Update
  `.env` and the `BOT_TOKEN` secret in **both** tracker repos.
- `GH_PAT`: revoke at github.com/settings/personal-access-tokens, issue
  a new one with the same scopes, update `.env`.

### Logs

```bash
docker compose logs --tail=200 bot       # last 200 lines
docker compose logs -f bot                # follow
LOG_FORMAT=json docker compose up         # structured logs (pipe to jq)
```

Logs include user_ids, chat_ids, dispatch outcomes, and HTTP error
bodies (with token-shaped strings redacted). They do **not** include
the content of your messages.

---

## Command cheatsheet

| Command | Where | What it does |
|---|---|---|
| `/start`, `/scrape` | anywhere | Open the wizard |
| `/steam`, `/itch`, `/mixed` | CHOOSE | Pick mode (or use inline buttons) |
| `/done` | COLLECT | Show preview, advance to CONFIRM |
| `/yes` | CONFIRM | Confirm (or use ✅ button) |
| `/reset` | COLLECT | Clear buffer, stay in COLLECT |
| `/show` | COLLECT | Print current buffer |
| `/cancel` | anywhere | Abort wizard, release lock |
| `/q <urls>` | anywhere | One-shot dispatch, bypass wizard |
| `/retry` | anywhere | Replay last dispatch (within 30 min) |
| `/status` | anywhere | Quota + lock state |
| `/whoami` | anywhere (no auth) | Print your Telegram ID |
| `/version` | anywhere | Bot metadata |
| `/help` | anywhere | List commands |
