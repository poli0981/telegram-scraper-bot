# Security Policy

## Reporting a vulnerability

**Do NOT open a public GitHub issue or discussion for security
vulnerabilities.**

Use one of the following private channels (in order of preference):

1. **GitHub Security Advisories** — preferred. Go to the repository's
   *Security → Report a vulnerability* page; this opens a private advisory
   that only the maintainer can see. <https://github.com/poli0981/telegram-scraper-bot/security/advisories/new>
2. **Email** — `lopop05905@proton.me` (subject prefix: `[security]`).
3. **Telegram DM** — `@SkullMute0011` or via the bot `@my_skull_bot`.
4. **Discord DM** — `skullmute` (account linked from
   [`AUTHORS.md`](AUTHORS.md)).

If you are unsure which channel is best, default to email or the GitHub
Security Advisory form.

When reporting, include:

- Affected version(s) (output of `/version` or the git SHA).
- Reproduction steps or proof-of-concept (minimal, if possible).
- Impact you assess (information disclosure, RCE, auth bypass, DoS, etc.).
- Whether you have already disclosed this to anyone else.

## What counts as a vulnerability

- Auth-bypass for the allow-list (`ALLOWED_USER_IDS`).
- Token leak through logs, error messages, or pickled state files.
- Remote code execution via crafted input (paste, file upload, callback
  data).
- Privilege escalation via the workflow_dispatch path (e.g., crafting
  inputs that trick the GitHub Actions workflow into executing untrusted
  code).
- Denial-of-service that survives a process restart (e.g., unbounded
  growth of `bot_data` that wedges PicklePersistence).
- Anything else where the Bot leaks data outside the operator's intended
  trust boundary.

## What is **not** in scope

- Telegram client vulnerabilities — report to Telegram.
- GitHub Actions / GitHub itself — report to GitHub.
- Steam, itch.io, or any tracked third-party site — report upstream.
- Misconfiguration where the operator publicly exposed `BOT_TOKEN` or
  `GH_PAT` (rotate the credential and audit logs).
- Issues in the **example tracker workflows** that you copy into your own
  repos — those are starter templates and you own them after copying.
- AI-generated false-positive scanner findings without a working PoC.

## Response process

The maintainer is one person and operates on a best-effort basis. Expect:

- Initial acknowledgement within **5 business days**.
- Triage (severity assessment, scope confirmation) within **14 days**.
- Fix or mitigation for High/Critical issues within **30 days** of triage,
  shipped in a patch release.
- Public disclosure (CVE if applicable, CHANGELOG entry, advisory) **after**
  a fix is available, with reporter credit unless you ask to remain
  anonymous.

For Critical issues affecting in-the-wild deployments, a coordinated
disclosure window of 90 days is the upper bound.

## Supported versions

| Version | Supported |
|---|---|
| `0.2.x` | ✅ active |
| `0.1.x` | ⚠ security fixes only — please upgrade |
| `< 0.1` | ❌ unsupported |

The project is pre-1.0 and self-hosted. Operators are expected to upgrade
within a reasonable window after a security release.

## Hardening checklist for operators

If you operate an instance, please ensure:

- [ ] `BOT_TOKEN` and `GH_PAT` are stored only in `.env` (never committed).
- [ ] `.env` permissions are `600` and not world-readable.
- [ ] `state/bot.pickle` is on an encrypted volume or filesystem with
      restrictive permissions.
- [ ] Container runs as non-root (the shipped Dockerfile does).
- [ ] `ALLOWED_USER_IDS` only contains trusted users.
- [ ] `GH_PAT` is fine-grained, scoped to the two tracker repos, with
      `Actions: write` and `Contents: read` only — no broader scopes.
- [ ] Logs are rotated (`docker-compose.yml` ships `max-size: 10m, max-file: 3`).
- [ ] `BOT_TOKEN` is rotated if you suspect compromise (re-issue via
      `@BotFather → /revoke`).
- [ ] `GH_PAT` is rotated periodically and on suspected compromise.
