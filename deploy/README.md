# Deployment

Two supported paths. Pick whichever fits your infra better.

---

## Option A — Docker / docker-compose

**Best for:** home server with Docker already running, easy isolation, simple log rotation.

### One-time setup

```bash
git clone https://github.com/poli0981/telegram-scraper-bot.git
cd telegram-scraper-bot
cp .env.example .env
$EDITOR .env                  # fill in BOT_TOKEN, GH_PAT, ALLOWED_USER_IDS, repos
mkdir -p state
docker compose build
```

### Run

```bash
docker compose up -d
docker compose logs -f bot
```

### Update

```bash
git pull
docker compose build
docker compose up -d            # zero-downtime swap
```

### Stop

```bash
docker compose down
```

State (PicklePersistence) lives in `./state/bot.pickle` on the host — survives container rebuilds.

---

## Option B — systemd on bare metal

**Best for:** VPS without Docker, tighter resource control, unified logging via journald.

### One-time setup

```bash
# As your normal user (e.g. kokone):
git clone https://github.com/poli0981/telegram-scraper-bot.git ~/telegram-scraper-bot
cd ~/telegram-scraper-bot

python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env
$EDITOR .env

mkdir -p state
```

### Install the service

```bash
# Edit deploy/bot.service if your username/path differs from /home/kokone
sudo cp deploy/bot.service /etc/systemd/system/telegram-scraper-bot.service
sudo systemctl daemon-reload
sudo systemctl enable --now telegram-scraper-bot
```

### Operate

```bash
sudo systemctl status telegram-scraper-bot          # status
journalctl -u telegram-scraper-bot -f               # follow logs
sudo systemctl restart telegram-scraper-bot         # restart after update
sudo systemctl stop telegram-scraper-bot            # stop
```

### Update

```bash
cd ~/telegram-scraper-bot
git pull
.venv/bin/pip install -r requirements.txt           # if deps changed
sudo systemctl restart telegram-scraper-bot
```

---

## Health check

After either deployment, send `/start` to your bot in Telegram. You should get
the mode-picker keyboard if your `ALLOWED_USER_IDS` includes your account.

If you get nothing:
- Check logs (`docker compose logs bot` or `journalctl -u telegram-scraper-bot`)
- Verify `BOT_TOKEN` is correct (test with `curl https://api.telegram.org/bot<TOKEN>/getMe`)
- Verify your Telegram user ID is in `ALLOWED_USER_IDS` (get yours from [@userinfobot](https://t.me/userinfobot))

If you get `⛔ Not authorized.`, the bot is alive but your ID isn't whitelisted.
