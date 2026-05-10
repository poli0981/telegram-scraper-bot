# Development environment

The reference development machine. Other configurations should also work
— Linux + any Python 3.12 will be fine — but the maintainer tests
primarily on what's listed below.

## Primary developer machine

| Component | Details |
|---|---|
| OS | Windows 11 Pro 25H2 Insider Preview (Dev Channel) |
| Build | 26300.8376 |
| CPU | Intel Core i7-14700KF |
| GPU | NVIDIA GeForce RTX 5080 (16 GB VRAM) |
| RAM | 32 GB DDR5 |
| Storage | 1 TB SSD |
| IDE | JetBrains PyCharm 2026.1.x (paid) |
| Container runtime | Docker Desktop (Personal), v4.71.0 (build 225177) |

## Software stack

| Tool | Version | Notes |
|---|---|---|
| Python | 3.12.10 | Pinned in `pyproject.toml` (`requires-python = "==3.12.*"`) |
| ruff | 0.7.4 | Linter + formatter; CI fails on violation |
| pytest | 8.3.3 | Test runner with `pytest-asyncio` and `pytest-cov` |
| respx | 0.21.1 | `httpx` mock for dispatcher tests |
| Docker | 4.71.0 | For the local-Docker workflow |
| Git | ≥ 2.40 | Signed commits + signed tags expected (GPG or SSH) |

## What "works on my machine" guarantees you

- Python 3.12 pinned via `pyproject.toml` and `Dockerfile`.
- Tests run on Ubuntu 24.04 in CI as a sanity check on the pinned spec.
- Windows-specific path quirks have been smoothed (Path objects, no
  hard-coded forward slashes).

## What it doesn't

- Bare-metal Windows 11 host (the bot is designed for Docker / Linux
  servers in production).
- macOS or BSD — should work, never tested by the maintainer.
- Python 3.13+ — pyproject.toml will refuse to install. We pin to 3.12
  on purpose so the in-prod runtime matches the developer's runtime.

## Optional: matching the reference setup

If you want the same dev experience:

```bash
# Python 3.12 via pyenv (Linux/macOS) or python.org installer (Windows)
py -3.12 -m venv .venv

# Install dev deps
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt

# Configure git signing (one-time, if not already done)
git config commit.gpgsign true
git config tag.gpgsign true
git config user.signingkey <YOUR_GPG_KEY_ID>
# or for SSH:
# git config gpg.format ssh
# git config user.signingkey ~/.ssh/id_ed25519.pub

# Run tests + lint to confirm setup
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check bot/ tests/
.venv/Scripts/python.exe -m ruff format --check bot/ tests/
```
