<!--
Thanks for the PR. Fill in each section below; delete the prompts as you go.
Keep PRs focused — one topic per PR. Doc-only changes can ride with the
code change they describe; otherwise split.
-->

## Summary

<!--
1–3 bullets covering the *why* and the *what*. Link the issue this closes
(`Closes #123`) if applicable.
-->

-

## Type of change

<!-- Tick all that apply. -->

- [ ] Bug fix (non-breaking)
- [ ] New feature (non-breaking)
- [ ] Breaking change (note the migration path in **Risks** below)
- [ ] Documentation
- [ ] Workflow / CI / build infrastructure
- [ ] Refactor (no functional change)
- [ ] Test-only

## Test plan

<!--
Concrete, reproducible steps. If you ran tests locally, list the command
output. If the change is user-facing, include the expected Telegram UX
(e.g., "/help now lists /foo").
-->

- [ ] `pytest` passes locally (`.venv/Scripts/python.exe -m pytest -q`).
- [ ] `ruff check bot/ tests/` clean.
- [ ] `ruff format --check bot/ tests/` clean.
- [ ] Manual smoke test in Telegram (where applicable):
  - …

## Risks / open questions

<!--
What could go wrong? Are there migration steps? Performance implications?
Anything you're unsure about? "None" is a fine answer for small changes.
-->

-

## Documentation

- [ ] `README.md` updated if user-facing surface changed.
- [ ] `CHANGELOG.md` entry added under `[Unreleased]`.
- [ ] `docs/USER_GUIDE.md` updated if the bot's user flow changed.
- [ ] No update needed.

## Privacy / security check

- [ ] No secrets, tokens, or `BOT_TOKEN`/`GH_PAT` values in the diff.
- [ ] No third-party Telegram User IDs in code, tests, comments, or fixtures.
- [ ] Logs do not surface user content (URLs, file contents) at INFO level
      or higher unless redacted.
- [ ] Any new external HTTP call is documented and rate-limit-safe.

## AI assistance

<!--
Disclose AI-assisted contributions per the convention in
ACKNOWLEDGEMENTS.md. Commits should include `Co-Authored-By: Claude` (or
similar) where the model contributed substantively.
-->

- [ ] No AI assistance.
- [ ] AI-assisted; commits include `Co-Authored-By:` trailer.

---

By submitting this PR you agree your contribution is licensed under the
project's [MIT License](../LICENSE) and you abide by the
[Code of Conduct](../CODE_OF_CONDUCT.md).
