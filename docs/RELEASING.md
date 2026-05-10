# Releasing

The maintainer's checklist for cutting a new version. Contributors don't
need this — your PR gets included in the next release the maintainer
cuts.

## Versioning policy

[SemVer 2.0](https://semver.org). Pre-1.0 caveat: we may break things in
minor bumps until `1.0.0`. Once 1.0.0 ships, MAJOR.MINOR.PATCH is binding.

## Release flow

```
[Author commits / merges PRs to main]
         ↓
[Bump version  →  PR  →  merge]
         ↓
[Tag signed  →  push tag]
         ↓
[release.yml fires  →  GitHub Release created]
         ↓
[announce-release.yml fires  →  Discord notification]
```

### Step 1 — close out the CHANGELOG

Move the items from `[Unreleased]` to a new `[X.Y.Z] — YYYY-MM-DD`
section in [`CHANGELOG.md`](../CHANGELOG.md). Add the comparison link at
the bottom:

```markdown
[X.Y.Z]: https://github.com/poli0981/telegram-scraper-bot/compare/vPREV...vX.Y.Z
```

Reset `[Unreleased]` to `_No unreleased changes._`.

Commit this on `main` (or as part of the release PR — either works).

### Step 2 — bump version

Two options:

**Option A — manual.** Edit:
- `bot/__init__.py` → `__version__ = "X.Y.Z"`
- `pyproject.toml` → `version = "X.Y.Z"`

Open a PR titled `chore: bump version to X.Y.Z`, merge.

**Option B — automated.** Run the workflow:

```
gh workflow run "Bump version" -f new_version=X.Y.Z
```

This runs `.github/workflows/bump-version.yml` which edits both files,
opens a `release/vX.Y.Z` branch, pushes, and opens a PR for you. Review
and merge it.

### Step 3 — pull, tag, push

```
git checkout main
git pull
git tag -s vX.Y.Z -m "Release vX.Y.Z"
git push origin vX.Y.Z
```

`tag.gpgsign = true` should already cause `git tag` (without `-s`) to
sign by default — `-s` is explicit and safe.

If your tag fails to sign with GPG, debug with:

```
echo "test" | gpg --clearsign      # confirms GPG is alive
git config --get user.signingkey   # must be set
gpg --list-secret-keys             # must include the configured key
```

### Step 4 — wait for the release workflow

`release.yml` triggers on `push: tags: [v*]`. It:

1. Checks out the repo at the tag.
2. Verifies the tag is annotated (warns if not signed).
3. Extracts the matching CHANGELOG section as release notes.
4. Creates the GitHub Release with notes + opens an "Announcements"
   discussion (best-effort; falls back gracefully if Discussions isn't
   enabled).

Watch it run:

```
gh run watch
```

### Step 5 — Discord announcement (automatic)

`announce-release.yml` fires on `release: [published]`. The wrapper
calls `poli0981/.github/.github/workflows/announce-release.yml@main`
which posts to the configured Discord webhooks (`DISCORD_RELEASES_WEBHOOK`
and/or `DISCORD_REPO_WEBHOOK` org-level secrets) and optionally pings
the role at `DISCORD_PING_ROLE_ID`.

If the announcement skips, check that the org-level secrets are set on
the `poli0981/.github` repo and that the bot account has access.

### Step 6 — verify

- Open the release on GitHub: it should have notes + "Discussion for
  this release" link.
- Open the Discord announcement channel: there should be an embed.
- Confirm the Docker image was rebuilt locally with the new SHA:
  `GIT_SHA=$(git rev-parse --short vX.Y.Z) docker compose build`.

### Step 7 — bump back to `[Unreleased]`

The release is out. If you didn't already in step 1, push a small
`chore: open [Unreleased] in CHANGELOG` commit so the next contribution
has a place to land.

## Rollback

If a release is broken:

1. Delete the release on GitHub (Releases page → Edit → Delete).
2. Delete the tag locally and remotely:
   ```
   git tag -d vX.Y.Z
   git push origin --delete vX.Y.Z
   ```
3. Push a fix commit on `main`.
4. Cut a new patch tag (`vX.Y.Z+1`).

Don't reuse a tag — repeating `v0.2.0` after a delete is confusing for
anyone who pulled the broken version. Always step forward.
