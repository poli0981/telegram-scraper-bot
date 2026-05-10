# Terms of Use / End-User License Agreement

**Last updated: 2026-05-10**

This document covers two distinct relationships:

1. Your use of the **source code** (the License section below).
2. Your interaction with a **specific running instance** of the Bot (the
   Service Terms section below).

The author publishes the source code; **the author does not operate a hosted
service**. Each operator runs their own deployment and is solely responsible
for it.

---

## A. License (Source Code)

The source code is licensed under the [MIT License](LICENSE).

Permitted: use, copy, modify, merge, publish, distribute, sublicense, and/or
sell copies of the software, subject to the conditions of the MIT License.

Required: include the copyright notice and the permission notice from
[LICENSE](LICENSE) in all copies or substantial portions of the software.

The author makes no commitment to provide updates, bug fixes, support,
roadmap items, or backward compatibility. Forking is encouraged.

## B. Service Terms (Running Instance)

If you are interacting with **somebody else's** running instance, the
following baseline applies (operators may impose stricter terms):

### B.1. No warranty

The Bot is provided **"AS IS" and "AS AVAILABLE"**, without warranty of any
kind, express or implied, including but not limited to the warranties of
merchantability, fitness for a particular purpose, title, and
non-infringement. See the full disclaimer in [`DISCLAIMER.md`](DISCLAIMER.md).

### B.2. No service-level commitment

The Bot is not a managed service. There is no SLA, no uptime guarantee, no
support contract, and no compensation for downtime, lost data, missed
dispatches, or failed workflows.

### B.3. Acceptable use

By using the Bot you agree to NOT:

- Submit content that is illegal in the operator's jurisdiction.
- Probe, scan, or test the vulnerability of the Bot or its host.
- Use the Bot to harvest, scrape, or extract data from third-party services
  in a way that violates those services' terms (Steam, itch.io, etc.).
- Bypass the rate limit, concurrency lock, or other protective gates.
- Submit malicious payloads (oversized files, exploit strings, prompt
  injection targeting the maintainer's review tools).
- Use the Bot in a way that would cause the operator's GitHub Actions
  budget, Telegram bot quota, or other resources to be exceeded with intent
  to disrupt service.

### B.4. Third-party services

Your use of the Bot inevitably involves Telegram (message transport) and
GitHub (workflow dispatch). You are bound by the terms of those services in
addition to these:

- Telegram Terms of Service: <https://telegram.org/tos>
- GitHub Terms of Service: <https://docs.github.com/en/site-policy>
- Steam, itch.io, and any other site whose URLs you submit: their respective
  terms.

The Bot does not assert any rights over content that originates from those
services.

### B.5. User authorization

The Bot enforces an allow-list (`ALLOWED_USER_IDS`). Authorization may be
granted, denied, or revoked by the operator at any time without notice.
Unauthorized users can use only `/whoami` to retrieve their own Telegram
ID for inclusion requests.

### B.6. Data handling

See [`PRIVACY.md`](PRIVACY.md) for what the Bot collects and where it goes.
By using the Bot you acknowledge that:

- Pasted URLs are forwarded to the configured GitHub Actions repositories.
- Your `chat_id` and message IDs are forwarded so workflow runs can edit
  your messages with results.
- Conversation state is persisted to disk for crash recovery.

### B.7. Changes to terms

Operators may update their service terms. Material changes affecting you as
a user should be communicated via the channel through which you initially
gained access.

### B.8. Termination

The operator may terminate your access at any time, including by removing
you from `ALLOWED_USER_IDS` or by shutting down the deployment. You may
stop using the Bot at any time.

### B.9. Governing law

These service terms are interpreted under the laws of the operator's
jurisdiction. The author of the source code is not party to any service
agreement and bears no liability for operator conduct.

## C. Severability

If any provision of these terms is found unenforceable, the remaining
provisions remain in full effect.
