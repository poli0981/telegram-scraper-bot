# Privacy Policy

**Last updated: 2026-05-10**

`telegram-scraper-bot` ("the Bot") is a self-hosted, open-source Telegram bot.
Each operator runs their own instance. **The author of the source code does
NOT operate a hosted instance** and never receives data from your bot.

This document describes the data your **self-hosted** instance handles. If you
interact with somebody else's instance, ask that operator for their policy.

## 1. Data the Bot processes

The Bot is provided by Telegram with the standard `Update` payload for any
message you send. From this it reads:

| Field | Purpose | Storage |
|---|---|---|
| Telegram `user_id` | Allow-list authorization (`ALLOWED_USER_IDS`) | In-memory; appears in logs |
| Telegram `username`, `first_name` | Logged on auth-rejection; rendered by `/whoami` | Logs only; not persisted |
| `chat_id` | Identify where to reply / where the workflow should edit | In-memory; persisted in `bot.pickle` for the duration of an active wizard |
| `message_id` (placeholder) | Identify the message the workflow will edit with results | Sent to GitHub as a workflow input; persisted briefly |
| URLs you paste / upload | The Bot's whole purpose. Forwarded to GitHub Actions as a workflow input. | Buffered in `user_data` until `/done`; saved as `last_dispatch` for `/retry` (TTL 30 min) |

Sensitive secrets (`BOT_TOKEN`, `GH_PAT`) live in the operator's environment;
the Bot never echoes them back and the dispatcher redacts token-shaped strings
before logging.

## 2. Data the Bot does NOT collect

- No analytics, telemetry, or usage tracking.
- No advertising IDs, fingerprints, or device data.
- No content of messages other than what you explicitly paste/upload.
- No access to your contacts, groups, or chat history beyond the Bot's chat.

## 3. Where your data goes

Two destinations only:

1. **Telegram** — by definition; your message goes through Telegram before the
   Bot sees it. Telegram's privacy policy applies upstream:
   <https://telegram.org/privacy>.
2. **GitHub Actions** in the configured tracker repos — the Bot sends your
   pasted URLs, your `chat_id`, and the placeholder `message_id` as
   `workflow_dispatch` inputs so the workflow can edit your message with the
   result. Nothing else is forwarded.

There are no third-party analytics, no remote logging services, and no
outbound calls beyond Telegram and GitHub.

## 4. Persistence on disk

The operator's host stores `bot.pickle` (default path: `state/bot.pickle`,
configurable via `PERSISTENCE_PATH`). It contains the active conversation
state — buffer, mode, last preview, last_dispatch payload — for crash
recovery. Old entries beyond their TTL are not actively pruned but are
ignored on read.

Operators are responsible for securing this file (filesystem permissions,
disk encryption at rest, backups).

## 5. Logs

Logs are written to stdout. In Docker, `docker-compose.yml` configures
`json-file` driver with `max-size: 10m, max-file: 3` (≈30 MB rolling).

Logs include `user_id`, `chat_id`, message IDs, dispatch outcomes, and HTTP
error bodies (with token-shaped strings redacted via the
[`bot/dispatcher.py`](bot/dispatcher.py) `_redact` helper). They do **not**
include the content of your messages.

## 6. Your rights (when interacting with someone else's instance)

If you interact with a third-party operator's bot:

- **Right to access / deletion**: contact that operator directly. They can
  delete `state/bot.pickle` and their log files.
- **Right to revoke authorization**: ask the operator to remove your user_id
  from `ALLOWED_USER_IDS`. Without authorization, the Bot will not accept
  your messages beyond the `/whoami` self-discovery command.
- **Telegram User ID is sensitive**. Do **not** post screenshots of `/whoami`
  publicly. If you need to share your ID with the operator, send it via DM
  through one of the channels listed in [`AUTHORS.md`](AUTHORS.md).

## 7. Children

The Bot is not directed at children under 13. Do not use it if you cannot
agree to Telegram's own age requirements.

## 8. Changes to this policy

Changes are tracked in [`CHANGELOG.md`](CHANGELOG.md) under the "Privacy"
section of any release that touches data handling.

## 9. Contact

For privacy questions about the **author's** code (not any specific
operator's deployment), see [`AUTHORS.md`](AUTHORS.md) for contact channels.
