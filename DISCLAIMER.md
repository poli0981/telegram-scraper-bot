# Disclaimer

**Last updated: 2026-05-10**

## No warranty

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.

This is the standard MIT disclaimer. It is not negotiable.

## No affiliation

`telegram-scraper-bot` is an independent project. It is **not** affiliated
with, endorsed by, sponsored by, or in any way officially connected to:

- **Telegram** / **Telegram FZ-LLC** / **Telegram Messenger Inc.**
- **Valve Corporation** / **Steam** / **Steamworks**
- **itch.io** / **itch corp**
- **GitHub** / **Microsoft Corporation**
- Any game publisher, developer, or distributor whose URLs you may submit.

All product names, trademarks, and registered trademarks are property of
their respective owners. Use of these names is for identification purposes
only and does not imply endorsement.

## No responsibility for third-party content

The Bot dispatches URLs you provide to GitHub Actions workflows that fetch
data from third-party websites (Steam store pages, itch.io game pages, etc.).
The author and operator:

- Do **not** vouch for the accuracy, legality, availability, or quality of
  any third-party content.
- Do **not** host any of that content; only metadata is processed.
- Are **not** responsible for changes in third-party APIs, rate limits, or
  terms of service that may break the Bot.

## No responsibility for misuse

You are solely responsible for what you submit to the Bot. The author and
operator are not responsible for:

- Account suspensions or bans on Steam, itch.io, GitHub, Telegram, or any
  other platform that may result from automated requests originating from
  the Bot or its workflow runs.
- Rate-limit or terms-of-service violations on third-party sites.
- Breach of contract with employers or clients if you use the Bot in a
  context where automated tooling is restricted.
- Any legal, financial, reputational, or data-loss consequences arising
  from your use of the Bot.

## Self-hosted nature

The Bot is designed to be **self-hosted**. The published source code is
infrastructure you stand up yourself; running it makes you the operator and
data controller. The author of the source code does not operate a hosted
service, does not have access to your data, and cannot recover lost state
on your behalf.

## Data accuracy

The Bot is a thin dispatcher. The actual data fetching is performed by the
GitHub Actions workflows in the configured tracker repositories. Bugs,
regressions, or data quality issues there are out of scope of this Bot's
warranty (which, to be clear, is none — see the top of this document).

## Beta / pre-release software

Portions of the Bot have been tagged with versions (e.g. `v0.1.0`,
`v0.2.0`). Pre-1.0 versions are explicitly developmental. Breaking changes
may occur in any minor version bump until `v1.0.0`. See
[`CHANGELOG.md`](CHANGELOG.md).

## Compliance

You are responsible for ensuring that your use of the Bot complies with all
applicable laws and regulations in your jurisdiction, including but not
limited to data-protection law (GDPR, CCPA, etc.), copyright law, and
computer-misuse statutes.

## AI-assisted development

Portions of this codebase were authored or refactored with the assistance
of large language models (Claude Code in particular). All output was
human-reviewed before being merged. See [`ACKNOWLEDGEMENTS.md`](ACKNOWLEDGEMENTS.md)
for details. The disclaimer above (no warranty) covers AI-generated
contributions equivalently to human-written code.
